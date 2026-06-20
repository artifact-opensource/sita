"""
SITA — Self-Improving Trading Agent
Linux-native. No MT5. No Wine. No Banks needed.

Modules:
    config      — Configuration, constants, exchange settings
    signal      — 7 strategies + multi-strategy fallback
    confluence  — 9-dimension entry quality gate
    risk        — Unified risk management (position sizing, SL/TP, limits)
    execution   — Direct exchange execution via ccxt
    position    — Dynamic BE, trailing stops, profit profiling
    reflection  — Self-improvement loop (fallback + Hermes LLM)
    journal     — Discord notifications and reporting
    adapters    — Backtesting engine
"""

import os
from pathlib import Path

# Load .env BEFORE config import (config reads os.getenv at module level)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _v = _v.strip().strip("'\"")
                os.environ.setdefault(_k.strip(), _v)

from .config import VERSION, CODENAME

__version__ = VERSION
__codename__ = CODENAME
