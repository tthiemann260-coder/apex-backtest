"""
swing_detector.py — Fractal-based swing high/low detection for SMC.

Detects confirmed swing highs and swing lows using a fractal approach:
- A swing high at index i is confirmed when it has `strength` bars on each
  side with strictly lower highs.
- A swing low at index i is confirmed when it has `strength` bars on each
  side with strictly higher lows.

Confirmation happens only after `strength` bars to the RIGHT have formed,
eliminating any lookahead bias.

Requirement: SMC-02 (partial)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent


@dataclass(frozen=True)
class SwingPoint:
    """Immutable record of a confirmed swing high or low."""
    price: Decimal
    timestamp: datetime
    abs_idx: int  # Absolute bar index in the full series


class SwingDetector:
    """Fractal swing detector with configurable strength.

    Parameters
    ----------
    strength : int
        Number of bars on each side required to confirm a swing.
        Minimum bars needed: ``2 * strength + 1``.
        Default: 2 (classic 5-bar fractal).
    max_history : int
        Maximum swing points to keep per direction. Default: 50.
    """

    def __init__(self, strength: int = 2, max_history: int = 50) -> None:
        if strength < 1:
            raise ValueError(f"strength must be >= 1, got {strength}")
        self._strength = strength
        self._max_history = max_history
        self._swing_highs: list[SwingPoint] = []
        self._swing_lows: list[SwingPoint] = []

    @property
    def swing_highs(self) -> list[SwingPoint]:
        return list(self._swing_highs)

    @property
    def swing_lows(self) -> list[SwingPoint]:
        return list(self._swing_lows)

    @property
    def strength(self) -> int:
        return self._strength

    def detect_confirmed_swings(
        self,
        bar_buffer: list[MarketEvent],
        bar_count: int,
    ) -> tuple[list[SwingPoint], list[SwingPoint]]:
        """Check for newly confirmed swings in the buffer.

        The candidate bar sits at ``buf[-(strength+1)]`` — the middle of
        the fractal window.  The right-side confirmation bars are
        ``buf[-strength:]`` through ``buf[-1]``.

        Parameters
        ----------
        bar_buffer : list[MarketEvent]
            Rolling buffer of historical bars (oldest first).
        bar_count : int
            Current absolute bar index (1-based count of bars seen so far).

        Returns
        -------
        tuple[list[SwingPoint], list[SwingPoint]]
            ``(new_highs, new_lows)`` — newly confirmed swings this bar.
            Each list is typically 0 or 1 elements.
        """
        min_bars = 2 * self._strength + 1
        if len(bar_buffer) < min_bars:
            return [], []

        new_highs: list[SwingPoint] = []
        new_lows: list[SwingPoint] = []

        s = self._strength
        candidate_idx = -(s + 1)  # Index into buffer
        candidate = bar_buffer[candidate_idx]

        # Absolute index of the candidate bar
        abs_idx = bar_count - s  # bar_count is 1-based after current bar

        # --- Swing High check ---
        is_swing_high = True
        for offset in range(1, s + 1):
            left = bar_buffer[candidate_idx - offset]
            right = bar_buffer[candidate_idx + offset]
            if left.high >= candidate.high or right.high >= candidate.high:
                is_swing_high = False
                break

        if is_swing_high:
            sp = SwingPoint(
                price=candidate.high,
                timestamp=candidate.timestamp,
                abs_idx=abs_idx,
            )
            # Avoid duplicate detection (same abs_idx)
            if not self._swing_highs or self._swing_highs[-1].abs_idx != abs_idx:
                self._swing_highs.append(sp)
                new_highs.append(sp)
                if len(self._swing_highs) > self._max_history:
                    self._swing_highs = self._swing_highs[-self._max_history:]

        # --- Swing Low check ---
        is_swing_low = True
        for offset in range(1, s + 1):
            left = bar_buffer[candidate_idx - offset]
            right = bar_buffer[candidate_idx + offset]
            if left.low <= candidate.low or right.low <= candidate.low:
                is_swing_low = False
                break

        if is_swing_low:
            sp = SwingPoint(
                price=candidate.low,
                timestamp=candidate.timestamp,
                abs_idx=abs_idx,
            )
            if not self._swing_lows or self._swing_lows[-1].abs_idx != abs_idx:
                self._swing_lows.append(sp)
                new_lows.append(sp)
                if len(self._swing_lows) > self._max_history:
                    self._swing_lows = self._swing_lows[-self._max_history:]

        return new_highs, new_lows
