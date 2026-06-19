#!/usr/bin/env python3
"""SITA launcher — loads .env then runs the trading engine."""
import os
import sys

# ── Load .env BEFORE any sita imports ──────────────────────────────────────
env_path = "/home/adam/Projects/sita/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                v = v.strip().strip("'\"")
                os.environ.setdefault(k.strip(), v)
    print(f"[launcher] Loaded .env — SITA_TRADING_MODE={os.environ.get('SITA_TRADING_MODE')}")
else:
    print(f"[launcher] WARNING: .env not found at {env_path}")

# ── Ensure project is on path ──────────────────────────────────────────────
sys.path.insert(0, "/home/adam/Projects/sita")

# ── Clear any stale .pyc for __main__ ──────────────────────────────────────
pyc_path = "/home/adam/Projects/sita/sita/__pycache__/__main__.cpython-313.pyc"
if os.path.exists(pyc_path):
    os.remove(pyc_path)
    print(f"[launcher] Removed stale .pyc")

# ── Run SITA ───────────────────────────────────────────────────────────────
from sita.__main__ import main
main()
