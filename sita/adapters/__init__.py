"""
SITA — Backtesting Engine
Test strategies against historical data before deploying to paper/live.

Features:
- Walk-forward backtesting
- Multi-strategy comparison
- Confluence filter integration
- Risk management simulation
- Performance metrics (Sharpe, drawdown, win rate, profit factor)
"""

from __future__ import annotations
import json
import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import STATE_DIR
from ..signal import StrategySelector
from ..confluence import EntryConfluenceFilter
from ..risk import UnifiedRiskManager, RiskLimits
from ..position import PositionManager

logger = logging.getLogger("sita.backtest")


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.01
    commission_pct: float = 0.001  # 0.1% per trade (taker fee)
    slippage_pct: float = 0.0005   # 0.05% slippage
    timeframe: str = "15m"
    lookback_bars: int = 200       # Bars needed before first signal
    warmup_bars: int = 50         # Bars for indicator warmup


@dataclass
class BacktestTrade:
    """A trade recorded during backtesting."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    entry_bar: int
    exit_bar: int
    exit_reason: str       # tp_hit, sl_hit, signal_reverse, end_of_data
    strategy: str
    confluence_score: float
    hold_bars: int = 0


@dataclass
class BacktestResult:
    """Complete backtest results."""
    config: Dict
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.pnl > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.pnl <= 0)

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0

    @property
    def total_pnl(self) -> float:
        return sum(t.pnl for t in self.trades)

    @property
    def total_pnl_pct(self) -> float:
        return self.total_pnl / self.config.get("initial_balance", 10000)

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.total_trades if self.total_trades > 0 else 0

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0
        peak = self.equity_curve[0]
        max_dd = 0
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        if len(self.equity_curve) < 2:
            return 0
        returns = np.diff(self.equity_curve) / np.array(self.equity_curve[:-1])
        if np.std(returns) == 0:
            return 0
        return float(np.mean(returns) / np.std(returns) * np.sqrt(252 * 96))  # Annualized for 15m

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float("inf")

    @property
    def avg_hold_bars(self) -> float:
        return np.mean([t.hold_bars for t in self.trades]) if self.trades else 0

    @property
    def avg_confluence(self) -> float:
        return np.mean([t.confluence_score for t in self.trades]) if self.trades else 0

    def summary(self) -> Dict:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": f"{self.win_rate:.1%}",
            "total_pnl": f"${self.total_pnl:.2f}",
            "total_pnl_pct": f"{self.total_pnl_pct:.1%}",
            "avg_pnl": f"${self.avg_pnl:.2f}",
            "max_drawdown": f"{self.max_drawdown_pct:.1%}",
            "sharpe": f"{self.sharpe_ratio:.2f}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "avg_hold_bars": f"{self.avg_hold_bars:.0f}",
            "avg_confluence": f"{self.avg_confluence:.0f}",
        }

    def save(self, path: str = None):
        """Save results to file."""
        if path is None:
            path = STATE_DIR / f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        data = {
            "config": self.config,
            "summary": self.summary(),
            "trades": [
                {
                    "symbol": t.symbol,
                    "side": t.side,
                    "entry": t.entry_price,
                    "exit": t.exit_price,
                    "pnl": t.pnl,
                    "reason": t.exit_reason,
                    "strategy": t.strategy,
                    "confluence": t.confluence_score,
                }
                for t in self.trades
            ],
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Backtest results saved to {path}")


class BacktestEngine:
    """
    Walk-forward backtesting engine.

    Simulates the full SITA pipeline on historical data:
    Signal → Confluence → Risk → Position Management
    """

    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.signal_engine = StrategySelector()
        self.confluence_filter = EntryConfluenceFilter()
        self.risk_manager = UnifiedRiskManager(limits=RiskLimits(
            max_risk_per_trade_pct=self.config.risk_per_trade,
            max_positions=5,
        ))
        self.position_manager = PositionManager()

    def run(self, ohlcv: pd.DataFrame, symbol: str = "BTC/USDT") -> BacktestResult:
        """
        Run backtest on historical OHLCV data.

        Args:
            ohlcv: DataFrame with columns [timestamp, open, high, low, close, volume]
            symbol: Trading symbol

        Returns:
            BacktestResult with full performance metrics
        """
        result = BacktestResult(config={
            "initial_balance": self.config.initial_balance,
            "risk_per_trade": self.config.risk_per_trade,
            "commission_pct": self.config.commission_pct,
            "slippage_pct": self.config.slippage_pct,
            "symbol": symbol,
            "bars": len(ohlcv),
        })

        balance = self.config.initial_balance
        self.risk_manager.initialize_balances(balance)
        equity_curve = [balance]

        open_position = None

        for i in range(self.config.warmup_bars, len(ohlcv)):
            # Current bar data
            current_bar = ohlcv.iloc[i]
            current_price = current_bar["close"]
            high = current_bar["high"]
            low = current_bar["low"]

            # Historical data up to this point
            hist = ohlcv.iloc[:i + 1]

            # ─── Manage open position ──────────────────────────────────
            if open_position:
                # Check SL/TP
                exit_price = None
                exit_reason = None

                if open_position["side"] == "long":
                    if low <= open_position["sl"]:
                        exit_price = open_position["sl"]
                        exit_reason = "sl_hit"
                    elif high >= open_position["tp"]:
                        exit_price = open_position["tp"]
                        exit_reason = "tp_hit"
                else:  # short
                    if high >= open_position["sl"]:
                        exit_price = open_position["sl"]
                        exit_reason = "sl_hit"
                    elif low <= open_position["tp"]:
                        exit_price = open_position["tp"]
                        exit_reason = "tp_hit"

                if exit_price:
                    # Close position
                    if open_position["side"] == "long":
                        pnl = (exit_price - open_position["entry"]) * open_position["size"]
                    else:
                        pnl = (open_position["entry"] - exit_price) * open_position["size"]

                    # Apply commission
                    commission = (open_position["entry"] + exit_price) * open_position["size"] * self.config.commission_pct
                    pnl -= commission

                    balance += pnl
                    self.risk_manager.update_balance(balance)

                    result.trades.append(BacktestTrade(
                        symbol=symbol,
                        side=open_position["side"],
                        entry_price=open_position["entry"],
                        exit_price=exit_price,
                        size=open_position["size"],
                        pnl=pnl,
                        pnl_pct=pnl / balance * 100,
                        entry_bar=open_position["bar"],
                        exit_bar=i,
                        exit_reason=exit_reason,
                        strategy=open_position["strategy"],
                        confluence_score=open_position["confluence"],
                        hold_bars=i - open_position["bar"],
                    ))

                    open_position = None
                else:
                    # Update trailing / BE
                    self._update_position_in_backtest(open_position, high, low, current_price)

            # ─── Generate signal ───────────────────────────────────────
            if not open_position:
                signal = self.signal_engine.generate_signal(hist, symbol)

                if signal.primary.has_signal:
                    # Confluence filter
                    atr = self._compute_atr(hist)
                    confluence = self.confluence_filter.analyze_entry(
                        signal_direction=signal.direction.value,
                        current_price=current_price,
                        symbol=symbol,
                        ohlcv=hist,
                        atr=atr,
                    )

                    if confluence.should_enter and confluence.position_mult > 0:
                        # Risk check
                        sl_price = self.risk_manager.calculate_stop_loss(
                            signal.direction.value, current_price, atr
                        )
                        tp_price = self.risk_manager.calculate_take_profit(
                            signal.direction.value, current_price, sl_price
                        )

                        risk_decision = self.risk_manager.approve_trade(
                            symbol=symbol,
                            direction=signal.direction.value,
                            entry_price=current_price,
                            stop_loss_price=sl_price,
                            take_profit_price=tp_price,
                            balance=balance,
                            confluence_mult=confluence.position_mult,
                        )

                        if risk_decision.action.value == "approved":
                            # Apply slippage
                            if signal.direction.value == "long":
                                entry_price = current_price * (1 + self.config.slippage_pct)
                            else:
                                entry_price = current_price * (1 - self.config.slippage_pct)

                            open_position = {
                                "side": signal.direction.value,
                                "entry": entry_price,
                                "sl": sl_price,
                                "tp": tp_price,
                                "size": risk_decision.position_size,
                                "strategy": signal.strategy_name,
                                "confluence": confluence.score,
                                "bar": i,
                                "highest": entry_price,
                                "lowest": entry_price,
                            }

            # Record equity
            equity_curve.append(balance)

        # Close any open position at end
        if open_position:
            final_price = ohlcv["close"].iloc[-1]
            if open_position["side"] == "long":
                pnl = (final_price - open_position["entry"]) * open_position["size"]
            else:
                pnl = (open_position["entry"] - final_price) * open_position["size"]
            balance += pnl
            result.trades.append(BacktestTrade(
                symbol=symbol,
                side=open_position["side"],
                entry_price=open_position["entry"],
                exit_price=final_price,
                size=open_position["size"],
                pnl=pnl,
                pnl_pct=pnl / balance * 100,
                entry_bar=open_position["bar"],
                exit_bar=len(ohlcv) - 1,
                exit_reason="end_of_data",
                strategy=open_position["strategy"],
                confluence_score=open_position["confluence"],
                hold_bars=len(ohlcv) - 1 - open_position["bar"],
            ))

        result.equity_curve = equity_curve

        logger.info(f"Backtest complete: {result.total_trades} trades, "
                     f"WR={result.win_rate:.0%}, PnL=${result.total_pnl:.2f}, "
                     f"Sharpe={result.sharpe_ratio:.2f}, MaxDD={result.max_drawdown_pct:.1%}")

        return result

    def _update_position_in_backtest(self, pos: Dict, high: float, low: float, close: float):
        """Update position with trailing stop and break-even during backtest."""
        if pos["side"] == "long":
            if high > pos["highest"]:
                pos["highest"] = high
            if low < pos["lowest"]:
                pos["lowest"] = low

            # Break-even at 1R profit
            risk = pos["entry"] - pos["sl"]
            if close >= pos["entry"] + risk:
                new_be = pos["entry"] * 1.001
                if new_be > pos["sl"]:
                    pos["sl"] = new_be

            # Trailing at 1.5R
            if close >= pos["entry"] + risk * 1.5:
                trail = pos["highest"] - risk * 0.5
                if trail > pos["sl"]:
                    pos["sl"] = trail

        else:  # short
            if low < pos["lowest"]:
                pos["lowest"] = low
            if high > pos["highest"]:
                pos["highest"] = high

            risk = pos["sl"] - pos["entry"]
            if close <= pos["entry"] - risk:
                new_be = pos["entry"] * 0.999
                if new_be < pos["sl"]:
                    pos["sl"] = new_be

            if close <= pos["entry"] - risk * 1.5:
                trail = pos["lowest"] + risk * 0.5
                if trail < pos["sl"]:
                    pos["sl"] = trail

    def _compute_atr(self, ohlcv: pd.DataFrame, period: int = 14) -> float:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])
