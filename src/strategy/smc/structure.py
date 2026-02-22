"""
structure.py — Market structure tracking (BOS / CHOCH) for SMC.

Tracks swing highs and swing lows to determine trend state and detect
Break of Structure (BOS) and Change of Character (CHOCH) events.

Rules:
- BOS (Break of Structure): break in the current trend direction, or
  any break when trend is UNDEFINED. Confirms trend continuation.
- CHOCH (Change of Character): break against the current trend.
  Signals potential reversal, flips the trend state.
- Only close-based confirmation counts (wicks are ignored).

Requirement: SMC-02 (partial)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.strategy.smc.swing_detector import SwingPoint


class TrendState(Enum):
    UNDEFINED = "UNDEFINED"
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"


class BreakType(Enum):
    BOS = "BOS"
    CHOCH = "CHOCH"


@dataclass(frozen=True)
class StructureBreak:
    """Immutable record of a BOS or CHOCH event."""
    break_type: BreakType
    direction: str  # "bullish" or "bearish"
    broken_level: Decimal
    timestamp: datetime
    bar_idx: int


class MarketStructureTracker:
    """Tracks market structure via swing highs/lows and detects BOS/CHOCH.

    Parameters
    ----------
    max_history : int
        Maximum structure break events to retain. Default: 50.
    """

    def __init__(self, max_history: int = 50) -> None:
        self._trend: TrendState = TrendState.UNDEFINED
        self._max_history = max_history

        # Last registered swings (candidates for break levels)
        self._last_swing_high: Optional[SwingPoint] = None
        self._last_swing_low: Optional[SwingPoint] = None

        # Structure break history
        self._breaks: list[StructureBreak] = []

        # Track the last BOS bar to avoid repeat signals
        self._last_break_bar: int = -1

    @property
    def trend(self) -> TrendState:
        return self._trend

    @property
    def breaks(self) -> list[StructureBreak]:
        return list(self._breaks)

    @property
    def last_swing_high(self) -> Optional[SwingPoint]:
        return self._last_swing_high

    @property
    def last_swing_low(self) -> Optional[SwingPoint]:
        return self._last_swing_low

    def on_new_swing_high(self, sh: SwingPoint) -> None:
        """Register a newly confirmed swing high."""
        self._last_swing_high = sh

    def on_new_swing_low(self, sl: SwingPoint) -> None:
        """Register a newly confirmed swing low."""
        self._last_swing_low = sl

    def on_bar_close(
        self,
        close: Decimal,
        bar_idx: int,
        timestamp: datetime,
    ) -> Optional[StructureBreak]:
        """Check if the current bar's close breaks market structure.

        Parameters
        ----------
        close : Decimal
            Close price of the current bar.
        bar_idx : int
            Absolute bar index.
        timestamp : datetime
            Timestamp of the current bar.

        Returns
        -------
        Optional[StructureBreak]
            A BOS or CHOCH event if structure broke, else None.
        """
        if bar_idx <= self._last_break_bar:
            return None

        result: Optional[StructureBreak] = None

        # --- Bullish break: close above last swing high ---
        if self._last_swing_high is not None and close > self._last_swing_high.price:
            if self._trend == TrendState.DOWNTREND:
                # Against trend → CHOCH
                result = StructureBreak(
                    break_type=BreakType.CHOCH,
                    direction="bullish",
                    broken_level=self._last_swing_high.price,
                    timestamp=timestamp,
                    bar_idx=bar_idx,
                )
                self._trend = TrendState.UPTREND
            else:
                # With trend or UNDEFINED → BOS
                result = StructureBreak(
                    break_type=BreakType.BOS,
                    direction="bullish",
                    broken_level=self._last_swing_high.price,
                    timestamp=timestamp,
                    bar_idx=bar_idx,
                )
                self._trend = TrendState.UPTREND

        # --- Bearish break: close below last swing low ---
        elif self._last_swing_low is not None and close < self._last_swing_low.price:
            if self._trend == TrendState.UPTREND:
                # Against trend → CHOCH
                result = StructureBreak(
                    break_type=BreakType.CHOCH,
                    direction="bearish",
                    broken_level=self._last_swing_low.price,
                    timestamp=timestamp,
                    bar_idx=bar_idx,
                )
                self._trend = TrendState.DOWNTREND
            else:
                # With trend or UNDEFINED → BOS
                result = StructureBreak(
                    break_type=BreakType.BOS,
                    direction="bearish",
                    broken_level=self._last_swing_low.price,
                    timestamp=timestamp,
                    bar_idx=bar_idx,
                )
                self._trend = TrendState.DOWNTREND

        if result is not None:
            self._last_break_bar = bar_idx
            self._breaks.append(result)
            if len(self._breaks) > self._max_history:
                self._breaks = self._breaks[-self._max_history:]

        return result
