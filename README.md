# SITA — Self-Improving Trading Agent

> **Codename: SITA 🔱** · Linux-native · No MT5 · No Wine · No Windows · AGPL-3.0

SITA is a fully autonomous, self-improving trading agent that runs on Linux and connects directly to cryptocurrency exchanges via [ccxt](https://github.com/ccxt/ccxt). It implements a complete trading pipeline — signal generation, multi-dimensional confluence filtering, adaptive risk management, exchange execution, position management, and reflection-driven strategy evolution.

Born from the ashes of Cthulu APEX (200K+ lines, 727 files), SITA distills the best signal grading, confluence scoring, and risk management into a clean, modular, production-ready architecture.

**Current Status**: ✅ Live trading on Binance Futures with real capital

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Pipeline Deep-Dive](#pipeline-deep-dive)
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
- **Hedge Mode Support** — Full Binance Futures hedge mode (dual-side position) compatibility

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

## Pipeline Deep-Dive

### 1. Data Acquisition

SITA fetches OHLCV (Open/High/Low/Close/Volume) data directly from the exchange via ccxt. No third-party data providers needed.

```python
ohlcv = exchange.fetch_ohlcv("BTC/USDT:USDT", "15m", limit=200)
```

- **Timeframes**: 1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d (exchange-dependent)
- **Limit**: 200 candles default (configurable)
- **Paper mode**: Generates synthetic OHLCV with realistic price action (trend + mean reversion + noise)

### 2. Regime Detection

Before any signal is generated, SITA classifies the current market regime using ADX, RSI, and EMA slope analysis:

| Regime | ADX Range | RSI Behavior | Strategy Recommendation |
|--------|-----------|--------------|------------------------|
| `trending_strong` | ADX > 25 | RSI trending | `trend_following` |
| `trending_weak` | ADX 20-25 | RSI mixed | `ema_crossover` |
| `ranging` | ADX < 20 | RSI mean-reverting | `mean_reversion` |
| `volatile` | ADX rising | RSI extreme | `scalping` |
| `reversal` | ADX diverging | RSI divergence | `rsi_reversal` |

Confidence levels: `high` (strong ADX + clear RSI), `medium` (mixed signals), `low` (uncertain — skip trading).

### 3. Liquidity Analysis

SITA scans for liquidity zones above and below current price:

- **Buy-side liquidity**: Clusters of stop losses above resistance
- **Sell-side liquidity**: Clusters of stop losses below support
- **Fair Value Gaps (FVG)**: Imbalanced price areas likely to be revisited
- **Liquidity bias**: Net directional pressure from zone distribution

This prevents entering trades directly into liquidity sweep zones.

### 4. Signal Generation

Seven strategies, each producing a signal with direction, confidence, and metadata:

| Strategy | Logic | Best Regime |
|----------|-------|-------------|
| `ema_crossover` | EMA 9/21 crossover with volume confirmation | trending_weak |
| `sma_crossover` | SMA 20/50 crossover, slower signal | trending_strong |
| `momentum_breakout` | Price breaks range with momentum spike | volatile |
| `trend_following` | Higher highs/lows in trend direction | trending_strong |
| `mean_reversion` | Price reverts to VWAP/mean in range | ranging |
| `rsi_reversal` | RSI divergence at extremes | reversal |
| `scalping` | Quick entries on micro-structure | volatile |

**Fallback strategy**: If no primary strategy produces a confident signal, a multi-strategy confluence aggregator combines all weak signals. If the aggregate exceeds the threshold, a trade is considered.

### 5. Confluence Filtering

Every signal passes through a 9-dimension confluence scorer. Each dimension is weighted and produces a score 0-100:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| `level` | 0.18 | Proximity to S/R, round numbers, EMA touch |
| `trend` | 0.17 | Macro trend alignment (higher timeframe) |
| `momentum` | 0.15 | RSI/MACD momentum in trade direction |
| `bos` | 0.12 | Break of Structure / Change of Character |
| `order_block` | 0.12 | ICT Order Block confluence |
| `structure` | 0.08 | Market structure alignment (HH/HL/LH/LL) |
| `session_orb` | 0.08 | Session Opening Range Breakout |
| `timing` | 0.10 | Entry timing quality (candle pattern) |

**Thresholds**:
- **Premium** (≥85): Full position size (1.0x)
- **Good** (70-84): 85% position size
- **Marginal** (50-69): 60% position size
- **Poor** (20-49): 30% position size (or skip)
- **Reject** (<20): No trade

### 6. Risk Management

See [Risk Management](#risk-management) section below for full details.

### 7. Execution

Orders are placed via ccxt directly on the exchange:

- **Market orders**: Immediate execution at current price
- **Limit orders**: Specified price (for entries at better levels)
- **SL/TP**: Stop-loss and take-profit attached as separate orders
- **Hedge mode**: All orders include `positionSide` (LONG/SHORT) and SL/TP include `reduceOnly`

**Minimum notional enforcement**: Binance Futures requires ≥ $5 USDT per order. SITA automatically scales position size up to meet this floor.

### 8. Position Management

Once in a trade, SITA actively manages the position:

- **Breakeven**: After 1R profit, SL moves to entry + spread
- **Trailing stop**: After 2R profit, SL trails at 1.5x ATR
- **Profit profiling**: Partial closes at milestones
  - 1R: Close 25%
  - 2R: Close 25%
  - 3R: Close remaining 50%

### 9. Reflection Loop

Every N closed trades (default: 5), SITA enters reflection:

1. **Score** current strategy (win rate, profit factor, drawdown, Sharpe)
2. **Hypothesize** improvements (one variable change)
3. **Apply** the change to strategy parameters
4. **Version** the prior strategy (saved to `state/history/`)
5. **Log** hypothesis with reasoning (appended to `state/hypotheses.jsonl`)

**One-variable rule**: Only ONE parameter changes per reflection cycle. This is the scientific method — isolate variables to understand causation.

---

## Quick Start

```bash
# Clone
git clone https://github.com/artifact-opensource/sita.git
cd sita

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
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
| `BINANCE_API_KEY` | — | Binance-specific API key (fallback) |
| `BINANCE_SECRET` | — | Binance-specific API secret (fallback) |
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
| `logs/sita.log` | Runtime log |

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

### strategy.yaml (auto-generated)

```yaml
version: "v07"
created: "2026-06-19T22:00:00Z"
primary_strategy: "trend_following"
fallback_enabled: true
disabled_symbols: ["ETH/USDT:USDT"]
parameters:
  rsi_period: 14
  rsi_entry_long: 20
  rsi_entry_short: 80
  sl_atr_mult: 1.5
  tp_rr_ratio: 2.0
  position_size_base: 0.5
```

---

## Live Trading

### ⚠️ Prerequisites

1. API key with Reading + Futures permissions
2. IP whitelist configured on exchange
3. Testnet tested first
4. Small initial capital recommended
5. `SITA_I_ACCEPT_RISK=true` set
6. Understand that **you can lose all invested capital**

### Starting Live Trading

```bash
export SITA_TRADING_MODE=live
export SITA_I_ACCEPT_RISK=true
python3 -m sita run
```

### Binance Setup

1. Create API key at https://www.binance.com/en/my/settings/api-management
2. Enable: **Reading**, **Futures**, **Universal Transfer**
3. Set IP restriction → add your public IP (`curl -s ifconfig.me`)
4. **Position mode**: SITA supports both one-way and hedge mode. If hedge mode is enabled, orders include `positionSide` automatically.
5. Transfer USDT to Futures wallet

### Minimum Order Size

Binance Futures requires **$5 USDT minimum notional** per order. SITA automatically enforces this — position sizes below $5 are scaled up to meet the floor. For a $10 account, this means each trade risks approximately 50% of the account (since the minimum position is $5). This is a constraint of the exchange, not SITA.

**Recommendation**: For proper risk management with SITA's default 1% risk per trade, a minimum account size of **$500** is recommended. With $10, you're trading at the exchange's minimum — higher risk per trade is unavoidable.

### Hedge Mode

Binance Futures supports two position modes:
- **One-way mode**: Only one direction per symbol (long OR short)
- **Hedge mode**: Both directions simultaneously (long AND short)

SITA auto-detects hedge mode and includes `positionSide` (LONG/SHORT) in all orders. SL/TP orders include `reduceOnly` to ensure they only close positions.

---

## Discord Integration

SITA posts rich embed notifications to Discord for all significant events:

| Event | Emoji | Content |
|-------|-------|---------|
| Startup | 🚀 | Version, mode, balance, watchlist, exchange |
| Trade Entry | 📈📉 | Symbol, side, size, entry, SL, TP |
| Trade Exit | ✅❌ | Symbol, side, P&L, close reason |
| Signal | 🟢🔴 | Symbol, direction, confidence, confluence score |
| Health | 💓 | Balance, open positions, win rate, total P&L |
| Reflection | 🧠 | Hypothesis, score, version, reasoning |
| Daily Report | 📊 | Trades count, win rate, P&L, recent trades |
| Error | ⚠️ | Error details, context |

### Delivery Methods

SITA supports two Discord delivery methods:

1. **Webhook** (preferred for simple posting): Channel settings → Integrations → Webhooks → New Webhook
2. **Bot API** (required for forum threads): Discord Developer Portal → Application → Bot

The webhook is tried first. If it fails, the bot API is used as fallback.

### Bot Setup

1. Create app at https://discord.com/developers/applications
2. Create bot, copy token
3. Enable privileged intents: **Message Content**, **Server Members**
4. Generate OAuth2 URL with permissions: `Send Messages`, `Embed Links`, `Create Public Threads`, `Manage Threads`
5. Invite bot to your server
6. Set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in `.env`

### Forum Channel Threading

For forum channels, SITA can create separate threads for different event types:
- `signals` — Trade signals and analysis
- `journal` — Reflection cycles and strategy updates
- `trades` — Trade execution log
- `alerts` — System alerts and errors

### Troubleshooting Discord 403

If Discord returns HTTP 403 (error code 1010):
- **Webhook**: The webhook URL may have been regenerated. Create a new webhook in channel settings.
- **Bot API**: The bot may have been removed from the server. Re-invite using the OAuth2 URL.
- **Forum channels**: Ensure the bot has `Create Public Threads` and `Manage Threads` permissions.

---

## Dashboard

Real-time web dashboard at `http://localhost:8090`:

- **Equity curve** — Balance over time
- **Open positions** — Live P&L, SL/TP levels
- **Trade history** — All closed trades with P&L
- **Confluence scores** — Per-symbol quality metrics
- **Risk gauges** — Daily/weekly/total loss limit usage
- **Reflection log** — Strategy evolution history
- **Regime indicator** — Current market regime per symbol

```bash
python3 -m sita dashboard
```

---

## Reflection System

Every N closed trades (default: 5), SITA reflects on its performance and evolves:

### Process

1. **Score** — Calculate win rate, profit factor, max drawdown, Sharpe ratio
2. **Hypothesize** — Generate candidate strategy changes based on performance analysis
3. **Apply ONE change** — Scientific method: one variable at a time
4. **Version** — Save prior strategy to `state/history/vNN_YYYY-MM-DD.yaml`
5. **Log** — Record hypothesis with reasoning in `state/hypotheses.jsonl`

### Hypothesis Types

| Type | Trigger | Action |
|------|---------|--------|
| Disable symbol | Symbol loses > 3 consecutive trades | Add to `disabled_symbols` list |
| Tighten SL | Win rate < 40% | Reduce ATR multiplier from 1.5 to 1.2 |
| Loosen SL | Win rate > 70% with early SL hits | Increase ATR multiplier from 1.5 to 2.0 |
| Adjust RSI threshold | RSI entries consistently wrong direction | Shift entry threshold by ±5 |
| Change position size | Drawdown exceeds target | Reduce base size by 25% |
| Switch strategy | Current strategy underperforms fallback | Promote fallback to primary |
| Allow both directions | Strong trend in both directions | Enable long + short simultaneously |

### Modes

- **Deterministic Fallback** (default): Rule-based evolution, no LLM needed. Works offline.
- **Hermes LLM** (production): Natural language reasoning for complex evolution. Requires Hermes API access.

```bash
# Force a reflection cycle (deterministic)
python3 -m sita reflect --fallback

# Force a reflection cycle (Hermes LLM)
python3 -m sita reflect --hermes
```

---

## Risk Management

### Position Sizing

SITA uses **%R position sizing** — the amount you're willing to risk per trade:

```
risk_amount = balance × risk_pct × confluence_mult
position_size = risk_amount / sl_distance
```

Where:
- `risk_pct` = account-tier-based risk percentage (0.5% - 2%)
- `confluence_mult` = quality multiplier (0.3 for poor, 0.85 for good, 1.0 for premium)
- `sl_distance` = |entry_price - stop_loss_price|

**Constraints**:
- Minimum notional: $5.00 (Binance Futures requirement)
- Maximum notional: 35% of balance per position
- Minimum lot size: 0.001 (exchange-dependent)

### Account Tiers

Risk per trade adapts to account size:

| Tier | Balance | Risk Per Trade | $10 Account |
|------|---------|----------------|-------------|
| Tiny | ≤ $1,000 | 0.5% | $0.05 |
| Small | ≤ $5,000 | 1.0% | — |
| Medium | ≤ $20,000 | 1.5% | — |
| Large | > $20,000 | 2.0% | — |

### Circuit Breakers

Hard limits that stop trading when hit:

| Limit | Threshold | Action | $10 Account |
|-------|-----------|--------|-------------|
| Daily Loss | 3% | Stop trading for the day | $0.30 |
| Weekly Loss | 5% | Stop trading for the week | $0.50 |
| Total Drawdown | 10% | Hard stop, close all | $1.00 |
| Recovery Mode | 5% DD | 50% risk reduction | $0.50 |

### Stop Loss Calculation

ATR-based stop loss adapts to market volatility:

```
SL_long = entry_price - (ATR × 1.5)
SL_short = entry_price + (ATR × 1.5)
```

ATR period: 14 candles. Multiplier adjustable via reflection.

### Take Profit Calculation

Risk:reward based take profit:

```
TP_long = entry_price + (|entry - SL| × 2.0)
TP_short = entry_price - (|entry - SL| × 2.0)
```

Default R:R ratio is 2:1. Adjustable via reflection.

### Position Management

- **Dynamic Breakeven**: After 1R profit, SL moves to entry price + spread
- **Trailing Stop**: After 2R profit, SL trails at 1.5x ATR from highest point
- **Profit Profiling**: Partial closes at R-milestones
  - 1R profit: Close 25% of position
  - 2R profit: Close 25% of position
  - 3R profit: Close remaining 50%

### Symbol Disabling

The reflection loop can disable consistently losing symbols. Disabled symbols:
- Are skipped during the trading cycle
- Have a cooldown period (default: 30 minutes)
- Are logged in `state/strategy.yaml` under `disabled_symbols`
- Can be re-enabled manually or by reflection

---

## Supported Exchanges

SITA uses **ccxt**, supporting **105+ exchanges**.

### Pre-Configured

| Exchange | ID | Testnet | Type | Min Notional | Hedge Mode |
|----------|----|---------|------|-------------|------------|
| Binance | `binance` | ✅ | Futures | $5 USDT | ✅ |
| Bybit | `bybit` | ✅ | Linear | $1 USDT | ✅ |
| OKX | `okx` | ✅ | Swap | $1 USDT | ✅ |
| Kraken | `kraken` | ❌ | Spot | $5 USD | ❌ |

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

From paper trading test (38 trades, $10K initial balance):

| Metric | Value |
|--------|-------|
| Win Rate | 65.8% |
| Total P&L | $1,391.82 |
| Max Drawdown | 0.59% |
| Strategy Evolution | v01 → v07 (5 cycles) |
| Best Performers | SOL shorts, BTC trend trades |
| Disabled Symbols | ETH (consistent losses) |

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

Set environment variables in Railway dashboard. Ensure `SITA_TRADING_MODE` and `SITA_I_ACCEPT_RISK` are set correctly.

### Process Management

For production deployments, use a process manager:

```bash
# systemd (recommended)
sudo cp sita.service /etc/systemd/system/
sudo systemctl enable sita
sudo systemctl start sita

# Or screen/tmux
screen -S sita
python3 -m sita run
# Ctrl+A, D to detach
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, component deep-dive, data flow diagrams |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Installation, configuration, live trading, troubleshooting |
| [docs/EXCHANGES.md](docs/EXCHANGES.md) | Complete list of 105+ supported exchanges |

---

## Safety

SITA implements multiple layers of protection:

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
- **Minimum notional enforcement** — Prevents exchange rejection errors
- **Hedge mode compatibility** — Correct position side on all orders

**⚠️ IMPORTANT**: Cryptocurrency trading involves substantial risk of loss. SITA is a tool — not financial advice. Never trade with money you cannot afford to lose. Past performance (including dry-run results) does not guarantee future results.

---

## License

**AGPL-3.0** — See [LICENSE](LICENSE)

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
