"""
SITA — Entry Confluence Filter
9-dimension quality gate from Cthulu Apex.

Scores each potential entry across 9 weighted dimensions:
  Level (18%) + Momentum (15%) + Timing (10%) + Structure (8%) +
  Trend (17%) + BOS (12%) + Order Block (12%) + Session ORB (8%)

Only PREMIUM and GOOD entries get full position size.
MARGINAL gets reduced. POOR and REJECT don't trade.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import logging

from ..config import CONFLUENCE_WEIGHTS, ENTRY_THRESHOLDS, POSITION_MULTIPLIERS

logger = logging.getLogger("sita.confluence")


class EntryQuality(Enum):
    PREMIUM = "premium"    # Score >= 85, full position
    GOOD = "good"          # Score >= 70, 85% position
    MARGINAL = "marginal"  # Score >= 50, 60% position
    POOR = "poor"          # Score >= 20, 30% position
    REJECT = "reject"      # Score < 20, no trade


@dataclass
class ConfluenceResult:
    """Result of confluence analysis."""
    quality: EntryQuality
    score: float              # 0-100
    should_enter: bool
    position_mult: float      # Size multiplier
    wait_for_better: bool
    optimal_entry: Optional[float] = None
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)

    @property
    def summary(self) -> str:
        return (f"Confluence: {self.quality.value} (score={self.score:.0f}), "
                f"mult={self.position_mult:.2f}, wait={self.wait_for_better}")


class EntryConfluenceFilter:
    """
    9-dimension confluence filter — the quality gate.

    Analyzes whether current price is optimal for entry:
    1. Level Score      (18%) — Proximity to S/R, round numbers, EMAs
    2. Momentum Score  (15%) — Momentum alignment
    3. Timing Score    (10%) — Entry timing quality
    4. Structure Score (8%)  — Market structure alignment
    5. Trend Score     (17%) — Macro trend alignment
    6. BOS Score       (12%) — Break of Structure / ChoCH
    7. Order Block     (12%) — ICT institutional zones
    8. Session ORB     (8%)  — Session Opening Range Breakout

    Banks are jealous. This is the system they don't want you to have.
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.weights = CONFLUENCE_WEIGHTS
        self.thresholds = ENTRY_THRESHOLDS
        self.position_multipliers = POSITION_MULTIPLIERS

        # Confluence parameters
        self.min_score_to_enter = self.config.get("min_score_to_enter", 50)
        self.min_score_for_full_size = self.config.get("min_score_for_full_size", 75)
        self.enable_wait_mode = self.config.get("enable_wait_mode", True)
        self.max_wait_bars = self.config.get("max_wait_bars", 10)
        self.sr_lookback = self.config.get("sr_lookback", 100)

        logger.info("EntryConfluenceFilter initialized with 9-dimension scoring")

    def analyze_entry(
        self,
        signal_direction: str,
        current_price: float,
        symbol: str,
        ohlcv: pd.DataFrame,
        atr: Optional[float] = None,
        signal_entry_price: Optional[float] = None,
    ) -> ConfluenceResult:
        """
        Analyze whether current conditions support a quality entry.

        Args:
            signal_direction: 'long' or 'short'
            current_price: Current market price
            symbol: Trading symbol
            ohlcv: OHLCV DataFrame (minimum 100 bars recommended)
            atr: Current ATR (computed if not provided)
            signal_entry_price: Price where signal was generated (drift check)

        Returns:
            ConfluenceResult with entry quality assessment
        """
        reasons = []
        warnings = []
        component_scores = {}

        if atr is None or np.isnan(atr):
            atr = self._compute_atr(ohlcv)

        if len(ohlcv) < 50:
            return ConfluenceResult(
                quality=EntryQuality.REJECT,
                score=0.0,
                should_enter=False,
                position_mult=0.0,
                wait_for_better=False,
                reasons=["Insufficient data (< 50 bars)"],
            )

        # ─── 1. Level Score (18%) ───────────────────────────────────────
        level_score, level_reasons = self._score_price_levels(
            signal_direction, current_price, ohlcv, atr
        )
        reasons.extend(level_reasons)
        component_scores["level"] = level_score

        # ─── 2. Momentum Score (15%) ────────────────────────────────────
        momentum_score, momentum_aligned, momentum_reasons = self._score_momentum(
            signal_direction, ohlcv
        )
        reasons.extend(momentum_reasons)
        component_scores["momentum"] = momentum_score

        # ─── 3. Timing Score (10%) ──────────────────────────────────────
        timing_score, timing_reasons, wait_for_better, optimal_entry = self._score_timing(
            signal_direction, current_price, ohlcv, atr
        )
        reasons.extend(timing_reasons)
        component_scores["timing"] = timing_score

        # ─── 4. Structure Score (8%) ────────────────────────────────────
        structure_score, structure_reasons = self._score_structure(
            signal_direction, ohlcv
        )
        reasons.extend(structure_reasons)
        component_scores["structure"] = structure_score

        # ─── 5. Trend Score (17%) ───────────────────────────────────────
        trend_aligned, trend_score, trend_reasons = self._check_trend_alignment(
            signal_direction, ohlcv
        )
        reasons.extend(trend_reasons)
        component_scores["trend"] = trend_score

        # ─── 6. BOS Score (12%) ─────────────────────────────────────────
        bos_confirmed, bos_score, bos_reasons = self._check_bos_choch(
            signal_direction, ohlcv
        )
        reasons.extend(bos_reasons)
        component_scores["bos"] = bos_score

        # ─── 7. Order Block Score (12%) ─────────────────────────────────
        ob_score, ob_aligned, ob_reasons = self._score_order_blocks(
            signal_direction, current_price, ohlcv, atr
        )
        reasons.extend(ob_reasons)
        component_scores["order_block"] = ob_score

        # ─── 8. Session ORB Score (8%) ──────────────────────────────────
        orb_score, orb_aligned, orb_reasons = self._score_session_orb(
            signal_direction, current_price, ohlcv
        )
        reasons.extend(orb_reasons)
        component_scores["session_orb"] = orb_score

        # ─── Signal drift penalty ───────────────────────────────────────
        drift_penalty = 0.0
        if signal_entry_price is not None and atr > 0:
            drift = abs(current_price - signal_entry_price) / atr
            if drift > 1.5:
                drift_penalty = min(drift * 10, 30)
                warnings.append(f"Price drifted {drift:.1f} ATR from signal")

        # ─── Counter-trend penalty ──────────────────────────────────────
        counter_trend_penalty = 0
        if not trend_aligned:
            counter_trend_penalty = 25
            adx_val = self._compute_adx(ohlcv)
            curr_adx = adx_val.iloc[-1] if not adx_val.empty else 0
            if curr_adx > 30:
                counter_trend_penalty += 10
            if curr_adx > 40:
                counter_trend_penalty += 10
            total_score_drift = counter_trend_penalty
            reasons.append(f"COUNTER-TREND PENALTY: -{total_score_drift}")
        else:
            counter_trend_penalty = -8  # Actually a bonus
            reasons.append("TREND ALIGNMENT BONUS: +8")

        # ─── Super confluence bonuses ───────────────────────────────────
        super_bonus = 0
        if ob_aligned and ob_score > 0.7:
            super_bonus += 8
            reasons.append("OB BONUS: Strong institutional level confluence")
        if orb_aligned and orb_score > 0.7:
            super_bonus += 5
            reasons.append("ORB BONUS: Session breakout confluence")
        if ob_aligned and orb_aligned and ob_score > 0.6 and orb_score > 0.6:
            super_bonus += 7
            reasons.append("SUPER CONFLUENCE: OB + ORB aligned")
        if bos_confirmed and bos_score > 0.6:
            super_bonus += 5
        elif not bos_confirmed:
            super_bonus -= 10

        # ─── Final weighted score ───────────────────────────────────────
        total_score = (
            level_score * self.weights["level"]
            + momentum_score * self.weights["momentum"]
            + timing_score * self.weights["timing"]
            + structure_score * self.weights["structure"]
            + trend_score * self.weights["trend"]
            + bos_score * self.weights["bos"]
            + ob_score * self.weights["order_block"]
            + orb_score * self.weights["session_orb"]
        ) * 100 - drift_penalty - counter_trend_penalty + super_bonus

        total_score = max(0, min(100, total_score))

        # ─── Quality classification ─────────────────────────────────────
        if total_score >= self.thresholds["premium"]:
            quality = EntryQuality.PREMIUM
        elif total_score >= self.thresholds["good"]:
            quality = EntryQuality.GOOD
        elif total_score >= self.thresholds["marginal"]:
            quality = EntryQuality.MARGINAL
        elif total_score >= self.thresholds["poor"]:
            quality = EntryQuality.POOR
        else:
            quality = EntryQuality.REJECT

        # ─── Position size multiplier ──────────────────────────────────
        position_mult = self.position_multipliers.get(quality.value, 0.0)

        # ─── Should enter? ─────────────────────────────────────────────
        should_enter = (
            quality in (EntryQuality.PREMIUM, EntryQuality.GOOD, EntryQuality.MARGINAL)
            and not wait_for_better
        )

        return ConfluenceResult(
            quality=quality,
            score=total_score,
            should_enter=should_enter,
            position_mult=position_mult,
            wait_for_better=wait_for_better,
            optimal_entry=optimal_entry,
            reasons=reasons,
            warnings=warnings,
            component_scores=component_scores,
        )

    # ─── Component Scorers ─────────────────────────────────────────────────

    def _score_price_levels(self, direction, price, ohlcv, atr) -> Tuple[float, List[str]]:
        """Score proximity to significant price levels."""
        reasons = []
        close = ohlcv["close"]
        score = 0.5  # Neutral start

        # EMA levels
        ema_21 = close.ewm(span=21).mean().iloc[-1]
        ema_50 = close.ewm(span=50).mean().iloc[-1]
        ema_200 = close.ewm(span=200).mean().iloc[-1] if len(close) >= 200 else None

        level_dist = lambda p: abs(price - p) / atr if atr > 0 else 999

        # Near EMA support (for longs)
        if direction == "long":
            if level_dist(ema_21) < 0.5:
                score += 0.15
                reasons.append("Near EMA-21 support (+0.15)")
            if level_dist(ema_50) < 0.5:
                score += 0.15
                reasons.append("Near EMA-50 support (+0.15)")
            if ema_200 and level_dist(ema_200) < 1.0:
                score += 0.2
                reasons.append("Near EMA-200 major support (+0.2)")

        # Near EMA resistance (for shorts)
        elif direction == "short":
            if level_dist(ema_21) < 0.5:
                score += 0.15
                reasons.append("Near EMA-21 resistance (+0.15)")
            if level_dist(ema_50) < 0.5:
                score += 0.15
                reasons.append("Near EMA-50 resistance (+0.15)")

        # Round number proximity
        round_levels = self._find_round_numbers(price, atr)
        for rl in round_levels:
            if abs(price - rl) / atr < 0.3:
                score += 0.1
                reasons.append(f"Near round number {rl} (+0.1)")

        return min(score, 1.0), reasons

    def _score_momentum(self, direction, ohlcv) -> Tuple[float, bool, List[str]]:
        """Score momentum alignment with signal direction."""
        reasons = []
        close = ohlcv["close"]
        score = 0.5

        # RSI momentum
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        curr_rsi = rsi.iloc[-1]

        # MACD momentum
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9).mean()
        macd_hist = macd_line - signal_line

        curr_macd_hist = macd_hist.iloc[-1]
        prev_macd_hist = macd_hist.iloc[-2]
        macd_rising = curr_macd_hist > prev_macd_hist

        aligned = True

        if direction == "long":
            if curr_rsi > 50:
                score += 0.1
                reasons.append(f"RSI above 50: {curr_rsi:.1f}")
            if macd_rising:
                score += 0.15
                reasons.append("MACD histogram rising (+0.15)")
            if curr_macd_hist > 0:
                score += 0.1
                reasons.append("MACD above signal (+0.1)")
            if curr_rsi < 30:
                aligned = False
                score -= 0.2
                reasons.append("RSI oversold — counter-momentum (-0.2)")

        elif direction == "short":
            if curr_rsi < 50:
                score += 0.1
                reasons.append(f"RSI below 50: {curr_rsi:.1f}")
            if not macd_rising:
                score += 0.15
                reasons.append("MACD histogram falling (+0.15)")
            if curr_macd_hist < 0:
                score += 0.1
                reasons.append("MACD below signal (+0.1)")
            if curr_rsi > 70:
                aligned = False
                score -= 0.2
                reasons.append("RSI overbought — counter-momentum (-0.2)")

        return max(0, min(score, 1.0)), aligned, reasons

    def _score_timing(self, direction, price, ohlcv, atr) -> Tuple[float, List[str], bool, Optional[float]]:
        """Score entry timing quality."""
        reasons = []
        score = 0.5
        wait_for_better = False
        optimal_entry = None

        close = ohlcv["close"]
        curr_close = close.iloc[-1]

        # Check if price is pulling back to a better level
        if direction == "long":
            recent_high = close.iloc[-10:].max()
            if curr_close < recent_high and (recent_high - curr_close) / atr < 1.0:
                score += 0.2
                reasons.append("Pulling back from recent high — good timing (+0.2)")
            elif curr_close >= recent_high:
                wait_for_better = True
                optimal_entry = curr_close - (atr * 0.5)
                reasons.append("At recent high — consider waiting for pullback")

        elif direction == "short":
            recent_low = close.iloc[-10:].min()
            if curr_close > recent_low and (curr_close - recent_low) / atr < 1.0:
                score += 0.2
                reasons.append("Pulling up from recent low — good timing (+0.2)")
            elif curr_close <= recent_low:
                wait_for_better = True
                optimal_entry = curr_close + (atr * 0.5)
                reasons.append("At recent low — consider waiting for pullback")

        # Volume confirmation
        if "volume" in ohlcv.columns:
            vol_sma = ohlcv["volume"].rolling(20).mean().iloc[-1]
            curr_vol = ohlcv["volume"].iloc[-1]
            if curr_vol > vol_sma * 1.5:
                score += 0.15
                reasons.append("High volume confirmation (+0.15)")

        return max(0, min(score, 1.0)), reasons, wait_for_better, optimal_entry

    def _score_structure(self, direction, ohlcv) -> Tuple[float, List[str]]:
        """Score market structure alignment."""
        reasons = []
        score = 0.5

        highs = ohlcv["high"]
        lows = ohlcv["low"]

        # Simple swing structure
        recent_highs = highs.iloc[-50:]
        recent_lows = lows.iloc[-50:]

        higher_highs = recent_highs.iloc[-1] > recent_highs.iloc[-20]
        higher_lows = recent_lows.iloc[-1] > recent_lows.iloc[-20]
        lower_highs = recent_highs.iloc[-1] < recent_highs.iloc[-20]
        lower_lows = recent_lows.iloc[-1] < recent_lows.iloc[-20]

        if direction == "long" and higher_highs and higher_lows:
            score += 0.3
            reasons.append("Higher highs + higher lows — bullish structure (+0.3)")
        elif direction == "short" and lower_highs and lower_lows:
            score += 0.3
            reasons.append("Lower highs + lower lows — bearish structure (+0.3)")

        return max(0, min(score, 1.0)), reasons

    def _check_trend_alignment(self, direction, ohlcv) -> Tuple[bool, float, List[str]]:
        """Check if macro trend supports signal direction."""
        reasons = []
        close = ohlcv["close"]
        score = 0.5

        if len(close) < 200:
            return True, score, ["Insufficient data for trend check — assumed aligned"]

        ema_50 = close.ewm(span=50).mean().iloc[-1]
        ema_200 = close.ewm(span=200).mean().iloc[-1]
        curr_close = close.iloc[-1]

        # ADX for trend strength
        adx_val = self._compute_adx(ohlcv)
        curr_adx = adx_val.iloc[-1] if not adx_val.empty else 0

        trend_aligned = True

        if direction == "long":
            if curr_close > ema_50 and ema_50 > ema_200:
                score = 0.9
                reasons.append("Strong uptrend: Close > EMA50 > EMA200")
            elif curr_close > ema_200:
                score = 0.7
                reasons.append("Above EMA200 — medium bullish")
            else:
                score = 0.3
                trend_aligned = False
                reasons.append("Below major EMAs — counter-trend long")

        elif direction == "short":
            if curr_close < ema_50 and ema_50 < ema_200:
                score = 0.9
                reasons.append("Strong downtrend: Close < EMA50 < EMA200")
            elif curr_close < ema_200:
                score = 0.7
                reasons.append("Below EMA200 — medium bearish")
            else:
                score = 0.3
                trend_aligned = False
                reasons.append("Above major EMAs — counter-trend short")

        if curr_adx > 25:
            score += 0.1
            reasons.append(f"ADX strong: {curr_adx:.1f}")

        return trend_aligned, min(score, 1.0), reasons

    def _check_bos_choch(self, direction, ohlcv) -> Tuple[bool, float, List[str]]:
        """Check Break of Structure (BOS) and Change of Character (ChoCH)."""
        reasons = []
        score = 0.5
        confirmed = False

        highs = ohlcv["high"].iloc[-50:]
        lows = ohlcv["low"].iloc[-50:]

        # Find recent swing points
        if direction == "long":
            # BOS: price breaks above recent swing high
            recent_swing_high = highs.iloc[-20:-2].max()
            if highs.iloc[-1] > recent_swing_high:
                confirmed = True
                score = 0.8
                reasons.append("BOS confirmed: broke above swing high")

        elif direction == "short":
            recent_swing_low = lows.iloc[-20:-2].min()
            if lows.iloc[-1] < recent_swing_low:
                confirmed = True
                score = 0.8
                reasons.append("BOS confirmed: broke below swing low")

        if not confirmed:
            score = 0.3
            reasons.append("No BOS confirmation")

        return confirmed, score, reasons

    def _score_order_blocks(self, direction, price, ohlcv, atr) -> Tuple[float, bool, List[str]]:
        """Score ICT Order Block confluence."""
        reasons = []
        score = 0.5
        aligned = False

        # Simplified OB detection: last down candle before strong up move (for longs)
        # Last up candle before strong down move (for shorts)
        close = ohlcv["close"]
        open_ = ohlcv["open"]

        if direction == "long":
            # Look for a bearish candle followed by strong bullish move
            for i in range(-10, -1):
                if close.iloc[i] < open_.iloc[i]:  # Bearish candle
                    if close.iloc[i + 1] > open_.iloc[i + 1]:  # Followed by bullish
                        ob_price = (open_.iloc[i] + close.iloc[i]) / 2
                        if abs(price - ob_price) / atr < 1.5:
                            aligned = True
                            score = 0.8
                            reasons.append(f"Near bullish OB at {ob_price:.2f}")
                            break

        elif direction == "short":
            for i in range(-10, -1):
                if close.iloc[i] > open_.iloc[i]:  # Bullish candle
                    if close.iloc[i + 1] < open_.iloc[i + 1]:  # Followed by bearish
                        ob_price = (open_.iloc[i] + close.iloc[i]) / 2
                        if abs(price - ob_price) / atr < 1.5:
                            aligned = True
                            score = 0.8
                            reasons.append(f"Near bearish OB at {ob_price:.2f}")
                            break

        if not aligned:
            reasons.append("No OB confluence detected")

        return score, aligned, reasons

    def _score_session_orb(self, direction, price, ohlcv) -> Tuple[float, bool, List[str]]:
        """Score Session Opening Range Breakout alignment."""
        reasons = []
        score = 0.5
        aligned = False

        if "timestamp" not in ohlcv.columns and not isinstance(ohlcv.index, pd.DatetimeIndex):
            return score, aligned, ["No timestamp data for session analysis"]

        # Determine current session
        try:
            if isinstance(ohlcv.index, pd.DatetimeIndex):
                current_hour = ohlcv.index[-1].hour
            else:
                ts = pd.to_datetime(ohlcv["timestamp"].iloc[-1], unit="ms")
                current_hour = ts.hour

            # London: 08:00-12:00 UTC
            # New York: 13:00-17:00 UTC
            # Asian: 00:00-08:00 UTC

            if 8 <= current_hour < 12:
                session = "london"
            elif 13 <= current_hour < 17:
                session = "new_york"
            else:
                session = "asian"

            # Check if price is breaking out of opening range
            if len(ohlcv) >= 30:
                opening_range_high = ohlcv["high"].iloc[-30:-20].max()
                opening_range_low = ohlcv["low"].iloc[-30:-20].min()

                if direction == "long" and price > opening_range_high:
                    aligned = True
                    score = 0.8
                    reasons.append(f"{session.upper()} ORB breakout (long)")
                elif direction == "short" and price < opening_range_low:
                    aligned = True
                    score = 0.8
                    reasons.append(f"{session.upper()} ORB breakout (short)")

        except Exception as e:
            reasons.append(f"Session analysis error: {e}")

        if not aligned:
            reasons.append("No session ORB alignment")

        return score, aligned, reasons

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _compute_atr(self, ohlcv: pd.DataFrame, period: int = 14) -> float:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]

    def _compute_adx(self, ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        mask = plus_dm > minus_dm
        plus_dm = plus_dm * mask
        minus_dm = minus_dm * (~mask)
        atr = self._compute_atr_full(ohlcv, period)
        plus_di = 100 * plus_dm.ewm(span=period).mean() / atr.replace(0, np.inf)
        minus_di = 100 * minus_dm.ewm(span=period).mean() / atr.replace(0, np.inf)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.inf)
        return dx.ewm(span=period).mean()

    def _compute_atr_full(self, ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _find_round_numbers(self, price: float, atr: float) -> List[float]:
        """Find round numbers near current price."""
        magnitude = 10 ** (len(str(int(price))) - 1)
        base = int(price / magnitude) * magnitude
        return [base - magnitude, base, base + magnitude, base + 2 * magnitude]
