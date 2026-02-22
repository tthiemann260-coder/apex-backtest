"""
classifier.py — Composite market regime classifier (ATR + ADX).

Combines VolatilityRegime (ATR) and TrendStrength (ADX) into a
2D classification matrix producing one of 6 MarketRegime types.

Requirement: REG-03
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.events import MarketEvent
from src.strategy.regime.atr_regime import ATRRegimeClassifier, VolatilityRegime
from src.strategy.regime.adx_classifier import ADXClassifier, TrendStrength


class RegimeType(Enum):
    STRONG_TREND = "STRONG_TREND"
    MODERATE_TREND = "MODERATE_TREND"
    WEAK_TREND = "WEAK_TREND"
    RANGING_LOW = "RANGING_LOW"
    RANGING_NORMAL = "RANGING_NORMAL"
    CHOPPY = "CHOPPY"


@dataclass(frozen=True)
class MarketRegime:
    """Immutable snapshot of the current market regime."""
    regime_type: RegimeType
    adx: Decimal
    adx_trend: str  # "rising" or "falling"
    vol_regime: VolatilityRegime
    current_atr: Decimal
    plus_di: Decimal
    minus_di: Decimal
    bullish_pressure: bool


# ---------------------------------------------------------------------------
# Classification matrix
# ---------------------------------------------------------------------------

_REGIME_MATRIX: dict[tuple[TrendStrength, VolatilityRegime], RegimeType] = {
    # ADX >= 40 (STRONG_TREND)
    (TrendStrength.STRONG_TREND, VolatilityRegime.LOW): RegimeType.WEAK_TREND,
    (TrendStrength.STRONG_TREND, VolatilityRegime.NORMAL): RegimeType.STRONG_TREND,
    (TrendStrength.STRONG_TREND, VolatilityRegime.HIGH): RegimeType.STRONG_TREND,
    # ADX 25-40 (TRENDING)
    (TrendStrength.TRENDING, VolatilityRegime.LOW): RegimeType.WEAK_TREND,
    (TrendStrength.TRENDING, VolatilityRegime.NORMAL): RegimeType.MODERATE_TREND,
    (TrendStrength.TRENDING, VolatilityRegime.HIGH): RegimeType.WEAK_TREND,
    # ADX 20-25 (WEAK_TREND)
    (TrendStrength.WEAK_TREND, VolatilityRegime.LOW): RegimeType.WEAK_TREND,
    (TrendStrength.WEAK_TREND, VolatilityRegime.NORMAL): RegimeType.WEAK_TREND,
    (TrendStrength.WEAK_TREND, VolatilityRegime.HIGH): RegimeType.WEAK_TREND,
    # ADX < 20 (RANGING)
    (TrendStrength.RANGING, VolatilityRegime.LOW): RegimeType.RANGING_LOW,
    (TrendStrength.RANGING, VolatilityRegime.NORMAL): RegimeType.RANGING_NORMAL,
    (TrendStrength.RANGING, VolatilityRegime.HIGH): RegimeType.CHOPPY,
}


class RegimeClassifier:
    """Combined ATR + ADX regime classifier.

    Parameters
    ----------
    atr_period : int
        ATR calculation period.
    adx_period : int
        ADX calculation period.
    regime_lookback : int
        Rolling window for ATR mean comparison.
    low_vol_threshold : Decimal
        ATR / mean_ATR below this → LOW volatility.
    high_vol_threshold : Decimal
        ATR / mean_ATR above this → HIGH volatility.
    """

    def __init__(
        self,
        atr_period: int = 14,
        adx_period: int = 14,
        regime_lookback: int = 50,
        low_vol_threshold: Decimal = Decimal("0.75"),
        high_vol_threshold: Decimal = Decimal("1.50"),
    ) -> None:
        self._atr_clf = ATRRegimeClassifier(
            atr_period=atr_period,
            regime_lookback=regime_lookback,
            low_threshold=low_vol_threshold,
            high_threshold=high_vol_threshold,
        )
        self._adx_clf = ADXClassifier(period=adx_period)
        self._regime: Optional[MarketRegime] = None
        self._prev_adx: Decimal = Decimal("0")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def regime(self) -> Optional[MarketRegime]:
        return self._regime

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self, event: MarketEvent, bar_buffer: list[MarketEvent],
    ) -> MarketRegime:
        """Update both classifiers and produce a MarketRegime."""
        # ATR volatility regime
        vol_regime = self._atr_clf.update(bar_buffer)

        # ADX trend strength (needs prev bar)
        if len(bar_buffer) >= 2:
            prev_bar = bar_buffer[-2]
            self._adx_clf.update(event, prev_bar)

        trend_strength = self._adx_clf.classify()
        adx = self._adx_clf.adx

        # ADX trend direction
        adx_trend = "rising" if adx >= self._prev_adx else "falling"
        self._prev_adx = adx

        # Bullish pressure: +DI > -DI
        bullish_pressure = self._adx_clf.plus_di > self._adx_clf.minus_di

        # 2D classification
        regime_type = _REGIME_MATRIX.get(
            (trend_strength, vol_regime),
            RegimeType.RANGING_NORMAL,
        )

        self._regime = MarketRegime(
            regime_type=regime_type,
            adx=adx,
            adx_trend=adx_trend,
            vol_regime=vol_regime,
            current_atr=self._atr_clf.current_atr,
            plus_di=self._adx_clf.plus_di,
            minus_di=self._adx_clf.minus_di,
            bullish_pressure=bullish_pressure,
        )

        return self._regime
