"""
SITA — Execution Layer
Linux-native exchange execution via ccxt. No MT5. No Wine. No Windows.

Supports: Binance, Bybit, OKX, Kraken (and any ccxt exchange)
Modes: paper (testnet/simulation) and live
"""

from __future__ import annotations
import time
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import TRADING_MODE, DEFAULT_EXCHANGE, SUPPORTED_EXCHANGES

logger = logging.getLogger("sita.execution")


@dataclass
class OrderResult:
    """Result of an order submission."""
    success: bool
    order_id: str = ""
    symbol: str = ""
    side: str = ""
    size: float = 0.0
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    error: str = ""
    raw: Dict = field(default_factory=dict)
    timestamp: str = ""


class ExchangeExecutor:
    """
    Direct exchange execution via ccxt.
    Replaces the MT5 + webhook bridge that Cthulu used.

    Paper mode: uses testnet or simulates orders.
    Live mode: real orders on real exchange.
    """

    def __init__(self, exchange_id: str = None, config: Dict = None):
        self.exchange_id = exchange_id or DEFAULT_EXCHANGE
        self.config = config or {}
        self.mode = TRADING_MODE
        self.exchange = None
        self._paper_positions: Dict[str, Dict] = {}
        self._paper_balance: float = self.config.get("paper_balance", 10000.0)
        self._order_counter = 0

        self._init_exchange()

    def _is_futures_symbol(self, symbol: str) -> bool:
        """Check if a symbol is a futures contract (contains ':USDT')."""
        return ":USDT" in symbol

    def _get_symbol_type(self, symbol: str) -> str:
        """Get the ccxt type for a symbol: 'spot' or 'future'."""
        return "future" if self._is_futures_symbol(symbol) else "spot"

    def _init_exchange(self) -> None:
        """Initialize ccxt exchange connection."""
        try:
            import ccxt
            exchange_class = getattr(ccxt, self.exchange_id)

            exchange_config = {
                "enableRateLimit": True,
                "options": {"defaultType": SUPPORTED_EXCHANGES.get(self.exchange_id, {}).get("default_type", "spot")},
            }

            # Add API keys for live trading
            if self.mode == "live":
                import os
                api_key = (
                    self.config.get("api_key")
                    or self.config.get("EXCHANGE_API_KEY")
                    or self.config.get("BINANCE_API_KEY")
                    or os.getenv("EXCHANGE_API_KEY")
                    or os.getenv("BINANCE_API_KEY")
                )
                api_secret = (
                    self.config.get("api_secret")
                    or self.config.get("EXCHANGE_API_SECRET")
                    or self.config.get("BINANCE_SECRET")
                    or os.getenv("EXCHANGE_API_SECRET")
                    or os.getenv("BINANCE_SECRET")
                )
                if api_key and api_secret:
                    exchange_config["apiKey"] = api_key
                    exchange_config["secret"] = api_secret
                else:
                    logger.warning("Live mode but no API keys provided — falling back to paper")
                    self.mode = "paper"

            # Use testnet for paper trading
            if self.mode == "paper":
                testnet_url = SUPPORTED_EXCHANGES.get(self.exchange_id, {}).get("testnet_url")
                if testnet_url:
                    exchange_config["urls"] = {"api": testnet_url}

            self.exchange = exchange_class(exchange_config)

            # Detect position mode (one-way vs hedge)
            try:
                pos_mode = self.exchange.fapiPrivateGetPositionSideDual() if hasattr(self.exchange, 'fapiPrivateGetPositionSideDual') else {}
                self._hedge_mode = pos_mode.get('dualSidePosition', False)
            except Exception:
                self._hedge_mode = False
            logger.info(f"Exchange initialized: {self.exchange_id} ({self.mode}, hedge={self._hedge_mode})")

        except ImportError:
            logger.error("ccxt not installed. Run: pip install ccxt")
            self.exchange = None
        except Exception as e:
            logger.error(f"Exchange init failed: {e}")
            self.exchange = None

    def get_balance(self, currency: str = "USDT") -> float:
        """Get account balance."""
        if self.mode == "paper":
            return self._paper_balance

        if not self.exchange:
            return 0.0

        try:
            balance = self.exchange.fetch_balance()
            return float(balance.get("free", {}).get(currency, 0.0))
        except Exception as e:
            logger.error(f"Balance fetch failed: {e}")
            return 0.0

    def get_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 200) -> list:
        """Fetch OHLCV data. In paper mode without exchange, generates synthetic data."""
        if self.exchange:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                return [
                    {"timestamp": candle[0], "open": candle[1], "high": candle[2],
                     "low": candle[3], "close": candle[4], "volume": candle[5]}
                    for candle in ohlcv
                ]
            except Exception as e:
                logger.warning(f"OHLCV fetch failed for {symbol}: {e}")

        # Paper mode: generate synthetic data for testing
        if self.mode == "paper":
            return self._generate_synthetic_ohlcv(symbol, limit)

        return []

    def _generate_synthetic_ohlcv(self, symbol: str, limit: int = 200) -> list:
        """Generate realistic synthetic OHLCV data for paper trading tests."""
        import numpy as np
        import pandas as pd

        np.random.seed(hash(symbol) % 2**32)

        # Base price by symbol
        base_prices = {"BTC/USDT:USDT": 105000, "ETH/USDT:USDT": 3500, "SOL/USDT:USDT": 150}
        base = base_prices.get(symbol, 100)

        # Generate realistic price action
        returns = np.random.normal(0.0001, 0.003, limit)
        # Add some regime behavior
        trend = np.sin(np.linspace(0, 4*np.pi, limit)) * 0.001
        returns += trend

        price = base * np.exp(np.cumsum(returns))

        now = int(pd.Timestamp.now().timestamp() * 1000)
        interval_ms = 15 * 60 * 1000  # 15 minutes

        data = []
        for i in range(limit):
            ts = now - (limit - i) * interval_ms
            p = price[i]
            noise = np.random.normal(0, 0.001)
            o = p * (1 + noise)
            h = p * (1 + abs(np.random.normal(0, 0.002)))
            l = p * (1 - abs(np.random.normal(0, 0.002)))
            c = p * (1 + np.random.normal(0, 0.001))
            v = np.random.uniform(100, 1000)
            data.append({"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": v})

        return data

    def get_current_price(self, symbol: str) -> float:
        """Get current market price."""
        if self.mode == "paper" and self._paper_positions.get(symbol):
            return self._paper_positions[symbol].get("entry_price", 0.0)

        if not self.exchange:
            return 0.0

        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker.get("last", 0.0))
        except Exception as e:
            logger.error(f"Price fetch failed for {symbol}: {e}")
            return 0.0

    def place_order(
        self,
        symbol: str,
        side: str,         # 'buy' or 'sell'
        size: float,
        order_type: str = "market",
        price: float = 0.0,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
    ) -> OrderResult:
        """
        Place an order on the exchange.
        In paper mode, simulates the order locally.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if self.mode == "paper":
            return self._place_paper_order(symbol, side, size, price, stop_loss, take_profit, timestamp)

        if not self.exchange:
            return OrderResult(success=False, error="Exchange not initialized", timestamp=timestamp)

        try:
            is_futures = self._is_futures_symbol(symbol)
            symbol_type = self._get_symbol_type(symbol)

            # Enforce minimum notional (Binance Futures >= $5)
            if is_futures:
                min_notional = SUPPORTED_EXCHANGES.get(self.exchange_id, {}).get("min_notional", 5.0)
            else:
                min_notional = 10.0  # Binance spot minimum notional ~$10 USDT

            order_price = price if price > 0 else self.get_current_price(symbol)
            notional = size * order_price
            if notional < min_notional:
                min_size = min_notional / order_price
                current_bal = self.get_balance()
                max_size = (current_bal * 0.55) / order_price
                logger.info(f"Notional check: notional=${notional:.2f}, min=${min_notional}, min_size={min_size:.4f}, max_size={max_size:.4f}, bal={current_bal:.2f}")
                if min_size <= max_size:
                    logger.info(f"Position size {size} too small (notional ${notional:.2f} < ${min_notional}), scaling up to {min_size:.4f}")
                    size = min_size
                else:
                    logger.info(f"Order skipped: notional ${notional:.2f} < ${min_notional} min, scaled size {min_size:.4f} exceeds 50% cap")
                    return OrderResult(success=False, error=f"Notional too small (${notional:.2f} < ${min_notional}), account too small to scale", timestamp=timestamp)

            # Round up to exchange step size (BNB=0.01, AVAX=1, ADA=0.01, etc.)
            if self.exchange and is_futures:
                try:
                    market = self.exchange.market(symbol)
                    step_size = market.get("limits", {}).get("amount", {}).get("min", 0)
                    if step_size > 0:
                        import math
                        size = math.ceil(size / step_size) * step_size
                        size = round(size, 8)
                except Exception:
                    pass

            # Build order params — spot has no positionSide
            if is_futures:
                position_side = "LONG" if side == "buy" else "SHORT"
                order_params = {"positionSide": position_side}
            else:
                order_params = {}

            # Set default type for this symbol
            self.exchange.options["defaultType"] = symbol_type

            # Place the main order
            if order_type == "market":
                order = self.exchange.create_market_order(symbol, side, size, None, order_params)
            elif order_type == "limit":
                order = self.exchange.create_limit_order(symbol, side, size, price, order_params)
            else:
                return OrderResult(success=False, error=f"Unsupported order type: {order_type}", timestamp=timestamp)

            order_id = str(order.get("id", ""))

            # Set SL/TP if supported (futures only — spot uses local monitoring)
            if is_futures and (stop_loss > 0 or take_profit > 0):
                try:
                    sl_tp_side = "sell" if side == "buy" else "buy"
                    sl_tp_position = "LONG" if sl_tp_side == "sell" else "SHORT"
                    sl_tp_params = {"positionSide": sl_tp_position}
                    if self._hedge_mode:
                        sl_tp_params["reduceOnly"] = True
                    if stop_loss > 0:
                        self.exchange.create_order(symbol, "stop_market", sl_tp_side, size, None, {**sl_tp_params, "stopPrice": stop_loss})
                    if take_profit > 0:
                        self.exchange.create_order(symbol, "take_profit_market", sl_tp_side, size, None, {**sl_tp_params, "stopPrice": take_profit})
                except Exception as e:
                    logger.warning(f"SL/TP order failed: {e}")

            logger.info(f"Order placed: {side} {size} {symbol} @ market (id={order_id}, type={symbol_type})")

            return OrderResult(
                success=True,
                order_id=order_id,
                symbol=symbol,
                side=side,
                size=size,
                price=float(order.get("price", 0)),
                stop_loss=stop_loss,
                take_profit=take_profit,
                raw=order,
                timestamp=timestamp,
            )

        except Exception as e:
            logger.error(f"Order failed: {e}")
            return OrderResult(success=False, error=str(e), symbol=symbol, side=side, size=size, timestamp=timestamp)

    def _place_paper_order(
        self, symbol, side, size, price, stop_loss, take_profit, timestamp
    ) -> OrderResult:
        """Simulate an order in paper mode."""
        self._order_counter += 1
        order_id = f"paper_{self._order_counter}"

        # Get current price as fill price
        if price <= 0:
            price = self.get_current_price(symbol)
            if price <= 0:
                price = 1.0  # Fallback for testing

        # Deduct from paper balance
        cost = size * price
        if side == "buy" and cost > self._paper_balance:
            return OrderResult(success=False, error="Insufficient paper balance", timestamp=timestamp)

        if side == "buy":
            self._paper_balance -= cost
        else:
            self._paper_balance += cost

        # Track position
        self._paper_positions[symbol] = {
            "side": side,
            "size": size,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "order_id": order_id,
            "timestamp": timestamp,
        }

        logger.info(f"PAPER ORDER: {side} {size} {symbol} @ {price} (balance={self._paper_balance:.2f})")

        return OrderResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            side=side,
            size=size,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            timestamp=timestamp,
        )

    def close_position(self, symbol: str) -> OrderResult:
        """Close an open position."""
        timestamp = datetime.now(timezone.utc).isoformat()

        if self.mode == "paper":
            pos = self._paper_positions.get(symbol)
            if not pos:
                return OrderResult(success=False, error="No paper position", timestamp=timestamp)

            current_price = self.get_current_price(symbol)
            pnl = (current_price - pos["entry_price"]) * pos["size"]
            if pos["side"] == "sell":
                pnl = -pnl

            self._paper_balance += pos["size"] * current_price
            del self._paper_positions[symbol]

            logger.info(f"PAPER CLOSE: {symbol} PnL={pnl:.2f}")
            return OrderResult(success=True, symbol=symbol, size=pos["size"], price=current_price, timestamp=timestamp)

        if not self.exchange:
            return OrderResult(success=False, error="Exchange not initialized", timestamp=timestamp)

        try:
            is_futures = self._is_futures_symbol(symbol)
            self.exchange.options["defaultType"] = self._get_symbol_type(symbol)

            if is_futures:
                # Futures: fetch positions and close
                positions = self.exchange.fetch_positions([symbol])
                for pos in positions:
                    size = float(pos.get("contracts", 0))
                    if size > 0:
                        side = "sell" if pos.get("side") == "long" else "buy"
                        position_side = "LONG" if side == "sell" else "SHORT"
                        close_params = {"positionSide": position_side}
                        if self._hedge_mode:
                            close_params["reduceOnly"] = True
                        order = self.exchange.create_market_order(
                            symbol, side, abs(size), None, close_params
                        )
                        return OrderResult(
                            success=True,
                            order_id=str(order.get("id", "")),
                            symbol=symbol,
                            side=side,
                            size=abs(size),
                            timestamp=timestamp,
                        )
            else:
                # Spot: fetch balance and sell
                balance = self.exchange.fetch_balance()
                base = symbol.split("/")[0]
                available = float(balance.get("free", {}).get(base, 0))
                if available > 0:
                    order = self.exchange.create_market_sell_order(symbol, available)
                    return OrderResult(
                        success=True,
                        order_id=str(order.get("id", "")),
                        symbol=symbol,
                        side="sell",
                        size=available,
                        timestamp=timestamp,
                    )

            return OrderResult(success=False, error="No open position", symbol=symbol, timestamp=timestamp)

        except Exception as e:
            logger.error(f"Close position failed: {e}")
            return OrderResult(success=False, error=str(e), symbol=symbol, timestamp=timestamp)

    def get_positions(self) -> Dict[str, Dict]:
        """Get all open positions."""
        if self.mode == "paper":
            return self._paper_positions.copy()

        if not self.exchange:
            return {}

        try:
            positions = self.exchange.fetch_positions()
            result = {}
            for pos in positions:
                size = float(pos.get("contracts", 0))
                if size > 0:
                    symbol = pos.get("symbol", "")
                    result[symbol] = {
                        "side": pos.get("side", ""),
                        "size": size,
                        "entry_price": float(pos.get("entryPrice", 0)),
                        "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                    }
            return result
        except Exception as e:
            logger.error(f"Positions fetch failed: {e}")
            return {}

    def sync_positions(self) -> list:
        """
        Fetch existing exchange positions for SITA startup sync.
        Returns list of dicts with symbol, side, size, entry_price, unrealized_pnl, is_futures.
        """
        positions = self.get_positions()
        result = []
        for symbol, pos in positions.items():
            is_futures = self._is_futures_symbol(symbol)
            result.append({
                "symbol": symbol,
                "side": pos["side"],
                "size": pos["size"],
                "entry_price": pos["entry_price"],
                "unrealized_pnl": pos["unrealized_pnl"],
                "is_futures": is_futures,
            })
            logger.info(f"Sync: found existing position: {symbol} {pos['side']} {pos['size']} @ {pos['entry_price']}")
        return result
