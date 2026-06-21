"""
SITA — Self-Improving Trading Agent
Configuration & Constants

Linux-native trading system. No MT5. No Wine. No Windows.
Direct exchange execution via ccxt.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Mapping
from pathlib import Path
from types import MappingProxyType

# ─── Paths ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(os.getenv("SITA_BASE_DIR", str(Path.home() / "Projects" / "sita")))
STATE_DIR = BASE_DIR / "state"
HISTORY_DIR = STATE_DIR / "history"
LOG_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"

for d in [STATE_DIR, HISTORY_DIR, LOG_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── Version ─────────────────────────────────────────────────────────────────

VERSION = "1.0.0"
CODENAME = "APEX"

# ─── Exchange Configuration ─────────────────────────────────────────────────

# Default exchange — ccxt exchange ID
DEFAULT_EXCHANGE = os.getenv("SITA_EXCHANGE", "binance")

# Trading mode
TRADING_MODE = os.getenv("SITA_TRADING_MODE", "paper")  # paper | live

# Risk acceptance flag (required for live trading)
I_ACCEPT_RISK = os.getenv("SITA_I_ACCEPT_RISK", "false").lower() == "true"

# ─── Supported Exchanges ─────────────────────────────────────────────────────

SUPPORTED_EXCHANGES: Mapping[str, Mapping] = MappingProxyType({
    "binance": MappingProxyType({
        "name": "Binance",
        "paper_trading": True,
        "testnet_url": "https://testnet.binance.vision",
        "default_type": "future",
        "timeframes": ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"),
        "min_notional": 5.0,    # Binance futures minimum notional
    }),
    "bybit": MappingProxyType({
        "name": "Bybit",
        "paper_trading": True,
        "testnet_url": "https://api-testnet.bybit.com",
        "default_type": "linear",
        "timeframes": ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"),
    }),
    "okx": MappingProxyType({
        "name": "OKX",
        "paper_trading": True,
        "testnet_url": "https://www.okx.com",
        "default_type": "swap",
        "timeframes": ("1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"),
    }),
    "kraken": MappingProxyType({
        "name": "Kraken",
        "paper_trading": False,
        "default_type": "spot",
        "timeframes": ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"),
    }),
})

# ─── Default Watchlist ─────────────────────────────────────────────────────

DEFAULT_WATCHLIST = (
    "SOL/USDT:USDT",       # SOL futures — $5 min notional
    "BNB/USDT:USDT",       # BNB futures — $5 min notional
    "XRP/USDT:USDT",       # XRP futures — $5 min notional
    "DOGE/USDT:USDT",      # DOGE futures — $5 min notional
    "ADA/USDT:USDT",       # ADA futures — $5 min notional
    "AVAX/USDT:USDT",      # AVAX futures — $5 min notional
    "DOT/USDT:USDT",       # DOT futures — $5 min notional
)

# ─── Confluence Scoring Weights ────────────────────────────────────────────
# Must sum to 1.0

CONFLUENCE_WEIGHTS: Mapping[str, float] = MappingProxyType({
    "level": 0.18,
    "momentum": 0.15,
    "timing": 0.10,
    "structure": 0.08,
    "trend": 0.17,
    "bos": 0.12,
    "order_block": 0.12,
    "session_orb": 0.08,
})

# ─── Entry Quality Thresholds ──────────────────────────────────────────────

ENTRY_THRESHOLDS: Mapping[str, int] = MappingProxyType({
    "premium": 80,
    "good": 55,
    "marginal": 40,
    "poor": 20,
    "reject": 0,
})

# ─── Position Size Multipliers ─────────────────────────────────────────────

POSITION_MULTIPLIERS: Mapping[str, float] = MappingProxyType({
    "premium": 1.0,
    "good": 0.85,
    "marginal": 0.75,
    "poor": 0.5,
    "reject": 0.0,
})

# ─── Risk Defaults ─────────────────────────────────────────────────────────

DEFAULT_RISK_LIMITS: Mapping[str, float] = MappingProxyType({
    "max_daily_loss_pct": 0.10,
    "max_weekly_loss_pct": 0.15,
    "max_total_loss_pct": 0.25,
    "max_risk_per_trade_pct": 0.02,
    "max_positions": 10,       # Dynamic: overridden by _get_max_positions()
    "max_positions_per_symbol": 5,
    "recovery_mode_threshold": 0.15,
    "recovery_mode_risk_mult": 0.75,
    "min_lot": 0.001,
    "min_notional": 0.01,
    "max_leverage": 10,
    "max_position_pct": 0.50,
})

# ─── Balance-Based Risk Categories ──────────────────────────────────────────

BALANCE_BREAKPOINTS = (1000.0, 5000.0, 20000.0)

RISK_BY_CATEGORY: Mapping[str, float] = MappingProxyType({
    "tiny": 0.02,
    "small": 0.02,
    "medium": 0.015,
    "large": 0.02,
})

# ─── Reflection Defaults ───────────────────────────────────────────────────

DEFAULT_REFLECTION_EVERY = 5  # Reflect every N closed trades
ONE_VARIABLE_ONLY = True      # Scientific method: change 1 var per cycle

# ─── Data Adapter Defaults ─────────────────────────────────────────────────

# Free public endpoints (no API key needed)
FREE_DATA_SOURCES: Mapping[str, str] = MappingProxyType({
    "price": "ccxt_ohlcv",
    "onchain": "coingecko",
    "news": "cryptopanic",
    "macro": "tradingview",
})

# Premium overrides (require API keys)
PREMIUM_DATA_SOURCES: Mapping[str, str] = MappingProxyType({
    "onchain": "glassnode",
    "news": "newsapi",
    "macro": "fred",
})

# ─── Arbitrage Configuration ────────────────────────────────────────────────

ARBITRAGE_ENABLED = os.getenv("SITA_ARBITRAGE_ENABLED", "true").lower() == "true"
ARBITRAGE_MIN_BASIS_PCT = float(os.getenv("SITA_ARBITRAGE_MIN_BASIS", "0.05"))  # 0.05% min basis
ARBITRAGE_MIN_FUNDING_RATE = float(os.getenv("SITA_ARBITRAGE_MIN_FUNDING", "0.00005"))  # 0.005% per 8h
ARBITRAGE_FEE_PCT = float(os.getenv("SITA_ARBITRAGE_FEE", "0.001"))  # 0.1% per trade

# ─── Logging ────────────────────────────────────────────────────────────────

LOG_LEVEL = os.getenv("SITA_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_FILE = LOG_DIR / "sita.log"

# ─── Railway Deployment ────────────────────────────────────────────────────

RAILWAY_ENV_VARS = [
    "SITA_EXCHANGE",
    "SITA_TRADING_MODE",
    "SITA_I_ACCEPT_RISK",
    "EXCHANGE_API_KEY",
    "EXCHANGE_API_SECRET",
]
