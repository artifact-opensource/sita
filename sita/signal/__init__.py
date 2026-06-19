"""
SITA — Signal Generation Engine
7 strategies from Cthulu Apex, rebuilt for Linux/native Python.

Each strategy exposes:
    generate_signal(ohlcv: pd.DataFrame, symbol: str) -> SignalResult

Strategies:
    1. EMA Crossover — Trend following with EMA fast/slow crossover
    2. SMA Crossover — Simple moving average crossover
    3. Momentum Breakout — ATR-based breakout with volume confirmation
    4. Scalping — Mean reversion on tight ranges (RSI + Bollinger)
    5. Trend Following — ADX-filtered trend continuation
    6. Mean Reversion — Bollinger Band + RSI reversal
    7. RSI Reversal — Pure RSI extreme reversal (APEX innovation)

Plus: Multi-strategy fallback — if primary is quiet, try alternatives.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging

logger = logging.getLogger("sita.signal")


# ─── Signal Types ────────────────────────────────────────────────────────────

class SignalDirection(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class SignalStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class SignalResult:
    """Result from a single strategy's signal generation."""
    direction: SignalDirection
    strength: SignalStrength
    confidence: float          # 0-1
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strategy_name: str = ""
    regime_affinity: str = ""   # Which market regime this works best in
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_signal(self) -> bool:
        return self.direction != SignalDirection.NONE and self.confidence > 0.3

    @property
    def summary(self) -> str:
        if not self.has_signal:
            return f"{self.strategy_name}: NO SIGNAL"
        return (f"{self.strategy_name}: {self.direction.value.upper()} "
                f"({self.strength.value}, conf={self.confidence:.2f})")


@dataclass
class AggregatedSignal:
    """Final signal after multi-strategy aggregation."""
    primary: SignalResult
    fallbacks_tried: List[str] = field(default_factory=list)
    regime: str = "unknown"
    timestamp: str = ""

    @property
    def direction(self) -> SignalDirection:
        return self.primary.direction

    @property
    def confidence(self) -> float:
        return self.primary.confidence

    @property
    def strategy_name(self) -> str:
        return self.primary.strategy_name


# ─── Indicator Helpers ──────────────────────────────────────────────────────

def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def compute_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.inf)
    return 100 - (100 / (1 + rs))


def compute_atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_adx(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # Where plus_dm > minus_dm, keep plus_dm, else 0
    mask = plus_dm > minus_dm
    plus_dm = plus_dm * mask
    minus_dm = minus_dm * (~mask)

    atr = compute_atr(ohlcv, period)
    plus_di = 100 * compute_ema(plus_dm, period) / atr.replace(0, np.inf)
    minus_di = 100 * compute_ema(minus_dm, period) / atr.replace(0, np.inf)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.inf)
    adx = compute_ema(dx, period)
    return adx


def compute_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    sma = compute_sma(series, period)
    std = series.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def compute_vwap(ohlcv: pd.DataFrame) -> pd.Series:
    typical_price = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    volume = ohlcv["volume"]
    vwap = (typical_price * volume).cumsum() / volume.cumsum()
    return vwap


def compute_supertrend(ohlcv: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.Series:
    hl2 = (ohlcv["high"] + ohlcv["low"]) / 2
    atr = compute_atr(ohlcv, period)
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(index=ohlcv.index, dtype=float)
    direction = pd.Series(index=ohlcv.index, dtype=int)

    supertrend.iloc[0] = upper_band.iloc[0]
    direction.iloc[0] = 1

    for i in range(1, len(ohlcv)):
        if ohlcv["close"].iloc[i] > supertrend.iloc[i - 1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        else:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1

    return supertrend


# ─── Strategy 1: EMA Crossover ──────────────────────────────────────────────

class EMACrossover:
    """EMA Fast/Slow Crossover — Trend following."""

    name = "ema_crossover"
    regime_affinity = "trending"

    def __init__(self, fast: int = 9, slow: int = 21):
        self.fast = fast
        self.slow = slow

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.slow + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        ema_fast = compute_ema(close, self.fast)
        ema_slow = compute_ema(close, self.slow)

        # Crossover detection
        prev_fast = ema_fast.iloc[-2]
        prev_slow = ema_slow.iloc[-2]
        curr_fast = ema_fast.iloc[-1]
        curr_slow = ema_slow.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            direction = SignalDirection.LONG
            confidence = min(abs(curr_fast - curr_slow) / curr_slow * 1000, 1.0)
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            direction = SignalDirection.SHORT
            confidence = min(abs(curr_slow - curr_fast) / curr_slow * 1000, 1.0)

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=close.iloc[-1],
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 2: SMA Crossover ──────────────────────────────────────────────

class SMACrossover:
    """SMA Crossover — Slower trend following."""

    name = "sma_crossover"
    regime_affinity = "trending_weak"

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.slow + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        sma_fast = compute_sma(close, self.fast)
        sma_slow = compute_sma(close, self.slow)

        prev_fast = sma_fast.iloc[-2]
        prev_slow = sma_slow.iloc[-2]
        curr_fast = sma_fast.iloc[-1]
        curr_slow = sma_slow.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            direction = SignalDirection.LONG
            confidence = min(abs(curr_fast - curr_slow) / curr_slow * 500, 1.0)
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            direction = SignalDirection.SHORT
            confidence = min(abs(curr_slow - curr_fast) / curr_slow * 500, 1.0)

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=close.iloc[-1],
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 3: Momentum Breakout ──────────────────────────────────────────

class MomentumBreakout:
    """ATR-based breakout with volume confirmation."""

    name = "momentum_breakout"
    regime_affinity = "volatile_breakout"

    def __init__(self, atr_period: int = 14, atr_mult: float = 1.5, vol_period: int = 20):
        self.atr_period = atr_period
        self.atr_mult = atr_mult
        self.vol_period = vol_period

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < max(self.atr_period, self.vol_period) + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        atr = compute_atr(ohlcv, self.atr_period)
        vol_sma = ohlcv["volume"].rolling(self.vol_period).mean()

        upper = close.rolling(20).max()
        lower = close.rolling(20).min()

        curr_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        curr_atr = atr.iloc[-1]
        curr_vol = ohlcv["volume"].iloc[-1]
        avg_vol = vol_sma.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        # Breakout above resistance with volume
        if prev_close <= upper.iloc[-2] and curr_close > upper.iloc[-1]:
            vol_boost = min(curr_vol / avg_vol, 2.0) / 2.0 if avg_vol > 0 else 0.5
            confidence = min(0.5 + vol_boost * 0.3, 1.0)
            direction = SignalDirection.LONG

        # Breakout below support with volume
        elif prev_close >= lower.iloc[-2] and curr_close < lower.iloc[-1]:
            vol_boost = min(curr_vol / avg_vol, 2.0) / 2.0 if avg_vol > 0 else 0.5
            confidence = min(0.5 + vol_boost * 0.3, 1.0)
            direction = SignalDirection.SHORT

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=curr_close,
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 4: Scalping ───────────────────────────────────────────────────

class Scalping:
    """Mean reversion scalping on tight ranges (RSI + Bollinger)."""

    name = "scalping"
    regime_affinity = "ranging_tight"

    def __init__(self, rsi_period: int = 14, rsi_ob: int = 75, rsi_os: int = 25, bb_period: int = 20):
        self.rsi_period = rsi_period
        self.rsi_ob = rsi_ob
        self.rsi_os = rsi_os
        self.bb_period = bb_period

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.bb_period + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        rsi = compute_rsi(close, self.rsi_period)
        bb_upper, bb_mid, bb_lower = compute_bollinger(close, self.bb_period)

        curr_rsi = rsi.iloc[-1]
        curr_close = close.iloc[-1]
        curr_bb_upper = bb_upper.iloc[-1]
        curr_bb_lower = bb_lower.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        # Oversold + at lower BB = LONG
        if curr_rsi < self.rsi_os and curr_close <= curr_bb_lower:
            confidence = min((self.rsi_os - curr_rsi) / self.rsi_os + 0.3, 1.0)
            direction = SignalDirection.LONG

        # Overbought + at upper BB = SHORT
        elif curr_rsi > self.rsi_ob and curr_close >= curr_bb_upper:
            confidence = min((curr_rsi - self.rsi_ob) / (100 - self.rsi_ob) + 0.3, 1.0)
            direction = SignalDirection.SHORT

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=curr_close,
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 5: Trend Following ────────────────────────────────────────────

class TrendFollowing:
    """ADX-filtered trend continuation."""

    name = "trend_following"
    regime_affinity = "trending_strong"

    def __init__(self, adx_period: int = 14, adx_threshold: int = 25, ema_period: int = 50):
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.ema_period = ema_period

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.ema_period + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        adx = compute_adx(ohlcv, self.adx_period)
        ema = compute_ema(close, self.ema_period)

        curr_adx = adx.iloc[-1]
        curr_close = close.iloc[-1]
        curr_ema = ema.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        if np.isnan(curr_adx):
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        # Strong trend
        if curr_adx > self.adx_threshold:
            if curr_close > curr_ema:
                direction = SignalDirection.LONG
                confidence = min(curr_adx / 50, 1.0)
            elif curr_close < curr_ema:
                direction = SignalDirection.SHORT
                confidence = min(curr_adx / 50, 1.0)

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=curr_close,
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 6: Mean Reversion ─────────────────────────────────────────────

class MeanReversion:
    """Bollinger Band + RSI mean reversion."""

    name = "mean_reversion"
    regime_affinity = "ranging"

    def __init__(self, bb_period: int = 20, rsi_period: int = 14, rsi_extreme: int = 30):
        self.bb_period = bb_period
        self.rsi_period = rsi_period
        self.rsi_extreme = rsi_extreme

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.bb_period + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        rsi = compute_rsi(close, self.rsi_period)
        bb_upper, bb_mid, bb_lower = compute_bollinger(close, self.bb_period)

        curr_rsi = rsi.iloc[-1]
        curr_close = close.iloc[-1]
        curr_bb_upper = bb_upper.iloc[-1]
        curr_bb_lower = bb_lower.iloc[-1]
        curr_bb_mid = bb_mid.iloc[-1]

        direction = SignalDirection.NONE
        confidence = 0.0

        # Price at lower BB + RSI oversold = LONG
        if curr_close <= curr_bb_lower and curr_rsi < self.rsi_extreme:
            confidence = 0.6 + min((self.rsi_extreme - curr_rsi) / 100, 0.3)
            direction = SignalDirection.LONG

        # Price at upper BB + RSI overbought = SHORT
        elif curr_close >= curr_bb_upper and curr_rsi > (100 - self.rsi_extreme):
            confidence = 0.6 + min((curr_rsi - (100 - self.rsi_extreme)) / 100, 0.3)
            direction = SignalDirection.SHORT

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=curr_close,
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy 7: RSI Reversal (APEX Innovation) ────────────────────────────

class RSIReversal:
    """
    Pure RSI extreme reversal — the APEX innovation.
    Trades immediately on extreme overbought/oversold without waiting for crossover.
    """

    name = "rsi_reversal"
    regime_affinity = "reversal"

    def __init__(self, rsi_period: int = 14, extreme_ob: int = 85, extreme_os: int = 25, cooldown_bars: int = 2):
        self.rsi_period = rsi_period
        self.extreme_ob = extreme_ob
        self.extreme_os = extreme_os
        self.cooldown_bars = cooldown_bars
        self._last_signal_bar: Optional[int] = None

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> SignalResult:
        if len(ohlcv) < self.rsi_period + 5:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        close = ohlcv["close"]
        rsi = compute_rsi(close, self.rsi_period)

        curr_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2]
        curr_close = close.iloc[-1]
        curr_bar = len(ohlcv) - 1

        direction = SignalDirection.NONE
        confidence = 0.0

        # Cooldown check
        if self._last_signal_bar is not None and (curr_bar - self._last_signal_bar) < self.cooldown_bars:
            return SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name=self.name)

        # LONG: RSI rising from extreme oversold
        if prev_rsi < self.extreme_os and curr_rsi > prev_rsi:
            confidence = min((self.extreme_os - prev_rsi) / self.extreme_os + 0.4, 1.0)
            direction = SignalDirection.LONG
            self._last_signal_bar = curr_bar

        # SHORT: RSI dropping from extreme overbought
        elif prev_rsi > self.extreme_ob and curr_rsi < prev_rsi:
            confidence = min((prev_rsi - self.extreme_ob) / (100 - self.extreme_ob) + 0.4, 1.0)
            direction = SignalDirection.SHORT
            self._last_signal_bar = curr_bar

        strength = SignalStrength.STRONG if confidence > 0.7 else SignalStrength.MODERATE if confidence > 0.4 else SignalStrength.WEAK

        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=curr_close,
            strategy_name=self.name,
            regime_affinity=self.regime_affinity,
        )


# ─── Strategy Selector with Multi-Strategy Fallback ────────────────────────

class StrategySelector:
    """
    Dynamic strategy selection with multi-strategy fallback.
    From Cthulu APEX: primary strategy → try up to 3 alternatives.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.strategies = [
            EMACrossover(fast=self.config.get("ema_fast", 9), slow=self.config.get("ema_slow", 21)),
            SMACrossover(fast=self.config.get("sma_fast", 20), slow=self.config.get("sma_slow", 50)),
            MomentumBreakout(),
            Scalping(),
            TrendFollowing(),
            MeanReversion(),
            RSIReversal(),
        ]
        self.fallback_count = self.config.get("fallback_count", 3)
        logger.info(f"StrategySelector initialized with {len(self.strategies)} strategies, fallback={self.fallback_count}")

    def generate_signal(self, ohlcv: pd.DataFrame, symbol: str = "") -> AggregatedSignal:
        """
        Generate signal with multi-strategy fallback.
        1. Try primary (highest regime affinity)
        2. If no signal, try up to N fallback strategies
        3. First strategy to generate a valid signal wins
        """
        fallbacks_tried = []

        # Score all strategies by regime affinity
        scored = []
        for s in self.strategies:
            result = s.generate_signal(ohlcv, symbol)
            scored.append(result)

        # Sort by confidence (highest first)
        scored.sort(key=lambda r: r.confidence, reverse=True)

        # Primary: highest confidence
        primary = scored[0] if scored else SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name="none")

        if primary.has_signal:
            return AggregatedSignal(
                primary=primary,
                fallbacks_tried=[],
                regime=primary.regime_affinity,
            )

        # Fallback: try alternatives
        for fallback in scored[1:self.fallback_count + 1]:
            fallbacks_tried.append(fallback.strategy_name)
            if fallback.has_signal:
                return AggregatedSignal(
                    primary=fallback,
                    fallbacks_tried=fallbacks_tried,
                    regime=fallback.regime_affinity,
                )

        # No signal from any strategy
        return AggregatedSignal(
            primary=SignalResult(SignalDirection.NONE, SignalStrength.WEAK, 0.0, strategy_name="none"),
            fallbacks_tried=fallbacks_tried,
            regime="unknown",
        )
