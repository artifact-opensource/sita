#!/usr/bin/env python3
"""SITA Live Launcher — sets env vars then runs the trading engine."""
import os
import sys

# ── 1. Read .env file directly ────────────────────────────────────────────
ENV_PATH = "/home/adam/Projects/sita/.env"
with open(ENV_PATH) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            v = v.strip().strip("'\"")
            os.environ.setdefault(k.strip(), v)

# ── 2. Remove stale .pyc for __main__ ─────────────────────────────────────
import pathlib
pyc = pathlib.Path("/home/adam/Projects/sita/sita/__pycache__/__main__.cpython-313.pyc")
if pyc.exists():
    pyc.unlink()

# ── 3. Verify ─────────────────────────────────────────────────────────────
assert os.environ.get("SITA_TRADING_MODE") == "live", f"TRADING_MODE={os.environ.get('SITA_TRADING_MODE')}"
assert os.environ.get("BINANCE_API_KEY"), "BINANCE_API_KEY not set"
print(f"[launcher] OK — mode=live, exchange=binance, key={os.environ['BINANCE_API_KEY'][:8]}...")

# ── 4. Run SITA ───────────────────────────────────────────────────────────
sys.path.insert(0, "/home/adam/Projects/sita")
sys.argv = ["sita", "run"]  # force 'run' subcommand
from sita.__main__ import main
main()
