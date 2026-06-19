"""
SITA — Market Regime Detector + Liquidity Analyzer
Real-time market regime classification and liquidity mapping.

Regimes:
- trending_strong: ADX > 25, directional momentum
- trending_weak: ADX 15-25, emerging trend
- ranging: ADX < 15, mean-reverting
- volatile_breakout: ATR expansion, volume spike
- reversal: RSI extremes + divergence

Liquidity:
- Stop hunt zones: clusters of stops above/below current price
- Fair value gaps: imbalances in price delivery
- Order block proximity: institutional interest zones
- Volume profile: high/low volume nodes
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger("sita.regime")


class MarketRegime(Enum):
    TRENDING_STRONG = "trending_strong"
    TRENDING_WEAK = "trending_weak"
    RANGING = "ranging"
    VOLATILE_BREAKOUT = "volatile_breakout"
    REVERSAL = "reversal"
    UNKNOWN = "unknown"


class RegimeConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RegimeResult:
    """Current market regime assessment."""
    regime: MarketRegime
    confidence: RegimeConfidence
    adx: float
    atr: float
    rsi: float
    volatility_pct: float
    trend_direction: str      # 'up', 'down', 'flat'
    score: float              # -1 to 1 (bearish to bullish)
    description: str = ""
    strategy_recommendation: str = ""


@dataclass
class LiquidityZone:
    """A liquidity zone (stop cluster, FVG, etc.)."""
    price_level: float
    zone_type: str           # 'stop_hunt', 'fvg', 'order_block', 'volume_node'
    strength: float          # 0-1
    direction: str           # 'above' or 'below' current
    size_estimate: float     # Estimated stop size in USD terms


@dataclass
class LiquidityMap:
    """Current liquidity landscape."""
    zones: List[LiquidityZone] = field(default_factory=list)
    nearest_liquidity_above: float = 0.0
    nearest_liquidity_below: float = 0.0
    liquidity_bias: str = "neutral"   # 'bullish', 'bearish', 'neutral'
    description: str = ""


class RegimeDetector:
    """
    Real-time market regime classification.

    Uses ADX, ATR, RSI, and volume to classify the current market state.
    Regime determines which strategies are favored.
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.adx_trending = self.config.get("adx_trending", 25)
        self.adx_ranging = self.config.get("adx_ranging", 15)
        self.atr_expansion_mult = self.config.get("atr_expansion_mult", 1.5)
        self.rsi_extreme_ob = self.config.get("rsi_extreme_ob", 75)
        self.rsi_extreme_os = self.config.get("rsi_extreme_os", 25)
        self.lookback = self.config.get("regime_lookback", 100)

    def detect(self, ohlcv: pd.DataFrame) -> RegimeResult:
        """
        Detect the current market regime.

        Returns RegimeResult with regime, confidence, and strategy recommendation.
        """
        if len(ohlcv) < 50:
            return RegimeResult(
                regime=MarketRegime.UNKNOWN,
                confidence=RegimeConfidence.LOW,
                adx=0, atr=0, rsi=50, volatility_pct=0,
                trend_direction="flat", score=0,
                description="Insufficient data",
            )

        close = ohlcv["close"]
        high = ohlcv["high"]
        low = ohlcv["low"]
        volume = ohlcv["volume"] if "volume" in ohlcv.columns else pd.Series(1.0, index=close.index)

        # Compute indicators
        adx = self._compute_adx(ohlcv)
        atr = self._compute_atr(ohlcv)
        rsi = self._compute_rsi(close)
        ema_21 = close.ewm(span=21).mean().iloc[-1]
        ema_50 = close.ewm(span=50).mean().iloc[-1]

        curr_adx = adx.iloc[-1] if not adx.empty else 0
        curr_atr = atr.iloc[-1] if not atr.empty else 0
        curr_rsi = rsi.iloc[-1] if not rsi.empty else 50
        curr_price = close.iloc[-1]

        # Volatility as percentage
        volatility_pct = (curr_atr / curr_price * 100) if curr_price > 0 else 0

        # Trend direction
        if curr_price > ema_21 > ema_50:
            trend_direction = "up"
        elif curr_price < ema_21 < ema_50:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        # ATR expansion (volatility spike)
        atr_sma = atr.rolling(20).mean().iloc[-1] if not atr.empty else curr_atr
        atr_expanding = curr_atr > atr_sma * self.atr_expansion_mult if atr_sma > 0 else False

        # Volume spike
        vol_sma = volume.rolling(20).mean().iloc[-1]
        volume_spike = volume.iloc[-1] > vol_sma * 2 if vol_sma > 0 else False

        # ─── Regime Classification ──────────────────────────────────────

        regime = MarketRegime.UNKNOWN
        confidence = RegimeConfidence.LOW
        score = 0.0
        strategy_rec = "hold"

        # Priority 1: Reversal (RI extremes)
        if curr_rsi > self.rsi_extreme_ob or curr_rsi < self.rsi_extreme_os:
            regime = MarketRegime.REVERSAL
            confidence = RegimeConfidence.HIGH if curr_adx > 20 else RegimeConfidence.MEDIUM
            score = -(curr_rsi - 50) / 50  # Negative when overbought, positive when oversold
            strategy_rec = "mean_reversion"
            description = f"RSI extreme: {curr_rsi:.1f}"

        # Priority 2: Volatile breakout
        elif atr_expanding and volume_spike:
            regime = MarketRegime.VOLATILE_BREAKOUT
            confidence = RegimeConfidence.HIGH
            score = 0.3 if trend_direction == "up" else -0.3
            strategy_rec = "momentum_breakout"
            description = f"ATR expansion + volume spike: {volatility_pct:.2f}%"

        # Priority 3: Trending
        elif curr_adx > self.adx_trending:
            if trend_direction == "up":
                regime = MarketRegime.TRENDING_STRONG
                score = min(curr_adx / 50, 1.0)
                strategy_rec = "trend_following"
            elif trend_direction == "down":
                regime = MarketRegime.TRENDING_STRONG
                score = -min(curr_adx / 50, 1.0)
                strategy_rec = "trend_following"
            else:
                regime = MarketRegime.TRENDING_WEAK
                score = 0.2
                strategy_rec = "ema_crossover"
            confidence = RegimeConfidence.HIGH if curr_adx > 35 else RegimeConfidence.MEDIUM
            description = f"ADX={curr_adx:.1f}, trend={trend_direction}"

        # Priority 4: Weak trend
        elif curr_adx > self.adx_ranging:
            regime = MarketRegime.TRENDING_WEAK
            confidence = RegimeConfidence.MEDIUM
            score = 0.1 if trend_direction == "up" else -0.1
            strategy_rec = "ema_crossover"
            description = f"Weak trend: ADX={curr_adx:.1f}"

        # Priority 5: Ranging
        else:
            regime = MarketRegime.RANGING
            confidence = RegimeConfidence.HIGH if curr_adx < 12 else RegimeConfidence.MEDIUM
            score = 0.0
            strategy_rec = "scalping"
            description = f"Ranging: ADX={curr_adx:.1f}"

        return RegimeResult(
            regime=regime,
            confidence=confidence,
            adx=round(curr_adx, 1),
            atr=round(curr_atr, 4),
            rsi=round(curr_rsi, 1),
            volatility_pct=round(volatility_pct, 4),
            trend_direction=trend_direction,
            score=round(score, 3),
            description=description,
            strategy_recommendation=strategy_rec,
        )

    def get_strategy_weights(self, regime: MarketRegime) -> Dict[str, float]:
        """
        Get strategy weights based on current regime.
        Regime-aware strategy selection — only trade what fits.
        """
        weights = {
            "trending_strong": {
                "trend_following": 1.0,
                "momentum_breakout": 0.8,
                "ema_crossover": 0.6,
                "sma_crossover": 0.5,
                "rsi_reversal": 0.1,    # Don't fade strong trends
                "mean_reversion": 0.1,
                "scalping": 0.2,
            },
            "trending_weak": {
                "ema_crossover": 1.0,
                "sma_crossover": 0.8,
                "trend_following": 0.6,
                "momentum_breakout": 0.4,
                "rsi_reversal": 0.3,
                "mean_reversion": 0.3,
                "scalping": 0.4,
            },
            "ranging": {
                "scalping": 1.0,
                "mean_reversion": 0.9,
                "rsi_reversal": 0.8,
                "ema_crossover": 0.3,
                "sma_crossover": 0.2,
                "trend_following": 0.1,
                "momentum_breakout": 0.1,
            },
            "volatile_breakout": {
                "momentum_breakout": 1.0,
                "trend_following": 0.7,
                "rsi_reversal": 0.5,
                "ema_crossover": 0.4,
                "scalping": 0.2,       # Avoid choppy breakouts
                "mean_reversion": 0.1,
                "sma_crossover": 0.3,
            },
            "reversal": {
                "rsi_reversal": 1.0,
                "mean_reversion": 0.9,
                "scalping": 0.5,
                "ema_crossover": 0.2,
                "trend_following": 0.1,
                "momentum_breakout": 0.1,
                "sma_crossover": 0.2,
            },
        }
        regime_key = regime.value if isinstance(regime, MarketRegime) else regime
        return weights.get(regime_key, {s: 0.5 for s in ["ema_crossover", "sma_crossover", "momentum_breakout", "scalping", "trend_following", "mean_reversion", "rsi_reversal"]})

    # ─── Indicator Helpers ─────────────────────────────────────────────────

    def _compute_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss.replace(0, np.inf)
        return 100 - (100 / (1 + rs))

    def _compute_atr(self, ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

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
        atr = self._compute_atr(ohlcv, period)
        plus_di = 100 * plus_dm.ewm(span=period).mean() / atr.replace(0, np.inf)
        minus_di = 100 * minus_dm.ewm(span=period).mean() / atr.replace(0, np.inf)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.inf)
        return dx.ewm(span=period).mean()


class LiquidityAnalyzer:
    """
    Liquidity mapping — find where stops cluster and institutional interest lies.

    Key concepts:
    - Stop hunts: liquidity pools above recent highs and below recent lows
    - Fair value gaps: price imbalances that attract price back
    - Volume nodes: high-volume price levels that act as magnets
    """

    def __init__(self, config: Dict = None):
        self.config = config or {}

    def analyze(self, ohlcv: pd.DataFrame, current_price: float) -> LiquidityMap:
        """
        Analyze the current liquidity landscape.
        """
        zones = []
        high = ohlcv["high"]
        low = ohlcv["low"]
        close = ohlcv["close"]
        volume = ohlcv["volume"] if "volume" in ohlcv.columns else pd.Series(1.0, index=close.index)

        # ─── Stop Hunt Zones ─────────────────────────────────────────────
        # Above recent swing highs (buy stops)
        recent_highs = high.iloc[-50:]
        swing_highs = self._find_swing_highs(recent_highs)
        for sh in swing_highs:
            if sh > current_price:
                zones.append(LiquidityZone(
                    price_level=sh,
                    zone_type="stop_hunt",
                    strength=0.7,
                    direction="above",
                    size_estimate=0,
                ))

        # Below recent swing lows (sell stops)
        recent_lows = low.iloc[-50:]
        swing_lows = self._find_swing_lows(recent_lows)
        for sl in swing_lows:
            if sl < current_price:
                zones.append(LiquidityZone(
                    price_level=sl,
                    zone_type="stop_hunt",
                    strength=0.7,
                    direction="below",
                    size_estimate=0,
                ))

        # ─── Fair Value Gaps ─────────────────────────────────────────────
        fvgs = self._find_fvgs(ohlcv)
        for fvg in fvgs:
            if abs(fvg - current_price) / current_price < 0.02:  # Within 2%
                direction = "above" if fvg > current_price else "below"
                zones.append(LiquidityZone(
                    price_level=fvg,
                    zone_type="fvg",
                    strength=0.6,
                    direction=direction,
                    size_estimate=0,
                ))

        # ─── Volume Nodes ────────────────────────────────────────────────
        if "volume" in ohlcv.columns:
            vol_nodes = self._find_volume_nodes(ohlcv)
            for vn in vol_nodes:
                if abs(vn - current_price) / current_price < 0.03:  # Within 3%
                    direction = "above" if vn > current_price else "below"
                    zones.append(LiquidityZone(
                        price_level=vn,
                        zone_type="volume_node",
                        strength=0.5,
                        direction=direction,
                        size_estimate=0,
                    ))

        # ─── Summary ─────────────────────────────────────────────────────
        above_zones = [z for z in zones if z.direction == "above"]
        below_zones = [z for z in zones if z.direction == "below"]

        nearest_above = min([z.price_level for z in above_zones]) if above_zones else 0
        nearest_below = max([z.price_level for z in below_zones]) if below_zones else 0

        # Bias: more liquidity above = bullish (stops to hunt up)
        # More liquidity below = bearish (stops to hunt down)
        above_strength = sum(z.strength for z in above_zones)
        below_strength = sum(z.strength for z in below_zones)

        if above_strength > below_strength * 1.5:
            bias = "bullish"
        elif below_strength > above_strength * 1.5:
            bias = "bearish"
        else:
            bias = "neutral"

        description = f"{len(zones)} zones: {len(above_zones)} above, {len(below_zones)} below. Bias: {bias}"

        return LiquidityMap(
            zones=zones,
            nearest_liquidity_above=nearest_above,
            nearest_liquidity_below=nearest_below,
            liquidity_bias=bias,
            description=description,
        )

    def _find_swing_highs(self, highs: pd.Series, order: int = 5) -> List[float]:
        """Find swing high points."""
        swing_highs = []
        for i in range(order, len(highs) - order):
            if all(highs.iloc[i] >= highs.iloc[i - j] for j in range(1, order + 1)) and \
               all(highs.iloc[i] >= highs.iloc[i + j] for j in range(1, order + 1)):
                swing_highs.append(float(highs.iloc[i]))
        return swing_highs[-5:]  # Last 5

    def _find_swing_lows(self, lows: pd.Series, order: int = 5) -> List[float]:
        """Find swing low points."""
        swing_lows = []
        for i in range(order, len(lows) - order):
            if all(lows.iloc[i] <= lows.iloc[i - j] for j in range(1, order + 1)) and \
               all(lows.iloc[i] <= lows.iloc[i + j] for j in range(1, order + 1)):
                swing_lows.append(float(lows.iloc[i]))
        return swing_lows[-5:]

    def _find_fvgs(self, ohlcv: pd.DataFrame) -> List[float]:
        """Find fair value gaps (imbalances)."""
        fvgs = []
        high = ohlcv["high"]
        low = ohlcv["low"]

        for i in range(2, len(ohlcv) - 1):
            # Bullish FVG: gap between candle 1 high and candle 3 low
            if low.iloc[i + 1] > high.iloc[i - 1]:
                fvg_price = (low.iloc[i + 1] + high.iloc[i - 1]) / 2
                fvgs.append(fvg_price)
            # Bearish FVG: gap between candle 1 low and candle 3 high
            elif high.iloc[i + 1] < low.iloc[i - 1]:
                fvg_price = (high.iloc[i + 1] + low.iloc[i - 1]) / 2
                fvgs.append(fvg_price)

        return fvgs[-10:]

    def _find_volume_nodes(self, ohlcv: pd.DataFrame, bins: int = 20) -> List[float]:
        """Find high-volume price nodes."""
        close = ohlcv["close"]
        volume = ohlcv["volume"]

        # Create price bins
        price_range = close.max() - close.min()
        if price_range <= 0:
            return []

        bin_size = price_range / bins
        volume_profile = {}

        for i in range(len(close)):
            bin_idx = int((close.iloc[i] - close.min()) / bin_size)
            bin_price = close.min() + bin_idx * bin_size
            volume_profile[bin_price] = volume_profile.get(bin_price, 0) + volume.iloc[i]

        # Find high-volume nodes (top 20%)
        if not volume_profile:
            return []

        sorted_nodes = sorted(volume_profile.items(), key=lambda x: x[1], reverse=True)
        top_count = max(1, len(sorted_nodes) // 5)
        return [price for price, vol in sorted_nodes[:top_count]]
