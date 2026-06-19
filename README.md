# SITA 
> Self-Improving Trading Agent
> **Codename: SITA 🔱** · Linux-native · No MT5 · No Wine · No Windows

SITA is a fully autonomous, self-improving trading agent that runs on Linux and connects directly to cryptocurrency exchanges via ccxt. It implements a complete trading pipeline — signal generation, 9-dimension confluence filtering, adaptive risk management, exchange execution, and reflection-driven strategy evolution.

Born from the ashes of Cthulu APEX (200K+ lines, 727 files), SITA distills the best signal grading, confluence scoring, and supernatural risk management into a clean, modular, production-ready architecture.

**Current Status**: ✅ Live trading on Binance futures with USDT

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Live Trading](#live-trading)
- [Discord Integration](#discord-integration)
- [Dashboard](#dashboard)
- [Reflection System](#reflection-system)
- [Risk Management](#risk-management)
- [Supported Exchanges](#supported-exchanges)
- [Testing](#testing)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Safety](#safety)
- [License](#license)

---

## Features

- **7 Trading Strategies** — EMA/SMA crossover, momentum breakout, scalping, trend following, mean reversion, RSI reversal, plus multi-strategy fallback
- **9-Dimension Confluence Filter** — Level proximity, trend alignment, momentum, BOS, order blocks, timing, structure, session ORB
- **Adaptive Risk Management** — %R position sizing, ATR-based SL/TP, daily/weekly/total circuit breakers, recovery mode
- **Regime Detection** — 5 market regimes (trending strong/weak, ranging, volatile, reversal) with confidence scoring
- **Liquidity Analysis** — Stop hunt zones, fair value gaps, volume nodes, liquidity bias
- **Self-Improving** — Deterministic reflection loop evolves strategy one variable at a time
- **Exchange-Agnostic** — ccxt supports 105+ exchanges; pre-configured for Binance, Bybit, OKX, Kraken
- **Discord Alerts** — Rich embed notifications for trades, signals, health, reflections, daily reports
- **Real-Time Dashboard** — Web UI with equity curve, positions, risk gauges, reflection log
- **Paper Trading** — Safe default mode with synthetic data generation
- **Full Audit Trail** — Every trade, strategy version, and hypothesis logged

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        SITA Pipeline                             │
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐    │
│  │   Signal    │    │  Confluence  │    │   Risk Manager    │    │
│  │  (7 strat + │───▶│  (9-dim gate │───▶│  (sizing, SL/TP,  │    │
│  │   fallback) │    │   0-100)     │    │   limits, recover)│    │
│  └─────────────┘    └──────────────┘    └────────┬──────────┘    │
│                                                  │               │
│  ┌─────────────┐    ┌──────────────┐             │               │
│  │   Regime    │    │  Liquidity   │             │               │
│  │  Detector   │    │  Analyzer    │             │               │
│  │ (5 regimes) │    │ (zones, FVG, │             │               │
│  │             │    │  stop hunts) │             │               │
│  └──────┬──────┘    └──────┬───────┘             │               │
│         │                  │                     │               │
│         └────────┬─────────┘                     │               │
│                  │                               │               │
│                  ▼                               ▼               │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                    Engine (main loop)                     │   │
│  │  Fetch → Regime → Liquidity → Signal → Confluence → Risk  │   │
│  └───────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                     Execution                             │   │
│  │         ccxt → Binance/Bybit/OKX/Kraken/105+              │   │
│  │              paper trading / live trading                 │   │
│  └───────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                   Position Manager                        │   │
│  │        dynamic BE, trailing stop, profit profiling        │   │
│  └───────────────────────────┬───────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │                   Reflection Loop                         │   │
│  │   every N trades → score → hypothesize → edit strategy    │   │
│  │           (deterministic fallback / Hermes LLM)           │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │              Dashboard (port 8090) + Discord              │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed component documentation.

---

## Quick Start

```bash
# Clone
git clone https://github.com/artifact-opensource/sita.git
cd sita

# Install
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Interactive setup (recommended)
python3 -m sita setup

# Or configure manually
cp .env.example .env
# Edit .env with your settings

# Paper trading (default)
python3 -m sita run

# Check status
python3 -m sita status
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SITA_EXCHANGE` | `binance` | Exchange ID (any ccxt exchange) |
| `SITA_TRADING_MODE` | `paper` | `paper` or `live` |
| `SITA_I_ACCEPT_RISK` | `false` | Must be `true` for live trading |
| `SITA_BASE_DIR` | `~/Projects/sita` | Base directory for state files |
| `SITA_LOG_LEVEL` | `INFO` | Logging level |
| `EXCHANGE_API_KEY` | — | API key for live trading |
| `EXCHANGE_API_SECRET` | — | API secret for live trading |
| `DISCORD_BOT_TOKEN` | — | Discord bot token |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook URL |
| `DISCORD_CHANNEL_ID` | — | Discord channel/forum ID |

### State Files

| File | Purpose |
|------|---------|
| `state/goal.yaml` | Trading targets (return, drawdown, Sharpe) |
| `state/strategy.yaml` | Current strategy (auto-evolved by reflection) |
| `state/history/` | Every prior strategy version (full audit trail) |
| `state/hypotheses.jsonl` | Reflection log with reasoning |
| `state/trades.jsonl` | Complete trade history |

### goal.yaml

```yaml
initial_balance: 10000
target_return_30d: 0.05      # 5% monthly target
max_drawdown: 0.10            # 10% max drawdown
min_sharpe: 1.5
min_win_rate: 0.45
max_daily_loss_pct: 0.03      # 3% daily stop
max_weekly_loss_pct: 0.05     # 5% weekly stop
```

---

## Live Trading

### ⚠️ Prerequisites

1. API key with Reading + Futures permissions
2. IP whitelist configured on exchange
3. Testnet tested first
4. Small initial capital recommended
5. `SITA_I_ACCEPT_RISK=true` set

### Starting Live Trading

```bash
export SITA_TRADING_MODE=live
export SITA_I_ACCEPT_RISK=true
python3 -m sita run
```

### Binance Setup

1. Create API key at https://www.binance.com/en/my/settings/api-management
2. Enable: Reading, Futures, Universal Transfer
3. Set IP restriction → add your public IP (`curl -s ifconfig.me`)
4. Transfer USDT to Futures wallet

### Minimum Order Size

Binance futures requires **$5 USDT minimum notional** per order. SITA automatically enforces this — position sizes below $5 are scaled up to meet the floor.

---

## Discord Integration

SITA posts rich embed notifications to Discord:

| Event | Content |
|-------|---------|
| 🚀 Startup | Version, mode, balance, watchlist |
| 📈 Trade Entry | Symbol, side, size, entry, SL, TP |
| 📉 Trade Exit | Symbol, side, P&L, reason |
| 🟢 Signal | Symbol, direction, confidence, confluence |
| 💓 Health | Balance, positions, win rate, P&L |
| 🧠 Reflection | Hypothesis, score, version, reasoning |
| 📊 Daily Report | Trades, win rate, P&L, recent history |

### Bot Setup

1. Create app at https://discord.com/developers/applications
2. Create bot, copy token
3. Enable privileged intents (Message Content, Server Members)
4. Invite with permissions: Send Messages, Embed Links, Create Public Threads
5. Set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in `.env`

### Webhook Setup

1. Channel settings → Integrations → Webhooks → New Webhook
2. Copy URL to `DISCORD_WEBHOOK_URL` in `.env`

---

## Dashboard

Real-time web dashboard at `http://localhost:8090`:

- Equity curve
- Open positions with live P&L
- Trade history
- Confluence scores
- Risk gauges (daily/weekly/total usage)
- Reflection log
- Regime indicator

```bash
python3 -m sita dashboard
```

---

## Reflection System

Every N closed trades (default: 5), SITA reflects on its performance and evolves:

1. **Score** — Win rate, profit factor, drawdown, Sharpe
2. **Hypothesize** — Generate candidate strategy changes
3. **Apply ONE change** — Scientific method: one variable at a time
4. **Version** — Save prior strategy to `state/history/`
5. **Log** — Record hypothesis with reasoning in `state/hypotheses.jsonl`

### Hypothesis Types

- Disable consistently losing symbols
- Adjust SL tightness
- Change entry indicator threshold
- Adjust position size
- Allow/disallow directional bias
- Switch primary strategy

### Modes

- **Deterministic Fallback**: Rule-based, no LLM needed (default)
- **Hermes LLM**: Natural language reasoning for complex evolution (production)

---

## Risk Management

### Position Sizing

```
risk_amount = balance × risk_pct × confluence_mult
position_size = risk_amount / sl_distance
```

- **Risk per trade**: 0.5-2% (adaptive by account size)
- **Min notional**: $5.00 (Binance futures minimum)
- **Max notional**: 35% of balance per position

### Account Tiers

| Tier | Balance | Risk Per Trade |
|------|---------|----------------|
| Tiny | ≤ $1,000 | 0.5% |
| Small | ≤ $5,000 | 1.0% |
| Medium | ≤ $20,000 | 1.5% |
| Large | > $20,000 | 2.0% |

### Circuit Breakers

| Limit | Threshold | Action |
|-------|-----------|--------|
| Daily Loss | 3% | Stop trading for the day |
| Weekly Loss | 5% | Stop trading for the week |
| Total DD | 10% | Hard stop, close all positions |
| Recovery | 5% DD | 50% risk reduction |

### Position Management

- **Dynamic Breakeven**: Moves SL to entry after 1R profit
- **Trailing Stop**: Trails at 1.5x ATR after 2R profit
- **Profit Profiling**: Partial closes at 1R (25%), 2R (25%), 3R (50%)

---

## Supported Exchanges

SITA uses **ccxt**, supporting **105+ exchanges**.

### Pre-Configured

| Exchange | ID | Testnet | Type | Min Notional |
|----------|----|---------|------|-------------|
| Binance | `binance` | ✅ | Futures | $5 USDT |
| Bybit | `bybit` | ✅ | Linear | $1 USDT |
| OKX | `okx` | ✅ | Swap | $1 USDT |
| Kraken | `kraken` | ❌ | Spot | $5 USD |

### By Use Case

| Use Case | Recommended |
|----------|-------------|
| Largest liquidity perps | Binance, Bybit, OKX |
| No KYC perps | MEXC, Phemex, Bitget |
| Regulated spot | Coinbase, Kraken, Bitstamp |
| Altcoin hunting | KuCoin, Gate.io, MEXC |
| Crypto options | Deribit |
| DeFi perps | Hyperliquid, dYdX |

See [docs/EXCHANGES.md](docs/EXCHANGES.md) for the complete list.

---

## Testing

```bash
# Run integration tests
python3 -m pytest tests/ -v

# Paper trading with synthetic data
python3 -m sita run --exchange binance --timeframe 15m

# Force reflection cycle
python3 -m sita reflect --fallback

# Check current status
python3 -m sita status
```

### Dry-Run Results

From paper trading test (38 trades, $10K initial):

| Metric | Value |
|--------|-------|
| Win Rate | 65.8% |
| Total P&L | $1,391.82 |
| Max Drawdown | 0.59% |
| Strategy Evolution | v01 → v07 (5 cycles) |
| Best Performers | SOL shorts, BTC trend trades |
| Disabled | ETH (consistent losses) |

---

## Deployment

### Local

```bash
python3 -m sita run
```

### Docker

```bash
docker build -t sita .
docker run -d --env-file .env -p 8090:8090 sita
```

### Railway

```bash
cd sita
railway up
```

Set environment variables in Railway dashboard.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, component deep-dive, data flow |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Installation, configuration, live trading, troubleshooting |
| [docs/EXCHANGES.md](docs/EXCHANGES.md) | Complete list of 105+ supported exchanges |

---

## Safety

- **Paper trading by default** — Must explicitly set `SITA_TRADING_MODE=live` + `SITA_I_ACCEPT_RISK=true`
- **Confluence gate** — Low-quality signals rejected before risk check
- **Daily loss limit** — Stops trading at 3% daily loss
- **Weekly loss limit** — Stops trading at 5% weekly loss
- **Total loss limit** — Hard stop at 10% drawdown
- **Recovery mode** — Auto 50% risk reduction after 5% drawdown
- **Max 1 position** — Focused trading (configurable)
- **Symbol disabling** — Reflection disables losing symbols
- **Full audit trail** — Every trade, strategy version, and hypothesis logged
- **Version rollback** — Any prior strategy can be restored from `state/history/`

---

## License

**AGPL-3.0** — See [LICENSE](LICENSE)

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
