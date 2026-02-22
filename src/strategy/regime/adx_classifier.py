"""
adx_classifier.py — Wilder's ADX trend-strength classifier.

Computes ADX from first principles (no external library) using
Wilder's smoothing, then classifies trend strength into four buckets.

Requirement: REG-02
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum

from src.events import MarketEvent


class TrendStrength(Enum):
    RANGING = "RANGING"
    WEAK_TREND = "WEAK_TREND"
    TRENDING = "TRENDING"
    STRONG_TREND = "STRONG_TREND"


class ADXClassifier:
    """Compute Wilder's ADX and classify trend strength.

    Two-phase algorithm:
      Phase A (first ``period`` bars): accumulate raw TR / +DM / -DM.
      Phase B (subsequent bars): Wilder's smoothing for TR, +DM, -DM, ADX.

    Parameters
    ----------
    period : int
        Smoothing period (default 14).
    """

    def __init__(self, period: int = 14) -> None:
        self._period = period

        # Phase A accumulators
        self._raw_tr: list[Decimal] = []
        self._raw_plus_dm: list[Decimal] = []
        self._raw_minus_dm: list[Decimal] = []

        # Phase B smoothed values
        self._smooth_tr: Decimal = Decimal("0")
        self._smooth_plus_dm: Decimal = Decimal("0")
        self._smooth_minus_dm: Decimal = Decimal("0")

        # ADX state
        self._dx_accumulator: list[Decimal] = []
        self._adx: Decimal = Decimal("0")
        self._adx_seeded: bool = False

        # DI values
        self._plus_di: Decimal = Decimal("0")
        self._minus_di: Decimal = Decimal("0")

        # Bar counter
        self._bar_count: int = 0
        self._phase_a_done: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def adx(self) -> Decimal:
        return self._adx

    @property
    def plus_di(self) -> Decimal:
        return self._plus_di

    @property
    def minus_di(self) -> Decimal:
        return self._minus_di

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, bar: MarketEvent, prev_bar: MarketEvent) -> Decimal:
        """Feed a new bar pair and return current ADX value."""
        self._bar_count += 1

        # Compute True Range, +DM, -DM
        tr = self._true_range(bar, prev_bar)
        plus_dm, minus_dm = self._directional_movement(bar, prev_bar)

        if not self._phase_a_done:
            self._phase_a(tr, plus_dm, minus_dm)
        else:
            self._phase_b(tr, plus_dm, minus_dm)

        return self._adx

    def classify(self) -> TrendStrength:
        """Classify current ADX into trend-strength bucket."""
        if self._adx < Decimal("20"):
            return TrendStrength.RANGING
        elif self._adx < Decimal("25"):
            return TrendStrength.WEAK_TREND
        elif self._adx < Decimal("40"):
            return TrendStrength.TRENDING
        else:
            return TrendStrength.STRONG_TREND

    # ------------------------------------------------------------------
    # Phase A — Initial accumulation
    # ------------------------------------------------------------------

    def _phase_a(
        self, tr: Decimal, plus_dm: Decimal, minus_dm: Decimal,
    ) -> None:
        """Collect first ``period`` values, then seed smoothed sums."""
        self._raw_tr.append(tr)
        self._raw_plus_dm.append(plus_dm)
        self._raw_minus_dm.append(minus_dm)

        if len(self._raw_tr) < self._period:
            return

        # Seed Phase B smoothed values with sums
        self._smooth_tr = sum(self._raw_tr)
        self._smooth_plus_dm = sum(self._raw_plus_dm)
        self._smooth_minus_dm = sum(self._raw_minus_dm)

        # Compute first DI values and DX
        self._update_di()
        dx = self._compute_dx()
        self._dx_accumulator.append(dx)

        self._phase_a_done = True
        # Free raw accumulators
        self._raw_tr.clear()
        self._raw_plus_dm.clear()
        self._raw_minus_dm.clear()

    # ------------------------------------------------------------------
    # Phase B — Wilder's Smoothing
    # ------------------------------------------------------------------

    def _phase_b(
        self, tr: Decimal, plus_dm: Decimal, minus_dm: Decimal,
    ) -> None:
        """Apply Wilder's smoothing and update ADX."""
        p = Decimal(str(self._period))

        # Wilder's smoothing: Smooth = Smooth - Smooth/period + new_value
        self._smooth_tr = self._smooth_tr - self._smooth_tr / p + tr
        self._smooth_plus_dm = self._smooth_plus_dm - self._smooth_plus_dm / p + plus_dm
        self._smooth_minus_dm = self._smooth_minus_dm - self._smooth_minus_dm / p + minus_dm

        self._update_di()
        dx = self._compute_dx()

        if not self._adx_seeded:
            # Collect period DX values for ADX seed
            self._dx_accumulator.append(dx)
            if len(self._dx_accumulator) >= self._period:
                self._adx = sum(self._dx_accumulator) / p
                self._adx_seeded = True
                self._dx_accumulator.clear()
        else:
            # ADX smoothing: ADX = (ADX * (period-1) + DX) / period
            self._adx = (self._adx * (p - Decimal("1")) + dx) / p

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _true_range(bar: MarketEvent, prev_bar: MarketEvent) -> Decimal:
        """Compute True Range."""
        return max(
            bar.high - bar.low,
            abs(bar.high - prev_bar.close),
            abs(bar.low - prev_bar.close),
        )

    @staticmethod
    def _directional_movement(
        bar: MarketEvent, prev_bar: MarketEvent,
    ) -> tuple[Decimal, Decimal]:
        """Compute +DM and -DM."""
        up_move = bar.high - prev_bar.high
        down_move = prev_bar.low - bar.low

        plus_dm = up_move if (up_move > down_move and up_move > 0) else Decimal("0")
        minus_dm = down_move if (down_move > up_move and down_move > 0) else Decimal("0")

        return plus_dm, minus_dm

    def _update_di(self) -> None:
        """Compute +DI and -DI from smoothed values."""
        if self._smooth_tr == 0:
            self._plus_di = Decimal("0")
            self._minus_di = Decimal("0")
            return
        self._plus_di = (self._smooth_plus_dm / self._smooth_tr) * Decimal("100")
        self._minus_di = (self._smooth_minus_dm / self._smooth_tr) * Decimal("100")

    def _compute_dx(self) -> Decimal:
        """Compute DX from +DI and -DI."""
        di_sum = self._plus_di + self._minus_di
        if di_sum == 0:
            return Decimal("0")
        return (abs(self._plus_di - self._minus_di) / di_sum) * Decimal("100")
