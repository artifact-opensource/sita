"""
SITA — Reflection Loop
The self-improving engine. Every N closed trades, Hermes reflects and edits strategy.yaml.

Two modes:
1. --fallback: deterministic rule-based reflection (no LLM needed)
2. --hermes: LLM-powered reflection (production mode)

Core principle: change exactly ONE variable per cycle. Scientific method.
"""

from __future__ import annotations
import json
import logging
import subprocess
import shutil
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone

from ..config import STATE_DIR, HISTORY_DIR, DEFAULT_REFLECTION_EVERY, ONE_VARIABLE_ONLY

logger = logging.getLogger("sita.reflection")


class ReflectionEngine:
    """
    Reflection engine — the self-improvement loop.

    Every N trades:
    1. Pull last N trade outcomes
    2. Score against goal.yaml
    3. Generate hypotheses (what variable to change)
    4. Apply exactly ONE change to strategy.yaml
    5. Save prior version to history/
    6. Append hypothesis to hypotheses.jsonl
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.reflection_every = self.config.get("reflection_every", DEFAULT_REFLECTION_EVERY)
        self.one_variable_only = self.config.get("one_variable_only", ONE_VARIABLE_ONLY)
        self.state_dir = Path(self.config.get("state_dir", STATE_DIR))
        self.history_dir = Path(self.config.get("history_dir", HISTORY_DIR))
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def should_reflect(self) -> bool:
        """Check if it's time to reflect."""
        trades_file = self.state_dir / "trades.jsonl"
        if not trades_file.exists():
            return False

        # Count closed trades since last reflection
        with open(trades_file) as f:
            lines = f.readlines()

        # Count trades since last reflection marker
        new_trades = 0
        for line in reversed(lines):
            try:
                trade = json.loads(line)
                if trade.get("_reflection_marker"):
                    break
                new_trades += 1
            except json.JSONDecodeError:
                continue

        return new_trades >= self.reflection_every

    def reflect_fallback(self) -> Dict[str, Any]:
        """
        Deterministic fallback reflection.
        Used before Hermes is installed or as a safety net.

        Rules:
        - If return < target: loosen entry threshold by 2
        - If drawdown > max: tighten stop_loss_pct by 0.2
        - If win rate < 40%: reduce position size
        - Always changes exactly ONE variable
        """
        goal = self._load_goal()
        strategy = self._load_strategy()
        trades = self._load_recent_trades(25)

        if not trades:
            return {"action": "none", "reason": "No trades to reflect on"}

        # Score current performance
        score = self._score_performance(trades, goal)
        logger.info(f"Reflection score: {score:.2f}")

        # Generate hypotheses
        hypotheses = self._generate_hypotheses(score, trades, goal, strategy)

        if not hypotheses:
            return {"action": "none", "reason": "No hypotheses generated"}

        # Pick highest confidence hypothesis
        best = max(hypotheses, key=lambda h: h.get("confidence", 0))
        logger.info(f"Best hypothesis: {best['description']} (confidence={best['confidence']:.2f})")

        # Apply the change
        result = self._apply_hypothesis(best, strategy)

        return {
            "action": "applied",
            "hypothesis": best,
            "score": score,
            "result": result,
        }

    def reflect_hermes(self) -> Dict[str, Any]:
        """
        Hermes-powered reflection.
        Reads trades and current strategy, formats prompt, calls Hermes subprocess.
        """
        goal = self._load_goal()
        strategy = self._load_strategy()
        trades = self._load_recent_trades(25)

        if not trades:
            return {"action": "none", "reason": "No trades to reflect on"}

        # Format prompt for Hermes
        prompt = self._format_hermes_prompt(trades, goal, strategy)

        try:
            result = subprocess.run(
                ["hermes", "chat", "-q", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"Hermes reflection failed: {result.stderr}")
                return {"action": "error", "reason": result.stderr}

            # Parse Hermes output
            hermes_output = result.stdout.strip()
            hypothesis = self._parse_hermes_output(hermes_output)

            if hypothesis:
                apply_result = self._apply_hypothesis(hypothesis, strategy)
                return {
                    "action": "applied",
                    "hypothesis": hypothesis,
                    "hermes_output": hermes_output,
                    "result": apply_result,
                }
            else:
                return {"action": "no_hypothesis", "hermes_output": hermes_output}

        except FileNotFoundError:
            logger.warning("Hermes not found — falling back to deterministic reflection")
            return self.reflect_fallback()
        except subprocess.TimeoutExpired:
            logger.error("Hermes reflection timed out")
            return {"action": "timeout"}

    def _score_performance(self, trades: List[Dict], goal: Dict) -> float:
        """
        Score trades against goal. Returns float in [-1, +1].

        Composite of:
        - Realized return vs target
        - Drawdown vs max
        - Sharpe vs min
        """
        if not trades:
            return 0.0

        # Calculate metrics
        pnls = [t.get("pnl", 0) for t in trades]
        total_pnl = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) if pnls else 0

        # Return score — normalize to per-trade basis, not 30-day
        # Target is 5% per 30 days = ~0.17% per day = ~0.007% per 15min trade
        # For reflection, we use a simpler metric: are we winning more than losing?
        target_return = goal.get("target_return_30d", 0.05)
        actual_return = total_pnl / goal.get("initial_balance", 10000)
        # Normalize: if we're making money, score is positive
        if actual_return > 0:
            return_score = min(actual_return / (target_return / 30), 1.0)  # Daily normalized
        else:
            return_score = max(actual_return / (target_return / 30), -1.0)

        # Drawdown score
        max_dd = goal.get("max_drawdown", 0.08)
        peak = 0
        dd = 0
        running = 0
        for p in pnls:
            running += p
            if running > peak:
                peak = running
            current_dd = (peak - running) / peak if peak > 0 else 0
            if current_dd > dd:
                dd = current_dd
        dd_score = 1.0 - (dd / max_dd) if max_dd > 0 else 1.0

        # Win rate score
        wr_score = win_rate

        # Composite
        score = (return_score * 0.4 + dd_score * 0.3 + wr_score * 0.3)
        return max(-1.0, min(1.0, score))

    def _generate_hypotheses(self, score, trades, goal, strategy) -> List[Dict]:
        """Generate hypotheses for what to change. Analyzes loss patterns."""
        hypotheses = []
        current_strategy = strategy.get("entry", {})

        # Analyze loss patterns
        pnls = [t.get("pnl", 0) for t in trades]
        losses = [p for p in pnls if p < 0]
        wins = [p for p in pnls if p > 0]

        # Per-symbol analysis
        symbol_pnls = {}
        for t in trades:
            sym = t.get("symbol", "unknown")
            if sym not in symbol_pnls:
                symbol_pnls[sym] = []
            symbol_pnls[sym].append(t.get("pnl", 0))

        # Find the worst-performing symbol
        worst_symbol = None
        worst_pnl = 0
        for sym, pnls_list in symbol_pnls.items():
            total = sum(pnls_list)
            if total < worst_pnl:
                worst_pnl = total
                worst_symbol = sym

        # Hypothesis 1: If a specific symbol is consistently losing, stop trading it
        if worst_symbol and worst_pnl < -100:
            hypotheses.append({
                "variable": f"disable_symbol",
                "current_value": worst_symbol,
                "new_value": "disabled",
                "direction": "disable",
                "description": f"Disable {worst_symbol} (losing ${worst_pnl:.2f})",
                "confidence": 0.85,
                "reasoning": f"{worst_symbol} consistently losing — stop trading it",
            })

        # Hypothesis 2: If avg loss > avg win, tighten stops
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        current_sl = strategy.get("stop_loss_pct", 2.0)

        if avg_loss > avg_win * 1.5 and current_sl > 0.5:
            new_sl = max(0.5, current_sl - 0.3)
            hypotheses.append({
                "variable": "stop_loss_pct",
                "current_value": current_sl,
                "new_value": new_sl,
                "direction": "tighten",
                "description": f"Tighten SL: {current_sl}% → {new_sl}% (avg loss ${avg_loss:.0f} > avg win ${avg_win:.0f})",
                "confidence": 0.8,
                "reasoning": f"Average loss (${avg_loss:.0f}) exceeds average win (${avg_win:.0f})",
            })

        # Hypothesis 3: If win rate < 40%, change indicator
        win_rate = len(wins) / len(pnls) if pnls else 0.5
        current_indicator = current_strategy.get("indicator", "rsi")
        current_threshold = current_strategy.get("threshold", 30)

        if win_rate < 0.4:
            alternatives = {"rsi": "ema", "ema": "sma", "sma": "momentum", "momentum": "rsi"}
            new_indicator = alternatives.get(current_indicator, "ema")
            hypotheses.append({
                "variable": "entry.indicator",
                "current_value": current_indicator,
                "new_value": new_indicator,
                "direction": "change",
                "description": f"Change indicator: {current_indicator} → {new_indicator} (WR {win_rate:.0%})",
                "confidence": 0.7,
                "reasoning": f"Win rate {win_rate:.0%} too low for {current_indicator}",
            })

        # Hypothesis 4: If score < -0.3, reduce position size
        current_size = strategy.get("position_size_r", 0.5)
        if score < -0.3 and current_size > 0.1:
            new_size = max(0.1, current_size - 0.1)
            hypotheses.append({
                "variable": "position_size_r",
                "current_value": current_size,
                "new_value": new_size,
                "direction": "reduce",
                "description": f"Reduce size: {current_size} → {new_size}R (score {score:.2f})",
                "confidence": 0.6,
                "reasoning": "Significant underperformance — reduce exposure",
            })

        # Hypothesis 5: If threshold is already very loose (< 25 for RSI), change direction
        current_direction = strategy.get("entry", {}).get("direction", "long") if isinstance(strategy.get("entry"), dict) else strategy.get("entry.direction", "long")
        if current_indicator == "rsi" and current_threshold < 25 and current_direction != "both":
            hypotheses.append({
                "variable": "entry.direction",
                "current_value": current_direction,
                "new_value": "both",
                "direction": "expand",
                "description": "Allow both long and short signals",
                "confidence": 0.65,
                "reasoning": "Threshold already loose — market may need directional flexibility",
            })

        # Hypothesis 6: Loosen entry threshold (original, but lower priority)
        if score < 0 and current_threshold > 20:
            new_threshold = max(15, current_threshold - 2)
            hypotheses.append({
                "variable": "entry.threshold",
                "current_value": current_threshold,
                "new_value": new_threshold,
                "direction": "loosen",
                "description": f"Loosen threshold: {current_threshold} → {new_threshold}",
                "confidence": min(abs(score) * 100, 0.9) * 0.5,  # Lower confidence
                "reasoning": "Return below target — need more entries",
            })

        return hypotheses

    def _apply_hypothesis(self, hypothesis: Dict, strategy: Dict) -> Dict:
        """Apply a hypothesis to strategy.yaml. Changes exactly ONE variable."""
        variable = hypothesis["variable"]
        new_value = hypothesis["new_value"]

        # Save current strategy to history
        version = strategy.get("version", "01")
        history_file = self.history_dir / f"v{version}.yaml"
        import yaml
        with open(history_file, "w") as f:
            yaml.dump(strategy, f)
        logger.info(f"Saved strategy v{version} to history")

        # Apply the change
        parts = variable.split(".")
        if variable == "disable_symbol":
            # Special handling: disable a symbol
            disabled = strategy.get("disabled_symbols", [])
            if hypothesis["current_value"] not in disabled:
                disabled.append(hypothesis["current_value"])
            strategy["disabled_symbols"] = disabled
            new_value = disabled
            target = None
        elif variable == "entry.direction" and new_value == "both":
            # Special: allow both directions
            target = strategy
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = new_value
        else:
            target = strategy
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = new_value

        # Bump version
        try:
            version_num = int(version)
            strategy["version"] = f"{version_num + 1:02d}"
        except ValueError:
            strategy["version"] = "02"

        # Save updated strategy
        strategy_file = self.state_dir / "strategy.yaml"
        with open(strategy_file, "w") as f:
            yaml.dump(strategy, f)

        # Append hypothesis
        hypotheses_file = self.state_dir / "hypotheses.jsonl"
        with open(hypotheses_file, "a") as f:
            f.write(json.dumps({
                **hypothesis,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "strategy_version": strategy["version"],
            }) + "\n")

        # Mark trades as reflected
        self._mark_trades_reflected()

        logger.info(f"Applied hypothesis: {hypothesis['description']}")
        return {"version": strategy["version"], "variable": variable, "new_value": new_value}

    def _format_hermes_prompt(self, trades: List[Dict], goal: Dict, strategy: Dict) -> str:
        """Format the reflection prompt for Hermes."""
        return f"""You are the reflection engine of a self-improving trading agent.

## Goal
- Target return: {goal.get('target_return_30d', 'N/A')} per 30 days
- Max drawdown: {goal.get('max_drawdown', 'N/A')}
- Min Sharpe: {goal.get('min_sharpe', 'N/A')}
- Reflection cadence: every {self.reflection_every} trades

## Current Strategy (v{strategy.get('version', '01')})
{json.dumps(strategy, indent=2)}

## Last {len(trades)} Trades
{json.dumps(trades[-10:], indent=2)}

## Task
1. Score the recent performance against the goal (return, drawdown, win rate)
2. Generate 1-3 hypotheses for what SINGLE variable to change in strategy.yaml
3. Each hypothesis must name exactly ONE variable and predict the score direction
4. Pick the highest-confidence hypothesis
5. Output in this exact JSON format:

```json
{{
  "variable": "entry.threshold",
  "current_value": 30,
  "new_value": 28,
  "direction": "loosen",
  "description": "Loosen entry threshold: 30 → 28",
  "confidence": 0.75,
  "reasoning": "Return below target, need more entries"
}}
```

Output ONLY the JSON, nothing else."""

    def _parse_hermes_output(self, output: str) -> Optional[Dict]:
        """Parse Hermes JSON output."""
        import re
        # Try to find JSON in output
        json_match = re.search(r'\{.*\}', output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _load_goal(self) -> Dict:
        goal_file = self.state_dir / "goal.yaml"
        if goal_file.exists():
            import yaml
            with open(goal_file) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_strategy(self) -> Dict:
        strategy_file = self.state_dir / "strategy.yaml"
        if strategy_file.exists():
            import yaml
            with open(strategy_file) as f:
                return yaml.safe_load(f) or self._default_strategy()
        return self._default_strategy()

    def _load_recent_trades(self, count: int = 25) -> List[Dict]:
        trades_file = self.state_dir / "trades.jsonl"
        if not trades_file.exists():
            return []
        with open(trades_file) as f:
            lines = f.readlines()
        trades = []
        for line in lines[-count:]:
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return trades

    def _mark_trades_reflected(self) -> None:
        """Mark that trades have been reflected on."""
        trades_file = self.state_dir / "trades.jsonl"
        with open(trades_file, "a") as f:
            f.write(json.dumps({"_reflection_marker": True, "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")

    def _default_strategy(self) -> Dict:
        return {
            "version": "01",
            "entry": {"indicator": "rsi", "threshold": 30, "direction": "long"},
            "stop_loss_pct": 2.0,
            "position_size_r": 0.5,
        }
