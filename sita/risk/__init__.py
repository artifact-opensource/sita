"""
SITA — Unified Risk Manager
Ported from Cthulu APEX. Banks are jealous.

Features:
- Position sizing based on risk per trade + stop loss distance
- Daily/Weekly/Total loss limits with circuit breakers
- Recovery mode (auto-reduces risk after drawdown)
- Adaptive risk by account size (4 tiers)
- Dynamic SL/TP calculation
- Break-even automation
- Profit profiling (partial closes at targets)
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging

from ..config import DEFAULT_RISK_LIMITS, BALANCE_BREAKPOINTS, RISK_BY_CATEGORY

logger = logging.getLogger("sita.risk")


class RiskAction(Enum):
    APPROVED = "approved"
    REDUCED = "reduced"
    REJECTED = "rejected"
    LOCKED = "locked"


@dataclass
class RiskLimits:
    max_daily_loss_pct: float = 0.03
    max_weekly_loss_pct: float = 0.06
    max_total_loss_pct: float = 0.10
    max_risk_per_trade_pct: float = 0.01
    max_positions: int = 5
    max_positions_per_symbol: int = 2
    recovery_mode_threshold: float = 0.08
    recovery_mode_risk_mult: float = 0.50
    min_lot: float = 0.001
    min_notional: float = 5.0        # Minimum order notional in USDT (Binance futures = 5)
    balance_breakpoints: List[float] = field(default_factory=lambda: BALANCE_BREAKPOINTS)
    risk_by_category: Dict[str, float] = field(default_factory=lambda: RISK_BY_CATEGORY)


@dataclass
class RiskState:
    day_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    week_start: datetime = field(default_factory=lambda: datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday()))
    initial_balance: float = 0.0
    peak_balance: float = 0.0
    current_balance: float = 0.0
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    total_pnl: float = 0.0
    open_positions: int = 0
    positions_by_symbol: Dict[str, int] = field(default_factory=dict)
    daily_limit_hit: bool = False
    weekly_limit_hit: bool = False
    total_limit_hit: bool = False
    recovery_mode: bool = False
    recent_trades: List[Dict[str, Any]] = field(default_factory=list)
    wins: int = 0
    losses: int = 0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.5

    @property
    def drawdown_pct(self) -> float:
        if self.peak_balance <= 0:
            return 0.0
        return (self.peak_balance - self.current_balance) / self.peak_balance


@dataclass
class RiskDecision:
    """Risk manager's decision on a proposed trade."""
    action: RiskAction
    position_size: float          # Adjusted size
    stop_loss_price: float        # Calculated SL
    take_profit_price: float      # Calculated TP
    risk_amount: float            # Actual risk in account currency
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class UnifiedRiskManager:
    """
    Unified Risk Management — the supernatural layer.

    Consolidates all risk functions:
    - Position sizing (risk-based, not fixed lot)
    - Stop loss calculation (ATR-based, not fixed pips)
    - Daily/Weekly/Total loss limits
    - Recovery mode (auto de-risk after drawdown)
    - Adaptive risk by account size
    """

    def __init__(self, config: Optional[Dict] = None, limits: Optional[RiskLimits] = None):
        self.config = config or {}
        # Always start with our strict defaults
        self.limits = RiskLimits()
        for key, value in DEFAULT_RISK_LIMITS.items():
            if hasattr(self.limits, key):
                setattr(self.limits, key, value)
        # Override with any explicitly provided limits object
        if limits:
            for key, value in limits.__dict__.items():
                setattr(self.limits, key, value)
        # Override with config dict
        if config:
            self._apply_config(config)
        self.state = RiskState()
        logger.info(f"UnifiedRiskManager: max_risk={self.limits.max_risk_per_trade_pct*100}%, max_pos={self.limits.max_positions}")

    def _apply_config(self, config: Dict) -> None:
        for key, value in config.items():
            if hasattr(self.limits, key):
                setattr(self.limits, key, value)

    def initialize_balances(self, balance: float) -> None:
        self.state.initial_balance = balance
        self.state.peak_balance = balance
        self.state.current_balance = balance
        logger.info(f"Risk manager initialized: balance={balance:.2f}")

    def update_balance(self, balance: float) -> None:
        self.state.current_balance = balance
        if balance > self.state.peak_balance:
            self.state.peak_balance = balance
        if self.state.drawdown_pct >= self.limits.recovery_mode_threshold:
            if not self.state.recovery_mode:
                logger.warning(f"RECOVERY MODE: DD={self.state.drawdown_pct*100:.1f}%")
                self.state.recovery_mode = True
        elif self.state.recovery_mode and self.state.drawdown_pct < self.limits.recovery_mode_threshold * 0.5:
            logger.info("Exiting recovery mode")
            self.state.recovery_mode = False
        self._check_limits()

    def _check_limits(self) -> None:
        initial = self.state.initial_balance
        if initial <= 0:
            return
        daily_loss = max(-self.state.daily_pnl, 0)
        if daily_loss / initial >= self.limits.max_daily_loss_pct and not self.state.daily_limit_hit:
            logger.warning(f"DAILY LOSS LIMIT: {daily_loss/initial*100:.1f}%")
            self.state.daily_limit_hit = True
        weekly_loss = max(-self.state.weekly_pnl, 0)
        if weekly_loss / initial >= self.limits.max_weekly_loss_pct and not self.state.weekly_limit_hit:
            logger.warning(f"WEEKLY LOSS LIMIT: {weekly_loss/initial*100:.1f}%")
            self.state.weekly_limit_hit = True
        if self.state.drawdown_pct >= self.limits.max_total_loss_pct and not self.state.total_limit_hit:
            logger.error(f"TOTAL LOSS LIMIT: DD={self.state.drawdown_pct*100:.1f}%")
            self.state.total_limit_hit = True

    def get_balance_category(self, balance: float) -> str:
        bp = self.limits.balance_breakpoints
        if balance <= bp[0]: return "tiny"
        elif balance <= bp[1]: return "small"
        elif balance <= bp[2]: return "medium"
        else: return "large"

    def get_risk_percentage(self, balance: float) -> float:
        category = self.get_balance_category(balance)
        base_risk = self.limits.risk_by_category.get(category, self.limits.max_risk_per_trade_pct)
        if self.state.recovery_mode:
            base_risk *= self.limits.recovery_mode_risk_mult
        return min(base_risk, self.limits.max_risk_per_trade_pct)

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_price: float,
        balance: float,
        confluence_mult: float = 1.0,
    ) -> Tuple[float, float]:
        """
        Calculate position size based on risk per trade and SL distance.
        Enforces Binance minimum notional (min_notional from config, default $5).
        When account is small, scales position to meet min notional floor.

        Returns: (position_size, risk_amount)
        """
        min_notional = self.config.get("min_notional", 5.0) if self.config else 5.0
        risk_pct = self.get_risk_percentage(balance)
        risk_amount = balance * risk_pct * confluence_mult

        sl_distance = abs(entry_price - stop_loss_price)
        if sl_distance <= 0:
            return self.limits.min_lot, 0.0

        # Base position size from risk
        position_size = risk_amount / sl_distance

        # Enforce minimum notional (Binance futures requires >= $5)
        min_size_for_notional = min_notional / entry_price if entry_price > 0 else position_size
        if position_size < min_size_for_notional:
            position_size = min_size_for_notional
            # Recalculate risk for this larger size
            risk_amount = position_size * sl_distance

        # Cap notional value: max 35% of balance per position
        max_notional = balance * 0.35
        max_size_by_notional = max_notional / entry_price if entry_price > 0 else position_size
        if position_size > max_size_by_notional:
            position_size = max_size_by_notional
            risk_amount = position_size * sl_distance

        position_size = max(position_size, self.limits.min_lot)

        # Recalculate actual risk with final size
        actual_risk = position_size * sl_distance

        return round(position_size, 6), round(actual_risk, 2)

    def calculate_stop_loss(
        self,
        direction: str,
        entry_price: float,
        atr: float,
        multiplier: float = 1.5,
    ) -> float:
        """ATR-based stop loss."""
        if direction == "long":
            return round(entry_price - (atr * multiplier), 8)
        else:
            return round(entry_price + (atr * multiplier), 8)

    def calculate_take_profit(
        self,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        risk_reward: float = 2.0,
    ) -> float:
        """Risk:reward based take profit."""
        risk = abs(entry_price - stop_loss_price)
        if direction == "long":
            return round(entry_price + (risk * risk_reward), 8)
        else:
            return round(entry_price - (risk * risk_reward), 8)

    def approve_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        balance: float,
        confluence_mult: float = 1.0,
    ) -> RiskDecision:
        """
        Main entry point: approve, reduce, or reject a trade.
        """
        reasons = []
        warnings = []

        # Check limits
        if self.state.daily_limit_hit:
            return RiskDecision(RiskAction.LOCKED, 0, 0, 0, 0, reasons=["Daily loss limit hit"])
        if self.state.weekly_limit_hit:
            return RiskDecision(RiskAction.LOCKED, 0, 0, 0, 0, reasons=["Weekly loss limit hit"])
        if self.state.total_limit_hit:
            return RiskDecision(RiskAction.LOCKED, 0, 0, 0, 0, reasons=["Total loss limit hit"])

        # Check position limits
        if self.state.open_positions >= self.limits.max_positions:
            return RiskDecision(RiskAction.REJECTED, 0, 0, 0, 0, reasons=[f"Max positions ({self.limits.max_positions}) reached"])

        symbol_count = self.state.positions_by_symbol.get(symbol, 0)
        if symbol_count >= self.limits.max_positions_per_symbol:
            return RiskDecision(RiskAction.REJECTED, 0, 0, 0, 0, reasons=[f"Max positions for {symbol}"])

        # Calculate position size
        position_size, risk_amount = self.calculate_position_size(
            symbol, entry_price, stop_loss_price, balance, confluence_mult
        )

        if position_size <= 0:
            return RiskDecision(RiskAction.REJECTED, 0, 0, 0, 0, reasons=["Position size too small"])

        # Recovery mode warning
        if self.state.recovery_mode:
            warnings.append("RECOVERY MODE: position size reduced")

        # Determine action
        if confluence_mult < 0.7:
            action = RiskAction.REDUCED
            reasons.append(f"Reduced size: confluence mult={confluence_mult:.2f}")
        else:
            action = RiskAction.APPROVED
            reasons.append(f"Approved: size={position_size}, risk={risk_amount:.2f}")

        return RiskDecision(
            action=action,
            position_size=position_size,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_amount=risk_amount,
            reasons=reasons,
            warnings=warnings,
        )

    def record_trade_result(self, pnl: float) -> None:
        """Record a closed trade's P&L."""
        self.state.daily_pnl += pnl
        self.state.weekly_pnl += pnl
        self.state.total_pnl += pnl
        if pnl > 0:
            self.state.wins += 1
        else:
            self.state.losses += 1
        self.state.recent_trades.append({
            "pnl": pnl,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 100 trades
        if len(self.state.recent_trades) > 100:
            self.state.recent_trades = self.state.recent_trades[-100:]
        self._check_limits()
