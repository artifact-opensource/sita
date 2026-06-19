# Self-Improving Trading Agent
> Codename: SITA 🔱

**Linux-native. No MT5. No Wine. No Banks needed.**

SITA is a self-improving trading agent that runs on Linux, connects directly to crypto exchanges via ccxt, and uses a deterministic fallback mechanism to reflect on its performance and evolve its strategy over time.

## Architecture

```
Signal (7 strategies + fallback)
    ↓
Confluence Filter (9-dimension quality gate, 0-100 score)
    ↓
Risk Manager (position sizing, auto SL/TP, limits, recovery mode)
    ↓
Execution (ccxt → Binance/Bybit/OKX, paper or live)
    ↓
Position Manager (dynamic BE, trailing stop, profit profiling)
    ↓
Reflection Loop (every N trades: score → hypothesize → edit strategy)
```

## Quick Start

```bash
# Install
cd ~/Projects/sita
pip install -e .

# Paper trading (default)
python3 -m sita run

# With specific exchange
python3 -m sita run --exchange bybit --timeframe 1h

# Check status
python3 -m sita status

# Force reflection
python3 -m sita reflect --fallback

# Backtest
python3 -m sita backtest
```

## Configuration

- `state/goal.yaml` — Your targets (return, drawdown, Sharpe)
- `state/strategy.yaml` — Current strategy (auto-evolved by reflection)
- `state/history/` — Every prior strategy version
- `state/hypotheses.jsonl` — Reflection log

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| SITA_EXCHANGE | binance | Exchange (binance, bybit, okx, kraken) |
| SITA_TRADING_MODE | paper | paper or live |
| SITA_I_ACCEPT_RISK | false | Required true for live trading |
| EXCHANGE_API_KEY | — | API key for live trading |
| EXCHANGE_API_SECRET | — | API secret for live trading |

## Railway Deployment

```bash
cd ~/Projects/sita
railway up
```

## Reflection Loop

Every N closed trades (default: 5):
1. Score performance against goal.yaml
2. Generate hypotheses (what single variable to change)
3. Apply exactly ONE change to strategy.yaml
4. Save prior version to history/
5. Log hypothesis to hypotheses.jsonl

Modes:
- `--fallback`: Deterministic rules (no LLM needed)
- `--hermes`: LLM-powered reasoning (production)

## Safety

- Paper trading by default
- Daily/Weekly/Total loss limits
- Recovery mode (auto-de-risk after drawdown)
- Max position limits
- All state files preserved (full audit trail)
