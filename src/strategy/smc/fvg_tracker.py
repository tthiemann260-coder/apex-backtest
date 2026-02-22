"""
fvg_tracker.py — Fair Value Gap state machine for SMC.

Tracks FVGs with full lifecycle: OPEN → TOUCHED → MITIGATED → INVERTED → EXPIRED.

Design:
- Detection from last 3 bars in buffer (no lookahead).
- Mitigation modes: "wick" (any touch), "50pct" (50% fill), "close" (full close through).
- Memory-bounded: oldest gaps expire when max_fvgs exceeded.
- Age-based expiry: gaps older than max_age_bars auto-expire.
- Same-bar guard: a gap cannot be mitigated on the bar it was detected.

Requirement: SMC-03
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.events import MarketEvent


class FVGState(Enum):
    OPEN = "OPEN"
    TOUCHED = "TOUCHED"
    MITIGATED = "MITIGATED"
    INVERTED = "INVERTED"
    EXPIRED = "EXPIRED"


@dataclass
class FairValueGap:
    """Mutable FVG with state machine transitions."""
    direction: str  # "bullish" or "bearish"
    top: Decimal
    bottom: Decimal
    midpoint: Decimal
    formed_bar_idx: int
    state: FVGState = FVGState.OPEN

    @property
    def size(self) -> Decimal:
        return self.top - self.bottom


class FVGTracker:
    """Detect and track Fair Value Gaps with lifecycle management.

    Parameters
    ----------
    max_fvgs : int
        Maximum tracked gaps. Oldest OPEN gap expires when exceeded. Default: 20.
    max_age_bars : int
        Gaps older than this many bars auto-expire. Default: 100.
    min_size_atr_mult : float
        Minimum gap size as multiple of ATR. Default: 0.5.
    mitigation_mode : str
        How mitigation is determined: "wick", "50pct", or "close". Default: "wick".
    """

    def __init__(
        self,
        max_fvgs: int = 20,
        max_age_bars: int = 100,
        min_size_atr_mult: float = 0.5,
        mitigation_mode: str = "wick",
    ) -> None:
        if mitigation_mode not in ("wick", "50pct", "close"):
            raise ValueError(f"Invalid mitigation_mode: {mitigation_mode}")
        self._max_fvgs = max_fvgs
        self._max_age_bars = max_age_bars
        self._min_size_atr_mult = Decimal(str(min_size_atr_mult))
        self._mitigation_mode = mitigation_mode
        self._gaps: list[FairValueGap] = []

    @property
    def all_gaps(self) -> list[FairValueGap]:
        return list(self._gaps)

    def get_active_fvgs(self, direction: Optional[str] = None) -> list[FairValueGap]:
        """Return gaps in OPEN or TOUCHED state, optionally filtered by direction."""
        result = [g for g in self._gaps if g.state in (FVGState.OPEN, FVGState.TOUCHED)]
        if direction is not None:
            result = [g for g in result if g.direction == direction]
        return result

    def detect_and_register(
        self,
        bar_buffer: list[MarketEvent],
        bar_idx: int,
        atr: Decimal,
    ) -> Optional[FairValueGap]:
        """Detect a new FVG from the last 3 bars and register it.

        Parameters
        ----------
        bar_buffer : list[MarketEvent]
            Rolling bar buffer.
        bar_idx : int
            Current absolute bar index.
        atr : Decimal
            Current ATR value for size filtering.

        Returns
        -------
        Optional[FairValueGap]
            Newly detected gap, or None.
        """
        if len(bar_buffer) < 3:
            return None

        bar1 = bar_buffer[-3]
        bar3 = bar_buffer[-1]
        min_size = atr * self._min_size_atr_mult

        gap: Optional[FairValueGap] = None

        # Bullish FVG: bar1.high < bar3.low
        if bar1.high < bar3.low:
            size = bar3.low - bar1.high
            if size >= min_size:
                top = bar3.low
                bottom = bar1.high
                gap = FairValueGap(
                    direction="bullish",
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2,
                    formed_bar_idx=bar_idx,
                )

        # Bearish FVG: bar1.low > bar3.high
        elif bar1.low > bar3.high:
            size = bar1.low - bar3.high
            if size >= min_size:
                top = bar1.low
                bottom = bar3.high
                gap = FairValueGap(
                    direction="bearish",
                    top=top,
                    bottom=bottom,
                    midpoint=(top + bottom) / 2,
                    formed_bar_idx=bar_idx,
                )

        if gap is not None:
            self._gaps.append(gap)
            self._enforce_memory_limit()

        return gap

    def update_all_states(self, event: MarketEvent, bar_idx: int) -> None:
        """Transition all tracked gaps based on current bar.

        Parameters
        ----------
        event : MarketEvent
            Current bar's OHLCV data.
        bar_idx : int
            Current absolute bar index.
        """
        for gap in self._gaps:
            if gap.state in (FVGState.INVERTED, FVGState.EXPIRED):
                continue

            # MITIGATED → INVERTED check (before skipping)
            if gap.state == FVGState.MITIGATED:
                self._check_inversion(gap, event)
                continue

            # Age-based expiry
            age = bar_idx - gap.formed_bar_idx
            if age > self._max_age_bars:
                gap.state = FVGState.EXPIRED
                continue

            # Same-bar guard: no mitigation on formation bar
            if bar_idx <= gap.formed_bar_idx:
                continue

            self._transition_gap(gap, event)

    def _check_inversion(self, gap: FairValueGap, event: MarketEvent) -> None:
        """Check MITIGATED → INVERTED transition."""
        if gap.direction == "bullish":
            if event.close < gap.bottom:
                gap.state = FVGState.INVERTED
        else:
            if event.close > gap.top:
                gap.state = FVGState.INVERTED

    def _transition_gap(self, gap: FairValueGap, event: MarketEvent) -> None:
        """Apply state transitions for a single gap."""
        if gap.direction == "bullish":
            self._transition_bullish(gap, event)
        else:
            self._transition_bearish(gap, event)

    def _transition_bullish(self, gap: FairValueGap, event: MarketEvent) -> None:
        """State transitions for a bullish FVG (gap-up)."""
        if gap.state == FVGState.OPEN:
            # OPEN → TOUCHED: wick enters zone from above (price dips into gap)
            if event.low <= gap.top:
                gap.state = FVGState.TOUCHED
                # Check immediate mitigation
                self._check_mitigation_bullish(gap, event)

        elif gap.state == FVGState.TOUCHED:
            self._check_mitigation_bullish(gap, event)

        # MITIGATED → INVERTED: close below bottom boundary
        if gap.state == FVGState.MITIGATED:
            if event.close < gap.bottom:
                gap.state = FVGState.INVERTED

    def _check_mitigation_bullish(self, gap: FairValueGap, event: MarketEvent) -> None:
        """Check if a bullish gap transitions to MITIGATED."""
        if gap.state != FVGState.TOUCHED:
            return

        if self._mitigation_mode == "wick":
            # Any wick below the bottom = mitigated
            if event.low <= gap.bottom:
                gap.state = FVGState.MITIGATED
        elif self._mitigation_mode == "50pct":
            # Wick reaches midpoint
            if event.low <= gap.midpoint:
                gap.state = FVGState.MITIGATED
        elif self._mitigation_mode == "close":
            # Close below bottom
            if event.close < gap.bottom:
                gap.state = FVGState.MITIGATED

    def _transition_bearish(self, gap: FairValueGap, event: MarketEvent) -> None:
        """State transitions for a bearish FVG (gap-down)."""
        if gap.state == FVGState.OPEN:
            # OPEN → TOUCHED: wick enters zone from below (price rises into gap)
            if event.high >= gap.bottom:
                gap.state = FVGState.TOUCHED
                self._check_mitigation_bearish(gap, event)

        elif gap.state == FVGState.TOUCHED:
            self._check_mitigation_bearish(gap, event)

        # MITIGATED → INVERTED: close above top boundary
        if gap.state == FVGState.MITIGATED:
            if event.close > gap.top:
                gap.state = FVGState.INVERTED

    def _check_mitigation_bearish(self, gap: FairValueGap, event: MarketEvent) -> None:
        """Check if a bearish gap transitions to MITIGATED."""
        if gap.state != FVGState.TOUCHED:
            return

        if self._mitigation_mode == "wick":
            if event.high >= gap.top:
                gap.state = FVGState.MITIGATED
        elif self._mitigation_mode == "50pct":
            if event.high >= gap.midpoint:
                gap.state = FVGState.MITIGATED
        elif self._mitigation_mode == "close":
            if event.close > gap.top:
                gap.state = FVGState.MITIGATED

    def _enforce_memory_limit(self) -> None:
        """Expire oldest OPEN gaps if exceeding max_fvgs."""
        active = [g for g in self._gaps if g.state in (FVGState.OPEN, FVGState.TOUCHED)]
        while len(active) > self._max_fvgs:
            # Find oldest OPEN gap and expire it
            for g in self._gaps:
                if g.state == FVGState.OPEN:
                    g.state = FVGState.EXPIRED
                    break
            else:
                # No OPEN left, expire oldest TOUCHED
                for g in self._gaps:
                    if g.state == FVGState.TOUCHED:
                        g.state = FVGState.EXPIRED
                        break
                else:
                    break
            active = [g for g in self._gaps if g.state in (FVGState.OPEN, FVGState.TOUCHED)]

        # Also prune fully terminal gaps from memory
        self._gaps = [
            g for g in self._gaps
            if g.state not in (FVGState.EXPIRED, FVGState.INVERTED)
               or (len(self._gaps) <= self._max_fvgs)
        ]
