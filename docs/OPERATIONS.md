# SITA Operations Guide

## Table of Contents

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Running SITA](#running-sita)
4. [Live Trading](#live-trading)
5. [Discord Integration](#discord-integration)
6. [Dashboard](#dashboard)
7. [Monitoring & Troubleshooting](#monitoring--troubleshooting)
8. [Reflection System](#reflection-system)
9. [Risk Management](#risk-management)
10. [Exchange Support](#exchange-support)

## Installation

### Prerequisites

- Python 3.10+
- pip or uv package manager
- Linux (tested on Kali, Ubuntu, Debian)

### Setup

```bash
# Clone
git clone https://github.com/artifact-opensource/sita.git
cd sita

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Verify
python3 -m sita status
```

### Dependencies

| Package | Purpose | Required |
|---------|---------|----------|
| ccxt | Exchange connectivity | Yes (for live/paper with real data) |
| pandas | Data manipulation | Yes |
| numpy | Numerical computation | Yes |
| flask | Dashboard web server | Yes (for dashboard) |

## Configuration

### Environment Variables

| Variable | Default | Description | Required For |
|----------|---------|-------------|--------------|
| `SITA_EXCHANGE` | `binance` | ccxt exchange ID | All modes |
| `SITA_TRADING_MODE` | `paper` | `paper` or `live` | All modes |
| `SITA_I_ACCEPT_RISK` | `false` | Must be `true` for live trading | Live only |
| `SITA_BASE_DIR` | `~/Projects/sita` | Base directory for state files | All modes |
| `SITA_LOG_LEVEL` | `INFO` | Logging level | All modes |
| `EXCHANGE_API_KEY` | — | Exchange API key | Live only |
| `EXCHANGE_API_SECRET` | — | Exchange API secret | Live only |
| `DISCORD_BOT_TOKEN` | — | Discord bot token | Discord alerts |
| `DISCORD_WEBHOOK_URL` | — | Discord webhook URL | Discord alerts |
| `DISCORD_CHANNEL_ID` | — | Discord channel ID | Discord alerts |

### .env File

Create `.env` in project root:

```env
SITA_EXCHANGE=binance
SITA_TRADING_MODE=paper
SITA_I_ACCEPT_RISK=false

EXCHANGE_API_KEY=your_api_key_here
EXCHANGE_API_SECRET=your_api_secret_here

DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_WEBHOOK_URL=your_webhook_url_here
DISCORD_CHANNEL_ID=your_channel_id_here
```

**Security**: `.env` is in `.gitignore`. Never commit credentials.

### goal.yaml

Define your trading goals:

```yaml
initial_balance: 10000
target_return_30d: 0.05      # 5% monthly target
max_drawdown: 0.10            # 10% max drawdown
min_sharpe: 1.5
min_win_rate: 0.45
max_daily_loss_pct: 0.03      # 3% daily stop
max_weekly_loss_pct: 0.05     # 5% weekly stop
```

### strategy.yaml (Auto-Evolved)

This file is managed by the reflection engine. Manual edits are possible but will be overwritten:

```yaml
version: '07'
entry:
  indicator: rsi
  threshold: 20
  direction: both
stop_loss_pct: 2.0
position_size_r: 0.5
regime: trending
disabled_symbols:
  - ETH/USDT:USDT
```

## Running SITA

### Paper Trading (Default)

```bash
python3 -m sita run
```

Uses synthetic data if no API keys, or testnet if configured.

### Live Trading

```bash
# Set env vars
export SITA_TRADING_MODE=live
export SITA_I_ACCEPT_RISK=true

# Run
python3 -m sita run
```

**⚠️ WARNING**: Live trading uses real money. Start with small amounts.

### With Options

```bash
# Specific exchange and timeframe
python3 -m sita run --exchange binance --timeframe 15m --interval 60

# Custom loop interval (seconds)
python3 -m sita run --interval 30
```

### Check Status

```bash
python3 -m sita status
```

### Force Reflection

```bash
# Deterministic fallback
python3 -m sita reflect --fallback

# Hermes LLM (requires Hermes API)
python3 -m sita reflect --hermes
```

## Live Trading

### Pre-Flight Checklist

1. ✅ API key created on exchange with appropriate permissions (Reading + Futures)
2. ✅ IP whitelist configured on exchange (add your public IP)
3. ✅ Testnet tested first
4. ✅ Small initial capital ($10-100 recommended for first run)
5. ✅ Discord alerts configured (optional but recommended)
6. ✅ `SITA_I_ACCEPT_RISK=true` set

### Binance-Specific Setup

1. Create API key at https://www.binance.com/en/my/settings/api-management
2. Enable: Reading, Futures, Universal Transfer
3. Set IP restriction to "Trusted IPs" and add your public IP
4. Find your public IP: `curl -s ifconfig.me`
5. Transfer USDT to Futures wallet

### Minimum Order Sizes

Binance futures enforces a minimum notional value of **$5 USDT** per order. SITA automatically enforces this via the `min_notional` config parameter. Position sizes below $5 are scaled up to meet the minimum.

### Monitoring Live Trading

```bash
# Watch log in real-time
tail -f logs/sita.log

# Check for errors
grep -i error logs/sita.log | tail -20

# Check trade activity
grep -i "order placed\|order failed\|position" logs/sita.log | tail -20
```

## Discord Integration

### Bot Setup

1. Create a Discord application at https://discord.com/developers/applications
2. Go to "Bot" section and create a bot
3. Copy the bot token
4. Enable these Privileged Intents:
   - Message Content Intent
   - Server Members Intent
5. Generate OAuth2 URL with permissions: `bot` + `applications.commands`
6. Required bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Create Public Threads (for forum channels)
   - Manage Threads (for forum channels)

### Webhook Setup

1. In Discord, go to channel settings → Integrations → Webhooks
2. Create a new webhook
3. Copy the webhook URL
4. Paste in `.env` as `DISCORD_WEBHOOK_URL`

### Forum Channel Setup

For thread-based journaling:

1. Create a Forum channel in your Discord server
2. Set the channel ID in `.env` as `DISCORD_CHANNEL_ID`
3. The bot will create threads for:
   - Signal discussions
   - Trade journals
   - Strategy reflections

### Troubleshooting Discord

**403 Error (Bot Token)**:
- Verify token is correct (no extra whitespace)
- Check bot is invited to server with correct permissions
- Ensure privileged intents are enabled in Developer Portal
- Bot may need to be re-invited after permission changes

**403 Error (Webhook)**:
- Webhook URL may be invalidated; regenerate in Discord
- Channel may have webhook permissions restricted

**No Messages Appearing**:
- Check `DISCORD_CHANNEL_ID` matches the target channel
- Verify bot has "Send Messages" permission in that channel
- For forum channels: bot needs "Create Public Threads"

## Dashboard

```bash
python3 -m sita dashboard
# or with custom port
python3 -m sita dashboard --port 8090
```

Access at `http://localhost:8090`

### Dashboard Features

- **Equity Curve**: Real-time balance history
- **Open Positions**: Live P&L for each position
- **Trade History**: Complete log with entry/exit prices
- **Risk Gauges**: Daily/weekly/total loss limit usage
- **Confluence Scores**: Historical signal quality
- **Reflection Log**: Strategy evolution timeline
- **Regime Indicator**: Current market regime

## Monitoring & Troubleshooting

### Log File

```
logs/sita.log
```

### Common Issues

**ccxt not installed**:
```bash
pip install ccxt
```

**Exchange connection failed**:
- Check API key/secret
- Verify IP whitelist includes your IP
- Test with: `python3 -c "import ccxt; e = ccxt.binance(); print(e.fetch_ticker('BTC/USDT'))"`

**Position size too small (Binance -4164)**:
- SITA auto-enforces $5 minimum notional
- If still occurring, check `min_notional` in config

**Discord 403**:
- Regenerate bot token or webhook URL
- Re-invite bot with correct permissions

**Stale .pyc cache**:
```bash
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```

### Health Check

```bash
# Check if engine is running
pgrep -f "sita"

# Check latest log entries
tail -5 logs/sita.log

# Check for errors in last hour
grep "$(date +%Y-%m-%d\ %H)" logs/sita.log | grep -i error
```

## Reflection System

### How It Works

Every N closed trades (default: 5), the reflection engine:

1. **Scores** performance against goals
2. **Generates hypotheses** for improvement
3. **Applies exactly ONE change** (scientific method)
4. **Versions** the prior strategy
5. **Logs** the hypothesis with reasoning

### Hypothesis Types

| Type | Example | When Applied |
|------|---------|-------------|
| Disable symbol | Disable ETH after 3+ consecutive losses | Symbol underperforming |
| Adjust SL | Tighten SL from 2% to 1.5% | Excessive slippage |
| Change threshold | RSI threshold 20 → 25 | Too many false signals |
| Direction bias | Allow only longs | Short signals losing |
| Strategy switch | EMA crossover → Trend following | Regime change detected |

### Viewing Reflection History

```bash
# View hypothesis log
cat state/hypothesies.jsonl | python3 -m json.tool

# View strategy evolution
ls -la state/history/

# Current strategy
cat state/strategy.yaml
```

### Manual Override

You can manually edit `state/strategy.yaml`, but the reflection engine will overwrite it on the next cycle. To make permanent changes, modify the reflection engine's hypothesis generation logic.

## Risk Management

### Position Sizing Formula

```
risk_amount = balance × risk_pct × confluence_mult
position_size = risk_amount / sl_distance

Where:
- risk_pct = 0.5-2% (by account tier)
- confluence_mult = 0.3-1.0 (by signal quality)
- sl_distance = |entry_price - stop_loss_price|
```

### Minimum Notional Enforcement

```
if (position_size × entry_price) < min_notional:
    position_size = min_notional / entry_price
```

This ensures all orders meet Binance's $5 minimum.

### Maximum Position Cap

```
max_notional = balance × 0.35
if (position_size × entry_price) > max_notional:
    position_size = max_notional / entry_price
```

### Circuit Breaker Logic

```
if daily_loss ≥ 3% of initial_balance:
    reject all new trades until next day

if weekly_loss ≥ 5% of initial_balance:
    reject all new trades until next week

if drawdown ≥ 10% of peak_balance:
    close all positions, halt trading

if drawdown ≥ 5% of peak_balance:
    enter recovery mode (50% risk reduction)
```

## Exchange Support

### Pre-Configured Exchanges

| Exchange | ID | Type | Testnet | Min Notional |
|----------|----|------|---------|-------------|
| Binance | `binance` | Futures | ✅ | $5 USDT |
| Bybit | `bybit` | Linear | ✅ | $1 USDT |
| OKX | `okx` | Swap | ✅ | $1 USDT |
| Kraken | `kraken` | Spot | ❌ | $5 USD |

### Adding a Custom Exchange

Edit `config.py`:

```python
SUPPORTED_EXCHANGES["myexchange"] = {
    "name": "MyExchange",
    "paper_trading": False,
    "default_type": "future",
    "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
}
```

Then set `SITA_EXCHANGE=myexchange` in `.env`.
