"""
SITA — Position Manager
Dynamic break-even, trailing stops, and profit profiling.

Features:
- Automatic break-even adjustment when price moves in favor
- Trailing stop that locks in profits
- Profit profiling: partial closes at R:R targets
- Position lifecycle management
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("sita.position")


@dataclass
class Position:
    """Tracked position."""
    symbol: str
    side: str               # 'long' or 'short'
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    order_id: str = ""
    status: str = "open"    # open | closed | partial
    highest_price: float = 0.0   # For trailing stop
    lowest_price: float = float("inf")
    partial_closes: List[Dict] = field(default_factory=list)
    opened_at: str = ""
    updated_at: str = ""

    @property
    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_distance(self) -> float:
        return abs(self.take_profit - self.entry_price)

    @property
    def rr_ratio(self) -> float:
        if self.risk_distance <= 0:
            return 0
        return self.reward_distance / self.risk_distance


class PositionManager:
    """
    Position lifecycle management.
    Dynamic BE + trailing stop + profit profiling.
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []

        # Break-even config
        self.be_trigger_rr = self.config.get("be_trigger_rr", 1.0)  # Move to BE after 1R profit
        self.be_buffer_pct = self.config.get("be_buffer_pct", 0.001)  # 0.1% buffer above/below entry

        # Trailing stop config
        self.trailing_trigger_rr = self.config.get("trailing_trigger_rr", 1.5)  # Start trailing after 1.5R
        self.trailing_distance_atr_mult = self.config.get("trailing_distance_atr_mult", 1.5)

        # Profit profiling config
        self.profit_targets = self.config.get("profit_targets", [
            {"rr": 1.0, "close_pct": 0.25},   # Close 25% at 1R
            {"rr": 2.0, "close_pct": 0.25},   # Close 25% at 2R
            {"rr": 3.0, "close_pct": 0.25},   # Close 25% at 3R
        ])
        self.final_target_rr = self.config.get("final_target_rr", 4.0)  # Let runners go to 4R

    def open_position(self, symbol: str, side: str, size: float, entry_price: float,
                      stop_loss: float, take_profit: float, order_id: str = "") -> Position:
        """Open a new tracked position."""
        now = datetime.now(timezone.utc).isoformat()
        pos = Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            order_id=order_id,
            highest_price=entry_price,
            lowest_price=entry_price,
            opened_at=now,
            updated_at=now,
        )
        self.positions[symbol] = pos
        logger.info(f"Position opened: {side} {size} {symbol} @ {entry_price}, SL={stop_loss}, TP={take_profit}")
        return pos

    def update_position(self, symbol: str, current_price: float, atr: float = 0) -> Dict:
        """
        Update a position with current price.
        Returns actions: close, partial_close, move_be, trail_stop, or hold.
        """
        pos = self.positions.get(symbol)
        if not pos or pos.status == "closed":
            return {"action": "none", "reason": "No open position"}

        # Update high/low
        if current_price > pos.highest_price:
            pos.highest_price = current_price
        if current_price < pos.lowest_price:
            pos.lowest_price = current_price

        pos.updated_at = datetime.now(timezone.utc).isoformat()

        result = {"action": "hold", "reason": "In profit zone", "position": pos}

        # Check stop loss hit
        if pos.side == "long" and current_price <= pos.stop_loss:
            return self._close_position(symbol, pos.stop_loss, "stop_loss_hit")
        elif pos.side == "short" and current_price >= pos.stop_loss:
            return self._close_position(symbol, pos.stop_loss, "stop_loss_hit")

        # Check take profit hit
        if pos.side == "long" and current_price >= pos.take_profit:
            return self._close_position(symbol, pos.take_profit, "take_profit_hit")
        elif pos.side == "short" and current_price <= pos.take_profit:
            return self._close_position(symbol, pos.take_profit, "take_profit_hit")

        # Calculate current R:R
        if pos.side == "long":
            current_profit = current_price - pos.entry_price
        else:
            current_profit = pos.entry_price - current_price

        current_rr = current_profit / pos.risk_distance if pos.risk_distance > 0 else 0

        # Profit profiling: partial closes
        for target in self.profit_targets:
            target_rr = target["rr"]
            close_pct = target["close_pct"]
            target_key = f"partial_{target_rr}r"

            if current_rr >= target_rr and target_key not in [p.get("target") for p in pos.partial_closes]:
                partial_size = pos.size * close_pct
                result = {
                    "action": "partial_close",
                    "size": partial_size,
                    "price": current_price,
                    "target": target_key,
                    "reason": f"Profit profiling: {target_rr}R reached, closing {close_pct*100}%",
                }
                pos.partial_closes.append({"target": target_key, "size": partial_size, "price": current_price})
                return result

        # Dynamic break-even
        if current_rr >= self.be_trigger_rr:
            if pos.side == "long" and pos.stop_loss < pos.entry_price:
                new_be = pos.entry_price * (1 + self.be_buffer_pct)
                if new_be > pos.stop_loss:
                    pos.stop_loss = new_be
                    result = {"action": "move_be", "new_sl": new_be, "reason": f"Break-even moved to {new_be}"}
            elif pos.side == "short" and pos.stop_loss > pos.entry_price:
                new_be = pos.entry_price * (1 - self.be_buffer_pct)
                if new_be < pos.stop_loss:
                    pos.stop_loss = new_be
                    result = {"action": "move_be", "new_sl": new_be, "reason": f"Break-even moved to {new_be}"}

        # Trailing stop
        if current_rr >= self.trailing_trigger_rr and atr > 0:
            trail_distance = atr * self.trailing_distance_atr_mult
            if pos.side == "long":
                new_sl = pos.highest_price - trail_distance
                if new_sl > pos.stop_loss:
                    pos.stop_loss = new_sl
                    result = {"action": "trail_stop", "new_sl": new_sl, "reason": f"Trailing stop: {new_sl}"}
            elif pos.side == "short":
                new_sl = pos.lowest_price + trail_distance
                if new_sl < pos.stop_loss:
                    pos.stop_loss = new_sl
                    result = {"action": "trail_stop", "new_sl": new_sl, "reason": f"Trailing stop: {new_sl}"}

        return result

    def _close_position(self, symbol: str, close_price: float, reason: str) -> Dict:
        """Close a position."""
        pos = self.positions.get(symbol)
        if not pos:
            return {"action": "none", "reason": "No position"}

        if pos.side == "long":
            pnl = (close_price - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - close_price) * pos.size

        pos.status = "closed"
        self.closed_positions.append(pos)
        del self.positions[symbol]

        logger.info(f"Position closed: {symbol} @ {close_price}, PnL={pnl:.2f}, reason={reason}")

        return {
            "action": "close",
            "price": close_price,
            "pnl": pnl,
            "reason": reason,
            "position": pos,
        }

    def get_open_positions(self) -> Dict[str, Position]:
        return self.positions.copy()

    def get_closed_positions(self, limit: int = 50) -> List[Position]:
        return self.closed_positions[-limit:]

    def get_stats(self) -> Dict:
        """Get position statistics."""
        closed = self.closed_positions
        if not closed:
            return {"total_trades": 0, "win_rate": 0, "avg_pnl": 0}

        wins = sum(1 for p in closed if (
            (p.side == "long" and p.stop_loss > p.entry_price) or
            (p.side == "short" and p.stop_loss < p.entry_price)
        ))
        total_pnl = sum(
            (p.highest_price - p.entry_price) * p.size if p.side == "long"
            else (p.entry_price - p.lowest_price) * p.size
            for p in closed
        )

        return {
            "total_trades": len(closed),
            "open_positions": len(self.positions),
            "wins": wins,
            "losses": len(closed) - wins,
            "win_rate": wins / len(closed) if closed else 0,
            "avg_pnl": total_pnl / len(closed) if closed else 0,
            "total_pnl": total_pnl,
        }
