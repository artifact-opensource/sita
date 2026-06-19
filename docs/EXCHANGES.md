# SITA — Supported Exchanges

SITA uses **ccxt** under the hood, which supports **105+ exchanges**. Below is the full list organized by category.

## Pre-Configured (Testnet + Paper Trading Ready)

These 4 exchanges are pre-configured in `src/config.py` with testnet URLs and default trading types:

| Exchange | ID | Paper | Type | Notes |
|----------|----|-------|------|-------|
| Binance | `binance` | ✅ | Futures | Largest liquidity, deep testnet |
| Bybit | `bybit` | ✅ | Linear | Good for perps, solid API |
| OKX | `okx` | ✅ | Swap | Strong altcoin selection |
| Kraken | `kraken` | ❌ | Spot | Regulated, good for EUR/USD |

## All Supported Exchanges

### Crypto Major (50)

| Exchange | ID | Category |
|----------|----|----------|
| Binance | `binance` | CEX — Largest spot + futures |
| Binance Coin-M | `binancecoinm` | CEX — Coin-margined futures |
| Binance US | `binanceus` | CEX — US-regulated spot |
| Binance USDM | `binanceusdm` | CEX — US-regulated futures |
| BingX | `bingx` | CEX — Copy trading + perps |
| Bitfinex | `bitfinex` | CEX — Old school, deep liquidity |
| Bitflyer | `bitflyer` | CEX — Japan-regulated |
| Bitget | `bitget` | CEX — Copy trading, strong perps |
| Bithumb | `bithumb` | CEX — Korea-regulated |
| BitMEX | `bitmex` | CEX — Perps pioneer |
| Bitso | `bitso` | CEX — Mexico/LatAm |
| Bitstamp | `bitstamp` | CEX — EU-regulated, old school |
| BTC Markets | `btcmarkets` | CEX — Australia-regulated |
| Bybit | `bybit` | CEX — Perps + copy trading |
| Bybit EU | `bybiteu` | CEX — EU-regulated Bybit |
| Coinbase | `coinbase` | CEX — US-regulated, public company |
| Coinbase Exchange | `coinbaseexchange` | CEX — Coinbase pro |
| Coinbase International | `coinbaseinternational` | CEX — International derivatives |
| Coincheck | `coincheck` | CEX — Japan-regulated |
| CoinEX | `coinex` | CEX — Altcoin focus |
| CoinSpot | `coinspot` | CEX — Australia-regulated |
| Crypto.com | `cryptocom` | CEX — Card + exchange |
| Deepcoin | `deepcoin` | CEX — Perps |
| Delta | `delta` | CEX — India-regulated |
| Deribit | `deribit` | CEX — Options + perps (BTC/ETH) |
| Extended | `extended` | CEX — Perps |
| Foxbit | `foxbit` | CEX — Brazil-regulated |
| Gate.io | `gate` | CEX — Altcoin king |
| Gemini | `gemini` | CEX — US-regulated, insured |
| HitBTC | `hitbtc` | CEX — Old school, wide selection |
| Independent Reserve | `independentreserve` | CEX — Australia/NZ-regulated |
| Kraken | `kraken` | CEX — US/EU-regulated |
| Kraken Futures | `krakenfutures` | CEX — Regulated futures |
| KuCoin | `kucoin` | CEX — Altcoin selection |
| KuCoin Futures | `kucoinfutures` | CEX — Perps |
| LBank | `lbank` | CEX — Altcoin focus |
| Mercado Bitcoin | `mercado` | CEX — Brazil-regulated |
| MEXC | `mexc` | CEX — Altcoin focus, no KYC |
| OKX | `okx` | CEX — Perps + altcoins |
| OKX US | `okxus` | CEX — US-regulated OKX |
| Phemex | `phemex` | CEX — Perps, no KYC |
| Poloniex | `poloniex` | CEX — Old school altcoins |
| Upbit | `upbit` | CEX — Korea-regulated |
| WhiteBIT | `whitebit` | CEX — EU-regulated |
| WOO X | `woo` | CEX — Institutional + retail |
| WOO Pro | `woofipro` | CEX — Pro trading |
| XT.com | `xt` | CEX — Altcoin focus |
| Zaif | `zaif` | CEX — Japan-regulated |

### Crypto Other (49)

| Exchange | ID | Category |
|----------|----|----------|
| Aftermath | `aftermath` | DEX — Perps |
| Apex | `apex` | DEX — Perps |
| AscendEX | `ascendex` | CEX — Altcoin focus |
| Aster | `aster` | DEX — Perps |
| Backpack | `backpack` | CEX — Solana ecosystem |
| Bequant | `bequant` | CEX — Institutional |
| Bit2C | `bit2c` | CEX — Israel-regulated |
| Bitbank | `bitbank` | CEX — Japan-regulated |
| Bitbns | `bitbns` | CEX — India-regulated |
| BitMart | `bitmart` | CEX — Altcoin focus |
| Bitopro | `bitopro` | CEX — Taiwan-regulated |
| Bitrue | `bitrue` | CEX — Altcoin focus |
| BitTeam | `bitteam` | CEX — EU |
| BitTrade | `bittrade` | CEX — Japan |
| Bitvavo | `bitvavo` | CEX — EU-regulated |
| Blockchain.com | `blockchaincom` | CEX — Wallet + exchange |
| Blofin | `blofin` | CEX — Perps |
| BTCBox | `btcbox` | CEX — Japan-regulated |
| BTCTurk | `btcturk` | CEX — Turkey-regulated |
| Bullish | `bullish` | CEX — Institutional |
| BYDFI | `bydfi` | CEX — Perps |
| CEX.IO | `cex` | CEX — Old school, EU |
| Coinmate | `coinmate` | CEX — EU-regulated |
| CoinMetro | `coinmetro` | CEX — EU-regulated |
| Coinone | `coinone` | CEX — Korea-regulated |
| Coins.ph | `coinsph` | CEX — Philippines-regulated |
| Cryptomus | `cryptomus` | CEX — Payment gateway |
| Derive | `derive` | DEX — Options |
| EXMO | `exmo` | CEX — EU/UK |
| FMFW.io | `fmfwio` | CEX — Perps |
| GRVT | `grvt` | DEX — Institutional perps |
| HashKey | `hashkey` | CEX — Hong Kong-regulated |
| Hibachi | `hibachi` | DEX — Perps |
| Hollaex | `hollaex` | CEX — White-label |
| HTX | `htx` | CEX — Old Huobi |
| Hyperliquid | `hyperliquid` | DEX — Perps leader |
| Indodax | `indodax` | CEX — Indonesia-regulated |
| Latoken | `latoken` | CEX — Altcoin focus |
| Luno | `luno` | CEX — Africa/UK/EU |
| NDAX | `ndax` | CEX — Canada-regulated |
| OneTrading | `onetrading` | CEX — EU-regulated |
| P2B | `p2b` | CEX — Altcoin focus |
| Pacifica | `pacifica` | DEX — Perps |
| Paradex | `paradex` | DEX — Perps (Starknet) |
| Paymium | `paymium` | CEX — France-regulated |
| Tokocrypto | `tokocrypto` | CEX — Indonesia-regulated |
| Toobit | `toobit` | CEX — Perps |
| Weex | `weex` | CEX — Perps |
| ZebPay | `zebpay` | CEX — India-regulated |

### Forex/CFD (3)

| Exchange | ID | Category |
|----------|----|----------|
| BigONE | `bigone` | CEX — Forex + crypto |
| Digifinex | `digifinex` | CEX — Forex + crypto |
| Lighter | `lighter` | DEX — Forex perps |

### Stocks (2)

| Exchange | ID | Category |
|----------|----|----------|
| Alpaca | `alpaca` | Broker — US stocks, commission-free |
| Mode Trade | `modetrade` | Broker — EU stocks |

### DeFi (1)

| Exchange | ID | Category |
|----------|----|----------|
| dYdX | `dydx` | DEX — Perps on dYdX chain |

## Adding a New Exchange

To add an exchange not pre-configured, add to `SUPPORTED_EXCHANGES` in `src/config.py`:

```python
"exchange_id": {
    "name": "Exchange Name",
    "paper_trading": True,       # Has testnet?
    "testnet_url": "https://...", # Testnet API URL
    "default_type": "future",    # spot, future, swap, linear
    "timeframes": ["1m", "5m", "15m", "1h", "4h", "1d"],
},
```

Then set `SITA_EXCHANGE=exchange_id` in your `.env` or Railway config.

## Recommended by Use Case

| Use Case | Recommended Exchange |
|----------|---------------------|
| **Crypto perps (largest liquidity)** | Binance, Bybit, OKX |
| **Crypto perps (no KYC)** | MEXC, Phemex, Bitget |
| **Crypto spot (regulated)** | Coinbase, Kraken, Bitstamp |
| **Altcoin hunting** | KuCoin, Gate.io, MEXC |
| **Options** | Deribit |
| **DeFi perps** | Hyperliquid, dYdX |
| **US stocks** | Alpaca |
| **Forex** | OANDA (manual setup) |
