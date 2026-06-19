# Self-Improving Trading Agent
> Codename: SITA 🔱

**Linux-native. No MT5. No Wine.**

SITA is a self-improving trading agent that runs on Linux, connects directly to crypto exchanges via ccxt, and uses a deterministic fallback mechanism (with optional LLM integration) to reflect on its performance and evolve its strategy over time.

Born from the ashes of Cthulu APEX (200K+ lines, 727 files), SITA distills the best signal grading, 9-dimension confluence, and supernatural risk management into a clean, modular, Linux-native architecture.

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
│  │ (5 regimes) │    │ (zones, FVG, │             │               |
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
│  │              Dashboard (port 8090) + Journal              │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### Signal Engine (7 Strategies + Fallback)

| Strategy | Best For | Indicators |
|----------|----------|------------|
| EMA Crossover | Trending markets | EMA 9/21/55 |
| SMA Crossover | Smooth trends | SMA 20/50/200 |
| Momentum Breakout | Strong moves | RSI + Volume |
| Scalping | Ranging/choppy | Bollinger Bands + RSI |
| Trend Following | Strong trends | ADX + EMA |
| Mean Reversion | Ranging | RSI extremes + BB |
| RSI Reversal | Overextended | RSI divergence |

When primary strategy lacks confidence, the **multi-strategy fallback** blends signals from all 7.

### Confluence Filter (9 Dimensions)

Every signal must pass through a 9-dimension quality gate scored 0-100:

| Dimension | Weight | What it Measures |
|-----------|--------|-----------------|
| Level Proximity | 18% | Distance to key S/R levels |
| Trend Alignment | 17% | Signal direction vs. trend |
| Momentum | 15% | RSI/MACD confirmation |
| Break of Structure | 12% | BOS/CHoCH detection |
| Order Block | 12% | Institutional order flow |
| Timing | 10% | Session/volume timing |
| Market Structure | 8% | Higher highs/lows |
| Opening Range | 8% | ORB breakouts |

**Score thresholds:**
- 80+ → Premium (full size)
- 60-79 → Good (reduced size)
- 40-59 → Marginal (minimum size, may wait)
- <40 → Rejected

### Risk Manager

- **Position sizing** — %R model with max notional cap (30% of equity)
- **Auto SL/TP** — ATR-based stops with regime awareness
- **Loss limits** — Daily (1.5%), Weekly (3%), Total (5%) circuit breakers
- **Recovery mode** — Auto 25% risk reduction after 3% drawdown
- **Max 3 positions** — 1 per symbol, max 3 concurrent

### Regime Detection

Classifies market into 5 regimes with confidence levels:

| Regime | Characteristics | Strategy Bias |
|--------|----------------|---------------|
| Trending Strong | ADX > 25, clear direction | Trend Following |
| Trending Weak | ADX 15-25, loose structure | EMA Crossover |
| Ranging | ADX < 15, bounded price | Scalping / Mean Rev |
| Volatile | ATR spike, wide range | Reduce size / wait |
| Reversal | RSI extreme + divergence | Mean Reversion |

### Liquidity Analysis

- Stop hunt zone detection
- Fair Value Gap (FVG) identification
- Volume Node mapping (high-volume price levels)
- Liquidity bias (bullish/bearish/neutral)

### Reflection Loop

Every N closed trades (default: 5):
1. Score performance against goals
2. Generate hypotheses (what single variable to change)
3. Apply exactly **ONE** change
4. Save prior version to history/
5. Log hypothesis with reasoning

**Hypothesis types:**
- Disable consistently losing symbols
- Tighten/loosen stop loss
- Change entry indicator
- Adjust position size
- Allow/disallow directions
- Switch strategy type

**Modes:**
- Deterministic fallback (rule-based, no LLM needed)
- Hermes LLM (natural language reasoning — production)

### Position Manager

- **Dynamic breakeven** — Moves SL to entry after 1R profit
- **Trailing stop** — Trails by 1.5x ATR after 2R
- **Profit profiling** — Partial closes at 1R (25%), 2R (25%), 3R (50%)

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

# With specific exchange
python3 -m sita run --exchange binance --timeframe 15m

# Check status
python3 -m sita status

# Force reflection
python3 -m sita reflect --fallback

# Backtest
python3 -m sita backtest

# Dashboard
python3 -m sita dashboard
```

## Supported Exchanges

SITA uses **ccxt** under the hood, supporting **105+ exchanges**.

### Pre-Configured (Ready to Use)

| Exchange | ID | Testnet | Type | Notes |
|----------|----|---------|------|-------|
| Binance | `binance` | ✅ | Futures | Largest liquidity, deep testnet |
| Bybit | `bybit` | ✅ | Linear | Good perps, solid API |
| OKX | `okx` | ✅ | Swap | Strong altcoin selection |
| Kraken | `kraken` | ❌ | Spot | Regulated, EUR/USD focus |

### Recommended by Use Case

| Use Case | Exchange |
|----------|----------|
| Largest liquidity perps | Binance, Bybit, OKX |
| No KYC perps | MEXC, Phemex, Bitget |
| Regulated spot | Coinbase, Kraken, Bitstamp |
| Altcoin hunting | KuCoin, Gate.io, MEXC |
| Crypto options | Deribit |
| DeFi perps | Hyperliquid, dYdX |

### Full Exchange List

<details>
<summary>Major CEX (50 exchanges)</summary>

Binance, Binance Coin-M, Binance US, Binance USDM, BingX, Bitfinex, Bitflyer, Bitget, Bithumb, BitMEX, Bitso, Bitstamp, BTC Markets, Bybit, Bybit EU, Coinbase, Coinbase Exchange, Coinbase International, Coincheck, CoinEX, CoinSpot, Crypto.com, Deepcoin, Delta, Deribit, Extended, Foxbit, Gate.io, Gemini, HitBTC, Independent Reserve, Kraken, Kraken Futures, KuCoin, KuCoin Futures, LBank, Mercado Bitcoin, MEXC, OKX, OKX US, Phemex, Poloniex, Upbit, WhiteBIT, WOO X, WOO Pro, XT.com, Zaif

</details>

<details>
<summary>Other CEX + DEX (49 exchanges)</summary>

Aftermath, Apex, AscendEX, Aster, Backpack, Bequant, Bit2C, Bitbank, Bitbns, BitMart, Bitopro, Bitrue, BitTeam, BitTrade, Bitvavo, Blockchain.com, Blofin, BTCBox, BTCTurk, Bullish, BYDFI, CEX.IO, Coinmate, CoinMetro, Coinone, Coins.ph, Cryptomus, Derive, EXMO, FMFW.io, GRVT, HashKey, Hibachi, Hollaex, HTX, Hyperliquid, Indodax, Latoken, Luno, NDAX, OneTrading, P2B, Pacifica, Paradex, Paymium, Tokocrypto, Toobit, Weex, ZebPay

</details>

<details>
<summary>Forex/CFD (3 exchanges)</summary>

BigONE, Digifinex, Lighter

</details>

<details>
<summary>Stocks (2 exchanges)</summary>

Alpaca (US stocks, commission-free), Mode Trade (EU stocks)

</details>

<details>
<summary>DeFi (1 exchange)</summary>

dYdX (perps on dYdX chain)

</details>

See [docs/EXCHANGES.md](docs/EXCHANGES.md) for the complete list with categories.

## Configuration

### State Files

| File | Purpose |
|------|---------|
| `state/goal.yaml` | Your targets (return, drawdown, Sharpe) |
| `state/strategy.yaml` | Current strategy (auto-evolved by reflection) |
| `state/history/` | Every prior strategy version (full audit trail) |
| `state/hypotheses.jsonl` | Reflection log with reasoning |
| `state/trades.jsonl` | Complete trade history |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SITA_EXCHANGE` | binance | Exchange ID |
| `SITA_TRADING_MODE` | paper | paper or live |
| `SITA_I_ACCEPT_RISK` | false | Must be true for live trading |
| `SITA_BASE_DIR` | . | Base directory for state files |
| `SITA_TIMEFRAME` | 15m | Default timeframe |
| `SITA_LOOP_INTERVAL` | 30 | Seconds between cycles |
| `EXCHANGE_API_KEY` | — | API key for live trading |
| `EXCHANGE_API_SECRET` | — | API secret for live trading |
| `DISCORD_TOKEN` | — | Discord bot token for alerts |
| `DISCORD_CHANNEL_ID` | — | Channel ID for alerts |

### goal.yaml

```yaml
initial_balance: 10000
target_return_30d: 0.05      # 5% monthly target
max_drawdown: 0.05            # 5% max drawdown
min_sharpe: 1.5
min_win_rate: 0.45
max_daily_loss_pct: 0.015     # 1.5% daily stop
max_weekly_loss_pct: 0.03     # 3% weekly stop
```

### strategy.yaml (Auto-Evolved)

```yaml
version: '06'
entry:
  indicator: rsi
  threshold: 22
  direction: both
stop_loss_pct: 2.0
position_size_r: 0.5
regime: trending
disabled_symbols:
  - ETH/USDT:USDT
```

## Safety

- **Paper trading by default** — Must explicitly set `SITA_TRADING_MODE=live` + `SITA_I_ACCEPT_RISK=true`
- **Daily loss limit** — Stops trading for the day at 1.5% loss
- **Weekly loss limit** — Stops trading for the week at 3% loss
- **Total loss limit** — Hard stop at 5% drawdown
- **Recovery mode** — Auto 25% risk reduction after 3% drawdown
- **Max 3 positions** — 1 per symbol, max 3 concurrent
- **Reflection versioning** — Every strategy change saved, full rollback capability
- **Audit trail** — Complete trade + hypothesis history

## Railway Deployment

```bash
cd sita
railway up
```

Set environment variables in Railway dashboard:
- `SITA_EXCHANGE=binance`
- `SITA_TRADING_MODE=paper`
- `EXCHANGE_API_KEY` / `EXCHANGE_API_SECRET` (for live)

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

## Testing

```bash
# Run integration test
python3 -m pytest tests/ -v

# Run with synthetic data
python3 -m sita run --exchange binance --timeframe 15m

# Backtest
python3 -m sita backtest
```

## License

**AGPL-3.0** — See [LICENSE](LICENSE)

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
