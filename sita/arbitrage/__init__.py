"""
SITA — Arbitrage Engine
Spot-Futures basis trading + cross-exchange arbitrage.

Strategies:
1. Spot-Futures Basis: Buy spot, sell perpetual futures → capture funding rate
2. Cross-Exchange: Buy on exchange A, sell on exchange B when spread > threshold
3. Triangular: USDT → ETH → BTC → USDT cycle for geometric arbitrage

The key insight: funding rates on perpetual futures are often +0.01% to +0.1% per 8h.
By holding spot long + perp short, you earn funding with minimal directional risk.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger("sita.arbitrage")


class ArbStrategy(Enum):
    SPOT_FUTURES_BASIS = "spot_futures_basis"
    CROSS_EXCHANGE = "cross_exchange"
    TRIANGULAR = "triangular"


@dataclass
class FundingRate:
    """Current funding rate for a perpetual contract."""
    symbol: str
    rate: float              # e.g. 0.0001 = 0.01%
    next_funding: int        # unix ms of next funding timestamp
    predicted_rate: float = 0.0  # predicted next rate (if available)

    @property
    def apy(self) -> float:
        """Annualized funding rate (3 payments/day)."""
        return self.rate * 3 * 365

    @property
    def hours_to_funding(self) -> float:
        return max(0, (self.next_funding / 1000 - time.time())) / 3600


@dataclass
class BasisOpportunity:
    """A spot-futures basis arbitrage opportunity."""
    symbol: str              # e.g. "ETH"
    spot_price: float
    futures_price: float
    basis_pct: float          # (futures - spot) / spot * 100
    funding_rate: float       # current funding rate
    estimated_apr: float      # estimated annual return from funding
    confidence: float         # 0-1
    timestamp: str = ""

    @property
    def is_favorable(self) -> bool:
        """Is the basis trade worth it after costs?"""
        # Pure funding play: positive funding rate earns yield even with 0% basis
        # 0.00001 = 0.001% per 8h ≈ 0.11% APY (3 payments/day * 365)
        # Any positive funding is profitable after fees (0.2% round-trip)
        if self.funding_rate > 0.00001 and self.confidence > 0.1:
            return True
        # Basis + funding play: both must be meaningful
        return self.funding_rate > 0.00005 and self.confidence > 0.5


@dataclass
class CrossExchangeOpportunity:
    """Cross-exchange price discrepancy."""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float         # (sell - buy) / buy * 100
    estimated_profit: float   # after fees
    confidence: float
    timestamp: str = ""


@dataclass
class ArbitrageState:
    """Tracks active arbitrage positions."""
    active_trades: Dict[str, Dict] = field(default_factory=dict)
    total_funding_earned: float = 0.0
    total_arb_profit: float = 0.0
    trade_count: int = 0
    last_scan: str = ""


class ArbitrageEngine:
    """
    Spot-Futures basis arbitrage + cross-exchange scanner.

    For a small account (~$10), the most practical play is:
    - Spot-Futures basis: Buy $10 spot ETH, sell $10 perp ETH → earn funding
    - This is delta-neutral (no directional risk)
    - Funding is collected every 8 hours
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.state = ArbitrageState()
        self.min_basis_pct = self.config.get("min_basis_pct", 0.05)     # 0.05% min basis
        self.min_funding_rate = self.config.get("min_funding_rate", 0.00005)  # 0.005% per 8h
        self.fee_pct = self.config.get("fee_pct", 0.001)                # 0.1% per trade (0.2% round-trip)
        self.exchanges: Dict[str, Any] = {}  # ccxt exchange instances
        logger.info("ArbitrageEngine initialized")

    def register_exchange(self, name: str, exchange: Any) -> None:
        """Register a ccxt exchange instance for scanning."""
        self.exchanges[name] = exchange
        logger.info(f"Exchange registered: {name}")

    def scan_spot_futures_basis(self, symbol: str, spot_exchange=None, futures_exchange=None) -> Optional[BasisOpportunity]:
        """
        Scan for spot-futures basis opportunity.
        symbol: base asset like "ETH" (will fetch ETH/USDT spot and ETH/USDT:USDT futures)
        """
        try:
            spot_ex = spot_exchange or self.exchanges.get("binance")
            futures_ex = futures_exchange or self.exchanges.get("binance")

            if not spot_ex or not futures_ex:
                logger.warning("No exchanges registered for basis scan")
                return None

            # Fetch spot price
            spot_ticker = spot_ex.fetch_ticker(f"{symbol}/USDT")
            spot_price = float(spot_ticker["last"])

            # Fetch futures price
            futures_ticker = futures_ex.fetch_ticker(f"{symbol}/USDT:USDT")
            futures_price = float(futures_ticker["last"])

            # Fetch funding rate
            funding = self._fetch_funding_rate(futures_ex, f"{symbol}/USDT:USDT")

            # Calculate basis
            basis_pct = (futures_price - spot_price) / spot_price * 100

            # Confidence based on data freshness and spread
            # Also factor in funding rate magnitude
            basis_conf = min(abs(basis_pct) / self.min_basis_pct, 1.0) if abs(basis_pct) > 0.01 else 0.0
            funding_conf = min(funding.apy / 0.10, 1.0) if funding and funding.apy > 0 else 0.0
            confidence = max(basis_conf, funding_conf)

            opp = BasisOpportunity(
                symbol=symbol,
                spot_price=spot_price,
                futures_price=futures_price,
                basis_pct=basis_pct,
                funding_rate=funding.rate if funding else 0.0,
                estimated_apr=funding.apy if funding else 0.0,
                confidence=confidence,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            if opp.is_favorable:
                logger.info(f"BASIS OPP: {symbol} spot={spot_price}, fut={futures_price}, "
                           f"basis={basis_pct:.3f}%, funding={funding.rate:.6f}, apy={funding.apy*100:.1f}%")
            else:
                logger.debug(f"Basis scan {symbol}: basis={basis_pct:.3f}%, funding={funding.rate if funding else 'N/A'}")

            return opp

        except Exception as e:
            logger.error(f"Basis scan failed for {symbol}: {e}")
            return None

    def _fetch_funding_rate(self, exchange, symbol: str) -> Optional[FundingRate]:
        """Fetch current funding rate for a perpetual contract."""
        try:
            # Generic ccxt method (works reliably for Binance)
            if hasattr(exchange, 'fetch_funding_rate'):
                data = exchange.fetch_funding_rate(symbol)
                return FundingRate(
                    symbol=symbol,
                    rate=float(data.get('fundingRate', 0)),
                    next_funding=int(data.get('fundingTimestamp', 0)),
                    predicted_rate=float(data.get('fundingRate', 0)),
                )
            # Binance raw API fallback — returns a LIST of rate entries, take the latest
            if hasattr(exchange, 'fapiPublicGetFundingRate'):
                raw = exchange.fapiPublicGetFundingRate({'symbol': symbol.replace('/', '')})
                if isinstance(raw, list) and raw:
                    # List is sorted by fundingTime descending — first entry is latest
                    data = raw[0]
                    return FundingRate(
                        symbol=symbol,
                        rate=float(data.get('fundingRate', 0)),
                        next_funding=int(data.get('fundingTime', 0)),
                    )
                elif isinstance(raw, dict):
                    return FundingRate(
                        symbol=symbol,
                        rate=float(raw.get('lastFundingRate', 0)),
                        next_funding=int(raw.get('nextFundingTime', 0)),
                    )
        except Exception as e:
            logger.debug(f"Funding rate fetch failed: {e}")
        return None

    def scan_cross_exchange(self, symbol: str = "ETH/USDT") -> List[CrossExchangeOpportunity]:
        """Scan for price differences across registered exchanges."""
        opportunities = []
        prices: Dict[str, float] = {}

        for name, ex in self.exchanges.items():
            try:
                ticker = ex.fetch_ticker(symbol)
                prices[name] = float(ticker["last"])
            except Exception as e:
                logger.debug(f"Price fetch failed for {name}: {e}")

        if len(prices) < 2:
            return opportunities

        # Find best buy (lowest) and best sell (highest)
        exchange_names = list(prices.keys())
        for i, buy_ex in enumerate(exchange_names):
            for sell_ex in exchange_names[i+1:]:
                buy_price = prices[buy_ex]
                sell_price = prices[sell_ex]

                if sell_price > buy_price:
                    spread_pct = (sell_price - buy_price) / buy_price * 100
                    profit_after_fees = (spread_pct / 100 - self.fee_pct * 2) * buy_price

                    if spread_pct > self.min_basis_pct:
                        opportunities.append(CrossExchangeOpportunity(
                            symbol=symbol,
                            buy_exchange=buy_ex,
                            sell_exchange=sell_ex,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            spread_pct=spread_pct,
                            estimated_profit=profit_after_fees,
                            confidence=min(spread_pct / (self.min_basis_pct * 2), 1.0),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ))

        return sorted(opportunities, key=lambda o: o.spread_pct, reverse=True)

    def execute_basis_trade(self, symbol: str, size_usdt: float,
                           spot_exchange=None, futures_exchange=None) -> Dict:
        """
        Execute spot-futures basis trade:
        1. Buy spot (long) with USDT
        2. Sell perpetual futures (short) with same notional
        → Delta-neutral, earn funding rate
        """
        result = {"success": False, "symbol": symbol, "size_usdt": size_usdt, "errors": []}

        try:
            spot_ex = spot_exchange or self.exchanges.get("binance")
            futures_ex = futures_exchange or self.exchanges.get("binance")

            if not spot_ex or not futures_ex:
                result["errors"].append("No exchanges registered")
                return result

            # Check if we can use spot trading on Binance
            spot_symbol = f"{symbol}/USDT"
            futures_symbol = f"{symbol}/USDT:USDT"

            # Get current prices
            spot_price = float(spot_ex.fetch_ticker(spot_symbol)["last"])
            futures_price = float(futures_ex.fetch_ticker(futures_symbol)["last"])

            # Calculate position size
            spot_size = size_usdt / spot_price
            futures_size = size_usdt / futures_price

            # Step 1: Buy spot
            logger.info(f"ARB: Buying {spot_size:.6f} {symbol} spot @ {spot_price}")
            spot_order = spot_ex.create_market_buy_order(spot_symbol, spot_size)
            logger.info(f"ARB: Spot buy filled: {spot_order.get('id', 'unknown')}")

            # Step 2: Sell futures (short)
            logger.info(f"ARB: Selling {futures_size:.6f} {symbol} futures @ {futures_price}")
            # For futures short, we need position side
            futures_order = futures_ex.create_market_sell_order(
                futures_symbol, futures_size,
                None,
                {"positionSide": "SHORT"}
            )
            logger.info(f"ARB: Futures short filled: {futures_order.get('id', 'unknown')}")

            # Record the trade
            trade_id = f"arb_{int(time.time())}"
            self.state.active_trades[trade_id] = {
                "symbol": symbol,
                "spot_size": spot_size,
                "futures_size": futures_size,
                "spot_entry": spot_price,
                "futures_entry": futures_price,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "funding_collected": 0.0,
            }
            self.state.trade_count += 1

            result["success"] = True
            result["trade_id"] = trade_id
            result["spot_order_id"] = spot_order.get("id", "")
            result["futures_order_id"] = futures_order.get("id", "")
            result["spot_price"] = spot_price
            result["futures_price"] = futures_price

            logger.info(f"ARB TRADE OPENED: {trade_id} — {symbol} basis trade, "
                       f"spot={spot_price}, futures={futures_price}")

        except Exception as e:
            logger.error(f"ARB trade execution failed: {e}")
            result["errors"].append(str(e))

        return result

    def close_basis_trade(self, trade_id: str, spot_exchange=None, futures_exchange=None) -> Dict:
        """Close a basis trade: sell spot, buy back futures."""
        result = {"success": False, "trade_id": trade_id}

        trade = self.state.active_trades.get(trade_id)
        if not trade:
            result["error"] = "Trade not found"
            return result

        try:
            spot_ex = spot_exchange or self.exchanges.get("binance")
            futures_ex = futures_exchange or self.exchanges.get("binance")

            symbol = trade["symbol"]
            spot_symbol = f"{symbol}/USDT"
            futures_symbol = f"{symbol}/USDT:USDT"

            # Sell spot
            spot_ex.create_market_sell_order(spot_symbol, trade["spot_size"])
            # Buy back futures short
            close_params = {"positionSide": "SHORT"}
            if spot_ex._hedge_mode if hasattr(spot_ex, '_hedge_mode') else False:
                close_params["reduceOnly"] = True
            futures_ex.create_market_buy_order(
                futures_symbol, trade["futures_size"],
                None,
                close_params
            )

            del self.state.active_trades[trade_id]
            result["success"] = True
            logger.info(f"ARB TRADE CLOSED: {trade_id}")

        except Exception as e:
            logger.error(f"ARB close failed: {e}")
            result["error"] = str(e)

        return result

    def get_active_trades(self) -> Dict[str, Dict]:
        return self.state.active_trades.copy()

    def get_state_summary(self) -> Dict:
        return {
            "active_trades": len(self.state.active_trades),
            "total_funding_earned": self.state.total_funding_earned,
            "total_arb_profit": self.state.total_arb_profit,
            "trade_count": self.state.trade_count,
            "last_scan": self.state.last_scan,
        }
