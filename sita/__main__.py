"""
SITA — Self-Improving Trading Agent
Main entry point.

Usage:
    python -m sita run                  # Run the trading loop
    python -m sita reflect --fallback   # Force a reflection cycle
    python -m sita reflect --hermes     # Hermes-powered reflection
    python -m sita status               # Show current status
    python -m sita backtest             # Run backtest
"""

import sys
import time
import signal
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    LOG_FILE, LOG_FORMAT, LOG_LEVEL, STATE_DIR, TRADING_MODE,
    DEFAULT_WATCHLIST, VERSION, CODENAME,
)
from .signal import StrategySelector
from .confluence import EntryConfluenceFilter
from .risk import UnifiedRiskManager
from .execution import ExchangeExecutor
from .position import PositionManager
from .reflection import ReflectionEngine
from .regime import RegimeDetector, LiquidityAnalyzer

# ─── Logging Setup ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("sita")


class SITA:
    """
    Self-Improving Trading Agent.

    Loop:
    1. Fetch OHLCV data for each symbol
    2. Generate signal (7 strategies + fallback)
    3. Score confluence (9-dimension quality gate)
    4. Risk check (position sizing, limits)
    5. Execute (paper or live)
    6. Manage positions (BE, trailing, profit profiling)
    7. Every N trades: reflect and evolve strategy
    """

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.running = False

        # Initialize components
        logger.info(f"Initializing SITA v{VERSION} '{CODENAME}'...")

        self.executor = ExchangeExecutor(
            exchange_id=self.config.get("exchange"),
            config=self.config,
        )

        self.signal_engine = StrategySelector(self.config.get("signal", {}))
        self.confluence_filter = EntryConfluenceFilter(self.config.get("confluence", {}))
        self.risk_manager = UnifiedRiskManager(self.config.get("risk", {}))
        self.position_manager = PositionManager(self.config.get("position", {}))
        self.reflection = ReflectionEngine(self.config.get("reflection", {}))
        self.regime_detector = RegimeDetector(self.config.get("regime", {}))
        self.liquidity_analyzer = LiquidityAnalyzer(self.config.get("liquidity", {}))

        # Initialize balance
        balance = self.executor.get_balance()
        self.risk_manager.initialize_balances(balance)
        logger.info(f"Balance: {balance:.2f} USDT")

        # Watchlist
        self.watchlist = self.config.get("watchlist", DEFAULT_WATCHLIST)
        self.timeframe = self.config.get("timeframe", "15m")
        self.loop_interval = self.config.get("loop_interval", 60)  # seconds

        logger.info(f"SITA initialized. Mode: {TRADING_MODE}. Watchlist: {self.watchlist}")

    def run(self):
        """Main trading loop."""
        self.running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("=" * 60)
        logger.info(f"  SITA v{VERSION} '{CODENAME}' — Starting trading loop")
        logger.info(f"  Mode: {TRADING_MODE} | Interval: {self.loop_interval}s")
        logger.info("=" * 60)

        cycle = 0
        while self.running:
            cycle += 1
            logger.info(f"─── Cycle {cycle} ───")

            try:
                self._trading_cycle(cycle)
            except Exception as e:
                logger.error(f"Cycle {cycle} error: {e}", exc_info=True)

            # Check if it's time to reflect
            if self.reflection.should_reflect():
                logger.info("Time to reflect!")
                result = self.reflection.reflect_fallback()
                logger.info(f"Reflection result: {result}")

            # Wait for next cycle
            logger.info(f"Sleeping {self.loop_interval}s...")
            time.sleep(self.loop_interval)

    def _trading_cycle(self, cycle: int):
        """Single trading cycle."""
        # Update balance
        balance = self.executor.get_balance()
        self.risk_manager.update_balance(balance)

        # Check each symbol
        for symbol in self.watchlist:
            self._process_symbol(symbol, balance)

        # Update existing positions
        self._manage_positions()

    def _process_symbol(self, symbol: str, balance: float):
        """Process a single symbol with regime awareness."""
        # Fetch data
        ohlcv_data = self.executor.get_ohlcv(symbol, self.timeframe, limit=200)
        if not ohlcv_data:
            logger.warning(f"No data for {symbol}")
            return

        import pandas as pd
        ohlcv = pd.DataFrame(ohlcv_data)
        ohlcv["timestamp"] = pd.to_datetime(ohlcv["timestamp"], unit="ms")

        current_price = ohlcv["close"].iloc[-1]

        # ─── 0. Regime Detection ────────────────────────────────────────
        regime = self.regime_detector.detect(ohlcv)
        logger.info(f"{symbol}: Regime={regime.regime.value} ({regime.confidence.value}), "
                     f"ADX={regime.adx}, RSI={regime.rsi}, Trend={regime.trend_direction}")
        logger.info(f"{symbol}: Strategy recommendation: {regime.strategy_recommendation}")

        # ─── 0b. Liquidity Analysis ──────────────────────────────────────
        liquidity = self.liquidity_analyzer.analyze(ohlcv, current_price)
        if liquidity.zones:
            logger.info(f"{symbol}: {len(liquidity.zones)} liquidity zones, bias={liquidity.liquidity_bias}")
            if liquidity.nearest_liquidity_above:
                logger.info(f"{symbol}: Nearest liquidity above: {liquidity.nearest_liquidity_above}")
            if liquidity.nearest_liquidity_below:
                logger.info(f"{symbol}: Nearest liquidity below: {liquidity.nearest_liquidity_below}")

        # Check if symbol is disabled
        strategy_state = self.reflection._load_strategy()
        disabled_symbols = strategy_state.get("disabled_symbols", [])
        if symbol in disabled_symbols:
            logger.info(f"{symbol}: Disabled by reflection — skipping")
            return

        # Skip if regime confidence is low
        if regime.confidence.value == "low":
            logger.info(f"{symbol}: Low regime confidence — skipping")
            return

        # ─── 1. Generate signal (regime-aware) ──────────────────────────
        signal = self.signal_engine.generate_signal(ohlcv, symbol)

        if not signal.primary.has_signal:
            logger.debug(f"{symbol}: No signal")
            return

        # Regime filter: check if signal direction matches regime
        if regime.regime.value == "trending_strong" and signal.direction.value == "short" and regime.trend_direction == "up":
            logger.info(f"{symbol}: Filtered — short signal in strong uptrend")
            return
        if regime.regime.value == "trending_strong" and signal.direction.value == "long" and regime.trend_direction == "down":
            logger.info(f"{symbol}: Filtered — long signal in strong downtrend")
            return

        logger.info(f"{symbol}: {signal.primary.summary}")

        # ─── 2. Confluence filter ───────────────────────────────────────
        atr = self._compute_atr(ohlcv)
        confluence = self.confluence_filter.analyze_entry(
            signal_direction=signal.direction.value,
            current_price=current_price,
            symbol=symbol,
            ohlcv=ohlcv,
            atr=atr,
        )

        logger.info(f"{symbol}: {confluence.summary}")

        if not confluence.should_enter:
            logger.info(f"{symbol}: Entry rejected by confluence filter")
            return

        # ─── 3. Risk check ──────────────────────────────────────────────
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

        if risk_decision.action.value in ("rejected", "locked"):
            logger.info(f"{symbol}: Risk rejected — {risk_decision.reasons}")
            return

        logger.info(f"{symbol}: Risk approved — size={risk_decision.position_size}, SL={sl_price}, TP={tp_price}")

        # ─── 4. Execute ─────────────────────────────────────────────────
        order = self.executor.place_order(
            symbol=symbol,
            side="buy" if signal.direction.value == "long" else "sell",
            size=risk_decision.position_size,
            stop_loss=sl_price,
            take_profit=tp_price,
        )

        if order.success:
            self.position_manager.open_position(
                symbol=symbol,
                side=signal.direction.value,
                size=risk_decision.position_size,
                entry_price=current_price,
                stop_loss=sl_price,
                take_profit=tp_price,
                order_id=order.order_id,
            )
            logger.info(f"{symbol}: Order placed — {order.order_id}")
        else:
            logger.error(f"{symbol}: Order failed — {order.error}")

    def _manage_positions(self):
        """Update and manage open positions."""
        for symbol, pos in self.position_manager.get_open_positions().items():
            current_price = self.executor.get_current_price(symbol)
            if current_price <= 0:
                continue

            atr = 0  # Could compute from recent data
            result = self.position_manager.update_position(symbol, current_price, atr)

            if result["action"] == "close":
                order = self.executor.close_position(symbol)
                if order.success:
                    self._record_trade(pos, result)
            elif result["action"] == "partial_close":
                logger.info(f"{symbol}: Partial close — {result['reason']}")

    def _record_trade(self, pos, result):
        """Record a closed trade."""
        import json
        trades_file = STATE_DIR / "trades.jsonl"
        with open(trades_file, "a") as f:
            f.write(json.dumps({
                "symbol": pos.symbol,
                "side": pos.side,
                "entry_price": pos.entry_price,
                "close_price": result.get("price", 0),
                "size": pos.size,
                "pnl": result.get("pnl", 0),
                "reason": result.get("reason", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }) + "\n")

    def _compute_atr(self, ohlcv: "pd.DataFrame", period: int = 14) -> float:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        import pandas as pd
        import numpy as np
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return float(tr.rolling(period).mean().iloc[-1])

    def _signal_handler(self, signum, frame):
        logger.info("Shutdown signal received")
        self.running = False

    def status(self) -> dict:
        """Get current status."""
        positions = self.position_manager.get_open_positions()
        stats = self.position_manager.get_stats()
        return {
            "version": VERSION,
            "codename": CODENAME,
            "mode": TRADING_MODE,
            "balance": self.executor.get_balance(),
            "open_positions": len(positions),
            "positions": {s: {"side": p.side, "size": p.size, "entry": p.entry_price, "sl": p.stop_loss, "tp": p.take_profit} for s, p in positions.items()},
            "stats": stats,
            "risk_limits": {
                "max_daily_loss": "1.5%",
                "max_weekly_loss": "3%",
                "max_total_dd": "5%",
                "max_risk_per_trade": "0.5%",
                "max_positions": 3,
                "recovery_threshold": "3%",
            },
        }


def main():
    parser = argparse.ArgumentParser(description="SITA — Self-Improving Trading Agent")
    subparsers = parser.add_subparsers(dest="command")

    # Run
    run_parser = subparsers.add_parser("run", help="Run the trading loop")
    run_parser.add_argument("--exchange", default=None, help="Exchange ID (binance, bybit, etc.)")
    run_parser.add_argument("--timeframe", default="15m", help="Trading timeframe")
    run_parser.add_argument("--interval", type=int, default=60, help="Loop interval in seconds")

    # Reflect
    reflect_parser = subparsers.add_parser("reflect", help="Force a reflection cycle")
    reflect_parser.add_argument("--fallback", action="store_true", help="Use deterministic fallback")
    reflect_parser.add_argument("--hermes", action="store_true", help="Use Hermes LLM")

    # Dashboard
    dashboard_parser = subparsers.add_parser("dashboard", help="Start the web dashboard")
    dashboard_parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    dashboard_parser.add_argument("--port", type=int, default=8090, help="Bind port")

    # Setup
    subparsers.add_parser("setup", help="Interactive setup wizard")

    # Status
    subparsers.add_parser("status", help="Show current status")

    args = parser.parse_args()

    config = {
        "exchange": getattr(args, "exchange", None),
        "timeframe": getattr(args, "timeframe", "15m"),
        "loop_interval": getattr(args, "interval", 60),
    }

    sita = SITA(config)

    if args.command == "run":
        sita.run()
    elif args.command == "dashboard":
        from dashboard.server import run_dashboard
        run_dashboard(host=args.host, port=args.port)
    elif args.command == "setup":
        from .setup import run_setup
        run_setup()
    elif args.command == "reflect":
        if args.hermes:
            result = sita.reflection.reflect_hermes()
        else:
            result = sita.reflection.reflect_fallback()
        print(result)
    elif args.command == "status":
        import json
        print(json.dumps(sita.status(), indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
