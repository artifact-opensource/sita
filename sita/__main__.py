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

import os
from pathlib import Path

# Load .env BEFORE any config imports (config reads os.getenv at module level)
_env_path = Path("/home/adam/Projects/sita/.env")
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _v = _v.strip().strip("'\"")
                os.environ.setdefault(_k.strip(), _v)
    print(f"[SITA DOTENV] Loaded .env from {_env_path}")
    print(f"[SITA DOTENV] SITA_TRADING_MODE={os.environ.get('SITA_TRADING_MODE')}")
else:
    print(f"[SITA DOTENV] WARNING: .env not found at {_env_path}")

import sys
import time
import signal
import logging
import argparse
from datetime import datetime, timezone

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
from .arbitrage import ArbitrageEngine

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
    2. Generate signal (8 strategies + fallback)
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

        # Arbitrage engine (spot-futures basis)
        self.arbitrage = ArbitrageEngine(self.config.get("arbitrage", {}))
        if self.executor and self.executor.exchange:
            self.arbitrage.register_exchange("binance", self.executor.exchange)

        # Discord notifier
        self.discord = None
        try:
            from .journal import DiscordNotifier
            import os as _os
            _token = _os.environ.get("DISCORD_BOT_TOKEN", "")
            _webhook = _os.environ.get("DISCORD_WEBHOOK_URL", "")
            _channel = _os.environ.get("DISCORD_CHANNEL_ID", "")
            if _token or _webhook:
                self.discord = DiscordNotifier(
                    token=_token,
                    channels={
                        "alerts": int(_channel) if _channel.isdigit() else None,
                        "signals": int(_channel) if _channel.isdigit() else None,
                        "health": int(_channel) if _channel.isdigit() else None,
                        "journal": int(_channel) if _channel.isdigit() else None,
                        "reports": int(_channel) if _channel.isdigit() else None,
                        "webhook_url": _webhook,
                    },
                )
                logger.info("Discord notifier enabled")
        except Exception as e:
            logger.warning(f"Discord notifier init failed: {e}")

        # Sync existing exchange positions on startup
        self._sync_exchange_positions()

        # Initialize balance
        balance = self.executor.get_balance()
        self.risk_manager.initialize_balances(balance)
        logger.info(f"Balance: {balance:.2f} USDT")

        # Watchlist
        self.watchlist = self.config.get("watchlist", DEFAULT_WATCHLIST)
        self.timeframe = self.config.get("timeframe", "15m")
        self.loop_interval = self.config.get("loop_interval", 60)  # seconds

        logger.info(f"SITA initialized. Mode: {TRADING_MODE}. Watchlist: {self.watchlist}")

        # Discord startup notification
        if self.discord:
            try:
                from .config import DEFAULT_EXCHANGE
                self.discord.post_alert(
                    "🚀 SITA Online",
                    f"v{VERSION} '{CODENAME}' started in **{TRADING_MODE}** mode",
                    color="green",
                    fields={
                        "Exchange": DEFAULT_EXCHANGE,
                        "Balance": f"${balance:.2f} USDT",
                        "Watchlist": ", ".join(self.watchlist),
                        "Timeframe": self.timeframe,
                    },
                )
            except Exception as e:
                logger.warning(f"Discord startup post failed: {e}")

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

        # Scan for arbitrage opportunities (funding rate plays)
        self._scan_arbitrage()

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
            # Track position count per symbol (only after successful order)
            self.risk_manager.state.positions_by_symbol[symbol] = self.risk_manager.state.positions_by_symbol.get(symbol, 0) + 1
            self.risk_manager.state.open_positions += 1
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

            # Discord trade alert
            if self.discord:
                try:
                    self.discord.post_trade(
                        symbol=symbol,
                        side=signal.direction.value,
                        size=risk_decision.position_size,
                        entry=current_price,
                        sl=sl_price,
                        tp=tp_price,
                    )
                except Exception as e:
                    logger.warning(f"Discord trade post failed: {e}")
        else:
            logger.error(f"{symbol}: Order failed — {order.error}")
            if self.discord:
                try:
                    self.discord.post_alert(
                        f"⚠️ Order Failed: {symbol}",
                        f"Error: {order.error}",
                        color="red",
                        fields={"Side": signal.direction.value, "Size": str(risk_decision.position_size)},
                    )
                except Exception as e:
                    logger.warning(f"Discord error post failed: {e}")

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
        # Update risk manager trade count
        self.risk_manager.record_trade_result(result.get("pnl", 0), symbol=pos.symbol)

    def _scan_arbitrage(self):
        """Scan for spot-futures basis opportunities."""
        if not self.arbitrage.exchanges:
            return

        for symbol in ["ETH", "BTC", "SOL"]:
            try:
                opp = self.arbitrage.scan_spot_futures_basis(symbol)
                if opp and opp.is_favorable:
                    logger.info(f"ARB OPPORTUNITY: {symbol} basis={opp.basis_pct:.3f}%, "
                               f"funding={opp.funding_rate:.6f}, est_apy={opp.estimated_apr*100:.1f}%")

                    if self.discord:
                        try:
                            self.discord.post_alert(
                                f"🔄 Arb Opportunity: {symbol}",
                                f"Basis: {opp.basis_pct:.3f}%\n"
                                f"Funding: {opp.funding_rate:.6f} ({opp.estimated_apr*100:.1f}% APY)\n"
                                f"Spot: ${opp.spot_price:.2f} → Futures: ${opp.futures_price:.2f}",
                                color="blue",
                                fields={
                                    "Est. APY": f"{opp.estimated_apr*100:.1f}%",
                                    "Confidence": f"{opp.confidence:.0%}",
                                },
                            )
                        except Exception as e:
                            logger.debug(f"Discord arb alert failed: {e}")
            except Exception as e:
                logger.debug(f"Arb scan failed for {symbol}: {e}")

    def _sync_exchange_positions(self):
        """Sync existing exchange positions into position manager and risk state on startup."""
        if not self.executor or not self.executor.exchange:
            return

        existing = self.executor.sync_positions()
        for pos_info in existing:
            symbol = pos_info["symbol"]
            side = pos_info["side"]
            size = pos_info["size"]
            entry = pos_info["entry_price"]

            # Register in risk manager
            self.risk_manager.state.positions_by_symbol[symbol] = \
                self.risk_manager.state.positions_by_symbol.get(symbol, 0) + 1
            self.risk_manager.state.open_positions += 1

            # Register in position manager
            self.position_manager.open_position(
                symbol=symbol,
                side=side,
                size=size,
                entry_price=entry,
                stop_loss=0,
                take_profit=0,
                order_id="existing",
            )

            logger.info(f"Synced position: {symbol} {side} {size} @ {entry}")

        if existing:
            logger.info(f"Synced {len(existing)} existing position(s) from exchange")

            # Notify Discord
            if self.discord:
                try:
                    pos_lines = []
                    for p in existing:
                        pos_lines.append(
                            f"{p['symbol']} {p['side']} {p['size']} @ ${p['entry_price']:.2f}"
                        )
                    self.discord.post_alert(
                        "🔄 Positions Synced",
                        "Found existing positions on exchange:\n" + "\n".join(pos_lines),
                        color="yellow",
                    )
                except Exception as e:
                    logger.debug(f"Discord sync notification failed: {e}")

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
                "max_daily_loss": "5%",
                "max_weekly_loss": "10%",
                "max_total_dd": "20%",
                "max_risk_per_trade": "1%",
                "max_positions": 1,
                "max_leverage": 10,
            },
        }


def load_dotenv():
    """Load .env file from project root into os.environ."""
    try:
        env_path = Path("/home/adam/Projects/sita/.env")
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        v = v.strip().strip("'\"")
                        import os
                        os.environ.setdefault(k.strip(), v)
            print(f"[dotenv] Loaded {env_path}")
    except Exception as e:
        print(f"[dotenv] Warning: {e}")


def main():
    load_dotenv()
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
