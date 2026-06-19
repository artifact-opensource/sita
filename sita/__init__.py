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

from .config import VERSION, CODENAME

__version__ = VERSION
__codename__ = CODENAME
