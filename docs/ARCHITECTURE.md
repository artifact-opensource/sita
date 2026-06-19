# SITA Architecture

## System Overview

SITA (Self-Improving Trading Agent) is a Linux-native, fully autonomous trading system that connects directly to cryptocurrency exchanges via ccxt. It implements a complete trading pipeline: signal generation → confluence filtering → risk management → execution → position management → reflection-driven strategy evolution.

**Key Design Principles:**
- **Linux-native**: No MT5, no Wine, no Windows dependencies
- **Self-improving**: Deterministic reflection loop evolves strategy over time
- **Risk-first**: Multiple circuit breakers, position limits, and drawdown controls
- **Exchange-agnostic**: ccxt abstraction supports 105+ exchanges out of the box
- **Paper-first**: Safe by default; live trading requires explicit opt-in

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SITA Trading Pipeline                       │
│                                                                 │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────┐           │
│  │  Regime  │   │  Liquidity   │   │    Signal     │           │
│  │ Detector │   │  Analyzer    │   │   Engine      │           │
│  │(5 regimes)│   │(zones, FVG) │   │(7 strategies) │           │
│  └────┬─────┘   └──────┬───────┘   └──────┬────────┘           │
│       │                │                   │                    │
│       └────────────────┼───────────────────┘                    │
│                        │                                        │
│                        ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Confluence Filter (9-Dimension)             │   │
│  │  Level(18%) + Trend(17%) + Momentum(15%) + BOS(12%)     │   │
│  │  + OrderBlock(12%) + Timing(10%) + Structure(8%)         │   │
│  │  + SessionORB(8%) = Score 0-100                         │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   Risk Manager                           │   │
│  │  Position sizing → SL/TP calc → Limit checks → Decision  │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               Exchange Executor (ccxt)                   │   │
│  │         Binance │ Bybit │ OKX │ Kraken │ 105+            │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                Position Manager                          │   │
│  │     Breakeven → Trailing Stop → Profit Profiling          │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                Reflection Engine                         │   │
│  │  Score → Hypothesize → Apply 1 change → Version strategy │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Discord Notifier │ Dashboard (port 8090) │ Journal      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Component Deep-Dive

### 1. Signal Engine (`sita/signal/`)

The signal engine implements 7 distinct trading strategies, each optimized for different market conditions:

| Strategy | Best For | Core Indicators | Signal Type |
|----------|----------|-----------------|-------------|
| EMA Crossover | Trending markets | EMA 9/21/55 | Trend |
| SMA Crossover | Smooth trends | SMA 20/50/200 | Trend |
| Momentout Breakout | Strong moves | RSI + Volume | Breakout |
| Scalping | Ranging/choppy | Bollinger Bands + RSI | Mean-reversion |
| Trend Following | Strong trends | ADX + EMA | Trend |
| Mean Reversion | Ranging | RSI extremes + BB | Reversal |
| RSI Reversal | Overextended | RSI divergence | Reversal |

**Multi-Strategy Fallback**: When the primary strategy produces low-confidence signals, the fallback engine blends signals from all 7 strategies using weighted voting. The weight of each strategy is inversely proportional to its recent loss rate.

**Regime-Aware Filtering**: The signal engine receives regime recommendations from the RegimeDetector and filters signals accordingly. For example, short signals are blocked during strong uptrends.

### 2. Confluence Filter (`sita/confluence/`)

Every signal must pass through a 9-dimension quality gate. Each dimension is scored 0-1 and weighted to produce a final score 0-100:

| Dimension | Weight | Measurement |
|-----------|--------|-------------|
| Level Proximity | 18% | Distance to key S/R levels, round numbers, EMA proximity |
| Trend Alignment | 17% | Signal direction vs. macro trend (EMA stack, higher highs/lows) |
| Momentum | 15% | RSI confirmation, MACD histogram direction |
| Break of Structure | 12% | BOS/CHoCH detection in price action |
| Order Block | 12% | ICT Order Block proximity and alignment |
| Timing | 10% | Session timing, volume timing |
| Market Structure | 8% | Higher highs/lows, lower highs/lows |
| Opening Range | 8% | ORB breakout confirmation |

**Score Interpretation:**
- **85+ (Premium)**: Full position size (1.0x multiplier)
- **70-84 (Good)**: Reduced size (0.85x multiplier)
- **50-69 (Marginal)**: Minimum size (0.6x), may wait for better entry
- **20-49 (Poor)**: Minimum size (0.3x), wait for pullback
- **<20 (Reject)**: No trade

### 3. Risk Manager (`sita/risk/`)

The risk manager implements a **%R (Percent Risk)** position sizing model:

```
position_size = (balance × risk_pct × confluence_mult) / sl_distance
```

**Position Sizing Rules:**
1. Risk per trade: 0.5-2% of balance (adaptive by account size tier)
2. Minimum notional: $5.00 (Binance futures requirement)
3. Maximum notional: 35% of balance per position
4. Recovery mode: 50% risk reduction after drawdown threshold

**Account Size Tiers:**

| Tier | Balance | Risk Per Trade |
|------|---------|----------------|
| Tiny | ≤ $1,000 | 0.5% |
| Small | ≤ $5,000 | 1.0% |
| Medium | ≤ $20,000 | 1.5% |
| Large | > $20,000 | 2.0% |

**Circuit Breakers:**

| Limit | Threshold | Action |
|-------|-----------|--------|
| Daily Loss | 3% of initial balance | Stop trading for the day |
| Weekly Loss | 5% of initial balance | Stop trading for the week |
| Total Drawdown | 10% of peak balance | Hard stop, kill all positions |
| Recovery Mode | 5% drawdown | 50% risk reduction |

**SL/TP Calculation:**
- Stop Loss: ATR-based, 1.5x ATR from entry
- Take Profit: Risk:Reward based, default 1:2 (TP = 2 × SL distance)

### 4. Exchange Executor (`sita/execution/`)

The execution layer wraps ccxt to provide a unified interface for:

- **Market orders**: Immediate execution at current price
- **Limit orders**: Execution at specified price
- **Stop-loss orders**: Stop-market orders for position protection
- **Take-profit orders**: Take-profit-market orders for profit capture
- **Position queries**: Fetch open positions, account balance

**Paper Trading Mode:**
- Simulates orders locally without exchange connection
- Generates synthetic OHLCV data using geometric Brownian motion with regime behavior
- Tracks paper balance and positions in memory

**Live Trading Mode:**
- Connects to real exchange via ccxt
- Requires API key/secret and `SITA_I_ACCEPT_RISK=true`
- Enforces exchange-specific minimums (e.g., Binance $5 notional minimum)

**Supported Exchanges (105+):**
- Pre-configured: Binance (futures), Bybit (linear), OKX (swap), Kraken (spot)
- All ccxt-supported exchanges work with minimal configuration

### 5. Position Manager (`sita/position/`)

Manages open positions with three advanced features:

**Dynamic Breakeven:**
When position reaches 1R profit, stop loss is moved to entry price + spread. This eliminates risk on winning trades.

**Trailing Stop:**
After 2R profit, stop loss trails at 1.5x ATR below current price (for longs). Locks in profits while allowing room for continuation.

**Profit Profiling:**
Partial closes at predetermined targets:
- 1R: Close 25% of position
- 2R: Close 25% of position
- 3R: Close remaining 50%

### 6. Regime Detector (`sita/regime/`)

Classifies the current market into one of 5 regimes using ADX, RSI, and price structure:

| Regime | ADX Range | Characteristics | Strategy Bias |
|--------|-----------|-----------------|---------------|
| Trending Strong | > 25 | Clear directional momentum | Trend Following |
| Trending Weak | 15-25 | Loose structure, moderate momentum | EMA Crossover |
| Ranging | < 15 | Bounded price action | Scalping / Mean Reversion |
| Volatile | ATR spike | Wide ranges, erratic moves | Reduce size / wait |
| Reversal | RSI extreme + divergence | Potential trend change | Mean Reversion |

Confidence levels (high/medium/low) are assigned based on indicator agreement.

### 7. Liquidity Analyzer (`sita/regime/`)

Identifies key liquidity zones that act as magnets for price:

- **Stop Hunt Zones**: Areas where retail stops cluster (below recent lows, above recent highs)
- **Fair Value Gaps (FVG)**: Imbalance zones from aggressive moves
- **Volume Nodes**: Price levels with historically high volume
- **Liquidity Bias**: Bullish/bearish/neutral based on zone distribution

### 8. Reflection Engine (`sita/reflection/`)

The self-improvement loop that makes SITA "self-improving":

**Cycle Trigger**: Every N closed trades (default: 5)

**Process:**
1. **Score**: Calculate performance score based on win rate, profit factor, drawdown, Sharpe
2. **Hypothesize**: Generate candidate strategy changes (one variable at a time)
3. **Select**: Pick the highest-impact hypothesis
4. **Apply**: Modify strategy.yaml with the change
5. **Version**: Save prior version to history/ with timestamp
6. **Log**: Record hypothesis with reasoning in hypotheses.jsonl

**Hypothesis Types:**
- Disable consistently losing symbols
- Adjust SL tightness (±0.5%)
- Change entry indicator threshold
- Adjust position size multiplier
- Allow/disallow directional bias
- Switch primary strategy type

**Modes:**
- **Deterministic Fallback**: Rule-based, no LLM required. Uses performance heuristics.
- **Hermes LLM**: Natural language reasoning for complex strategy evolution (production mode)

### 9. Discord Notifier (`sita/journal/`)

Posts rich embed notifications to Discord channels:

| Event | Channel | Content |
|-------|---------|---------|
| Startup | alerts | Version, mode, balance, watchlist |
| Trade Entry | alerts | Symbol, side, size, entry, SL, TP |
| Trade Exit | alerts | Symbol, side, P&L, reason |
| Signal | signals | Symbol, direction, confidence, confluence |
| Health | health | Balance, positions, win rate, P&L |
| Reflection | journal | Hypothesis, score, version, reasoning |
| Daily Report | reports | Trades, win rate, P&L, recent history |

**Delivery Methods:**
1. **Webhook** (preferred): Simple POST to Discord webhook URL
2. **Bot API** (fallback): Uses bot token + channel ID for thread creation

### 10. Dashboard (`sita/dashboard/`)

Real-time web dashboard at `http://localhost:8090`:

- Equity curve (live updating)
- Open positions with live P&L
- Trade history table
- Confluence score history
- Risk gauge (daily/weekly/total usage)
- Reflection log
- Regime indicator

## Data Flow

```
Exchange API (ccxt)
       │
       ▼
┌──────────────┐
│  OHLCV Data  │──────┐
└──────────────┘      │
                      ▼
              ┌──────────────┐
              │ Regime Detect│──→ Strategy recommendation
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │   Liquidity  │──→ Zone levels, bias
              │   Analyzer   │
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │    Signal    │──→ Direction, confidence
              │   Engine     │
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │  Confluence  │──→ Score 0-100, position mult
              │   Filter     │
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │    Risk      │──→ Size, SL, TP, approve/reject
              │   Manager    │
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │  Execution   │──→ Order on exchange
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │   Position   │──→ BE, trailing, partial close
              │   Manager    │
              └──────────────┘
                      │
                      ▼
              ┌──────────────┐
              │  Reflection  │──→ Strategy evolution
              └──────────────┘
```

## State Management

All state is stored as flat files in `state/`:

| File | Format | Purpose |
|------|--------|---------|
| `strategy.yaml` | YAML | Current strategy parameters (auto-evolved) |
| `goal.yaml` | YAML | Trading goals (return, drawdown, Sharpe) |
| `trades.jsonl` | JSONL | Complete trade history with P&L |
| `hypotheses.jsonl` | JSONL | Reflection log with reasoning |
| `history/` | YAML | Every prior strategy version (audit trail) |

**Why flat files?**
- Human-readable and auditable
- No database dependency
- Easy to version with git
- Survives container restarts (when mounted as volume)

## Configuration

Configuration is loaded in this order (later overrides earlier):

1. **Defaults** in `config.py` (DEFAULT_RISK_LIMITS, ENTRY_THRESHOLDS, etc.)
2. **Environment variables** (SITA_EXCHANGE, SITA_TRADING_MODE, etc.)
3. **`.env` file** (loaded before any config import via `load_dotenv()`)
4. **Runtime config dict** passed to SITA constructor

**Critical**: `load_dotenv()` runs BEFORE any config module imports because config reads `os.getenv()` at module level.

## Safety Architecture

SITA has multiple layers of protection:

1. **Default-deny**: Paper mode by default; live requires two explicit flags
2. **Confluence gate**: Low-quality signals are rejected before reaching risk
3. **Risk limits**: Daily/weekly/total circuit breakers
4. **Position limits**: Max concurrent positions, max per symbol
5. **Symbol disabling**: Reflection can disable consistently losing symbols
6. **Recovery mode**: Auto risk reduction after drawdown
7. **Version control**: Every strategy change is saved with rollback capability
8. **Audit trail**: Complete trade + hypothesis history

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
railway up
```

Set environment variables in Railway dashboard for API keys and mode.

## Performance Characteristics

From dry-run testing (38 trades, $10K paper):
- Win rate: 65.8%
- Total P&L: $1,391.82
- Max drawdown: 0.59%
- Strategy evolved: v01 → v07 in 5 reflection cycles
- Best performers: SOL shorts, BTC trend trades
- Disabled by reflection: ETH (consistent losses)
