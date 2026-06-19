#!/bin/bash
# SITA Live Launcher
# Loads .env and starts the trading engine

set -a
source /home/adam/Projects/sita/config/.env
set +a

cd /home/adam/Projects/sita

echo "============================================"
echo "  SITA v1.0.0 — Self-Improving Trading Agent"
echo "  MODE: $SITA_TRADING_MODE"
echo "  EXCHANGE: $SITA_EXCHANGE"
echo "  RISK ACCEPTED: $SITA_I_ACCEPT_RISK"
echo "============================================"
echo ""

python3 -m sita run
