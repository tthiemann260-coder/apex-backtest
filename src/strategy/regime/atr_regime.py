"""
atr_regime.py — ATR-based volatility regime classifier.

Classifies the current market into LOW, NORMAL, or HIGH volatility
by comparing the current ATR to its rolling mean.

Requirement: REG-01
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.events import MarketEvent


class VolatilityRegime(Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class ATRRegimeClassifier:
    """Classify volatility regime via ATR vs. rolling mean ATR.

    Parameters
    ----------
    atr_period : int
        Period for ATR calculation.
    regime_lookback : int
        Number of ATR values kept for the rolling mean.
    low_threshold : Decimal
        ATR / mean_ATR below this → LOW.
    high_threshold : Decimal
        ATR / mean_ATR above this → HIGH.
    """

    def __init__(
        self,
        atr_period: int = 14,
        regime_lookback: int = 50,
        low_threshold: Decimal = Decimal("0.75"),
        high_threshold: Decimal = Decimal("1.50"),
    ) -> None:
        self._atr_period = atr_period
        self._regime_lookback = regime_lookback
        self._low_threshold = low_threshold
        self._high_threshold = high_threshold
        self._atr_history: deque[Decimal] = deque(maxlen=regime_lookback)
        self._current_atr: Decimal = Decimal("0")
        self._regime: VolatilityRegime = VolatilityRegime.NORMAL

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def regime(self) -> VolatilityRegime:
        return self._regime

    @property
    def current_atr(self) -> Decimal:
        return self._current_atr

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, bar_buffer: list[MarketEvent]) -> VolatilityRegime:
        """Compute ATR from bar_buffer and classify volatility regime."""
        atr = self._compute_atr(bar_buffer)
        if atr is None:
            self._regime = VolatilityRegime.NORMAL
            return self._regime

        self._current_atr = atr
        self._atr_history.append(atr)

        # Warmup guard: not enough history to compare
        if len(self._atr_history) < self._atr_period:
            self._regime = VolatilityRegime.NORMAL
            return self._regime

        mean_atr = sum(self._atr_history) / Decimal(str(len(self._atr_history)))
        if mean_atr == 0:
            self._regime = VolatilityRegime.NORMAL
            return self._regime

        ratio = atr / mean_atr
        if ratio < self._low_threshold:
            self._regime = VolatilityRegime.LOW
        elif ratio > self._high_threshold:
            self._regime = VolatilityRegime.HIGH
        else:
            self._regime = VolatilityRegime.NORMAL

        return self._regime

    # ------------------------------------------------------------------
    # Internal ATR
    # ------------------------------------------------------------------

    def _compute_atr(self, bar_buffer: list[MarketEvent]) -> Optional[Decimal]:
        """Simple ATR identical to ICTStrategy._update_atr."""
        if len(bar_buffer) < 2:
            return None

        period = min(self._atr_period, len(bar_buffer) - 1)
        if period < 1:
            return None

        tr_sum = Decimal("0")
        for i in range(-period, 0):
            bar = bar_buffer[i]
            prev_close = bar_buffer[i - 1].close
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
            tr_sum += tr

        return tr_sum / Decimal(str(period))
