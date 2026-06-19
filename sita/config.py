"""
SITA — Self-Improving Trading Agent
Configuration & Constants

Linux-native trading system. No MT5. No Wine. No Windows.
Direct exchange execution via ccxt.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path

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

SUPPORTED_EXCHANGES = {
    "binance": {
        "name": "Binance",
        "paper_trading": True,  # testnet available
        "testnet_url": "https://testnet.binance.vision",
        "default_type": "future",  # futures for leverage
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"],
    },
    "bybit": {
        "name": "Bybit",
        "paper_trading": True,
        "testnet_url": "https://api-testnet.bybit.com",
        "default_type": "linear",
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
    },
    "okx": {
        "name": "OKX",
        "paper_trading": True,
        "testnet_url": "https://www.okx.com",
        "default_type": "swap",
        "timeframes": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
    },
    "kraken": {
        "name": "Kraken",
        "paper_trading": False,
        "default_type": "spot",
        "timeframes": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"],
    },
}

# ─── Default Watchlist ─────────────────────────────────────────────────────

DEFAULT_WATCHLIST = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
]

# ─── Confluence Scoring Weights ────────────────────────────────────────────
# Must sum to 1.0

CONFLUENCE_WEIGHTS = {
    "level": 0.18,       # Proximity to S/R, round numbers, EMAs
    "momentum": 0.15,    # Momentum alignment with entry
    "timing": 0.10,      # Entry timing quality
    "structure": 0.08,   # Market structure alignment
    "trend": 0.17,       # Macro trend alignment
    "bos": 0.12,         # Break of Structure / ChoCH
    "order_block": 0.12, # ICT Order Block confluence
    "session_orb": 0.08, # Session Opening Range Breakout
}

# ─── Entry Quality Thresholds ──────────────────────────────────────────────

ENTRY_THRESHOLDS = {
    "premium": 85,   # Full position size
    "good": 70,      # 85% position size
    "marginal": 50,  # 60% position size
    "poor": 20,      # 30% position size
    "reject": 0,     # No trade
}

# ─── Position Size Multipliers ─────────────────────────────────────────────

POSITION_MULTIPLIERS = {
    "premium": 1.0,
    "good": 0.85,
    "marginal": 0.6,
    "poor": 0.3,
    "reject": 0.0,
}

# ─── Risk Defaults ─────────────────────────────────────────────────────────

DEFAULT_RISK_LIMITS = {
    "max_daily_loss_pct": 0.03,         # 3% daily loss limit ($0.30 on $10)
    "max_weekly_loss_pct": 0.05,        # 5% weekly loss limit ($0.50 on $10)
    "max_total_loss_pct": 0.10,         # 10% total DD limit ($1.00 kill switch)
    "max_risk_per_trade_pct": 0.01,     # 1% risk per trade ($0.10 on $10)
    "max_positions": 1,                 # Max 1 concurrent position (focused)
    "max_positions_per_symbol": 1,      # Max 1 per symbol (no doubling up)
    "recovery_mode_threshold": 0.05,    # Enter recovery at 5% DD
    "recovery_mode_risk_mult": 0.5,     # 50% risk in recovery
    "min_lot": 0.001,
}

# ─── Balance-Based Risk Categories ──────────────────────────────────────────

BALANCE_BREAKPOINTS = [1000.0, 5000.0, 20000.0]

RISK_BY_CATEGORY = {
    "tiny": 0.005,    # 0.5% for accounts <= $1,000
    "small": 0.01,    # 1% for accounts <= $5,000
    "medium": 0.015,  # 1.5% for accounts <= $20,000
    "large": 0.02,    # 2% for accounts > $20,000
}

# ─── Reflection Defaults ───────────────────────────────────────────────────

DEFAULT_REFLECTION_EVERY = 5  # Reflect every N closed trades
ONE_VARIABLE_ONLY = True      # Scientific method: change 1 var per cycle

# ─── Data Adapter Defaults ─────────────────────────────────────────────────

# Free public endpoints (no API key needed)
FREE_DATA_SOURCES = {
    "price": "ccxt_ohlcv",       # OHLCV from exchange via ccxt
    "onchain": "coingecko",       # Free on-chain data
    "news": "cryptopanic",        # Free tier
    "macro": "tradingview",       # Free indicators
}

# Premium overrides (require API keys)
PREMIUM_DATA_SOURCES = {
    "onchain": "glassnode",
    "news": "newsapi",
    "macro": "fred",
}

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
