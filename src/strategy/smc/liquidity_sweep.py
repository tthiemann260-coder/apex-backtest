"""
liquidity_sweep.py — ICT Liquidity Sweep detection for SMC.

Detects when price sweeps beyond a swing high/low (taking liquidity) and
then closes back inside the range, confirming a stop-hunt / liquidity grab.

- Bullish sweep: price wicks below a swing low then closes above it.
- Bearish sweep: price wicks above a swing high then closes below it.

Filters:
- Minimum sweep depth (ATR-relative) to avoid noise.
- Per-level cooldown to prevent duplicate signals on the same swing.
- Swept-level tracking so each swing is only swept once.

Requirement: ICT-01
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent
from src.strategy.smc.swing_detector import SwingPoint


@dataclass(frozen=True)
class LiquiditySweep:
    """Immutable record of a confirmed liquidity sweep event."""
    direction: str        # "bullish" (swept lows) or "bearish" (swept highs)
    swept_level: Decimal  # The swing price that was taken
    sweep_wick: Decimal   # Wick tip of the sweep candle
    sweep_bar_idx: int
    timestamp: datetime
    confirmed: bool       # True once close back inside range


class LiquiditySweepDetector:
    """Detects liquidity sweeps at swing highs/lows.

    Parameters
    ----------
    min_depth_atr_mult : float
        Minimum sweep depth as a fraction of ATR. Sweeps shallower than
        ``min_depth_atr_mult * current_atr`` are discarded. Default: 0.1.
    cooldown_bars : int
        Per-level cooldown in bars.  After a sweep is detected at a given
        swing, that swing is ignored for the next *cooldown_bars*. Default: 10.
    max_sweeps : int
        Maximum number of sweep records to retain in memory. Default: 30.
    """

    def __init__(
        self,
        min_depth_atr_mult: float = 0.1,
        cooldown_bars: int = 10,
        max_sweeps: int = 30,
    ) -> None:
        self._min_depth_atr_mult = Decimal(str(min_depth_atr_mult))
        self._cooldown_bars = cooldown_bars
        self._max_sweeps = max_sweeps

        self._sweeps: list[LiquiditySweep] = []
        self._swept_levels: set[int] = set()           # abs_idx of swept swings
        self._cooldown_map: dict[int, int] = {}         # abs_idx -> bar_idx of last sweep

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def recent_sweeps(self) -> list[LiquiditySweep]:
        """Return a copy of the most recent sweep records."""
        return list(self._sweeps)

    @property
    def last_bullish_sweep(self) -> Optional[LiquiditySweep]:
        """Return the most recent bullish (swept lows) sweep, or None."""
        for sweep in reversed(self._sweeps):
            if sweep.direction == "bullish":
                return sweep
        return None

    @property
    def last_bearish_sweep(self) -> Optional[LiquiditySweep]:
        """Return the most recent bearish (swept highs) sweep, or None."""
        for sweep in reversed(self._sweeps):
            if sweep.direction == "bearish":
                return sweep
        return None

    def check_for_sweeps(
        self,
        event: MarketEvent,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        current_atr: Decimal,
        bar_idx: int,
    ) -> list[LiquiditySweep]:
        """Check the current bar for liquidity sweeps of known swing points.

        Parameters
        ----------
        event : MarketEvent
            Current bar data.
        swing_highs : list[SwingPoint]
            Confirmed swing highs from SwingDetector.
        swing_lows : list[SwingPoint]
            Confirmed swing lows from SwingDetector.
        current_atr : Decimal
            Current ATR value for depth filtering.
        bar_idx : int
            Absolute bar index.

        Returns
        -------
        list[LiquiditySweep]
            Newly detected sweeps on this bar (typically 0 or 1).
        """
        new_sweeps: list[LiquiditySweep] = []
        min_depth = self._min_depth_atr_mult * current_atr

        # --- Bullish sweeps: wick below swing low, close back above ---
        for sl in swing_lows:
            if sl.abs_idx in self._swept_levels:
                continue
            if self._in_cooldown(sl.abs_idx, bar_idx):
                continue
            if event.low < sl.price and event.close > sl.price:
                depth = sl.price - event.low
                if depth >= min_depth:
                    sweep = LiquiditySweep(
                        direction="bullish",
                        swept_level=sl.price,
                        sweep_wick=event.low,
                        sweep_bar_idx=bar_idx,
                        timestamp=event.timestamp,
                        confirmed=True,
                    )
                    self._register_sweep(sweep, sl.abs_idx, bar_idx)
                    new_sweeps.append(sweep)

        # --- Bearish sweeps: wick above swing high, close back below ---
        for sh in swing_highs:
            if sh.abs_idx in self._swept_levels:
                continue
            if self._in_cooldown(sh.abs_idx, bar_idx):
                continue
            if event.high > sh.price and event.close < sh.price:
                depth = event.high - sh.price
                if depth >= min_depth:
                    sweep = LiquiditySweep(
                        direction="bearish",
                        swept_level=sh.price,
                        sweep_wick=event.high,
                        sweep_bar_idx=bar_idx,
                        timestamp=event.timestamp,
                        confirmed=True,
                    )
                    self._register_sweep(sweep, sh.abs_idx, bar_idx)
                    new_sweeps.append(sweep)

        return new_sweeps

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _in_cooldown(self, swing_abs_idx: int, current_bar_idx: int) -> bool:
        """Return True if the swing is still in per-level cooldown."""
        if swing_abs_idx not in self._cooldown_map:
            return False
        return (current_bar_idx - self._cooldown_map[swing_abs_idx]) < self._cooldown_bars

    def _register_sweep(
        self,
        sweep: LiquiditySweep,
        swing_abs_idx: int,
        bar_idx: int,
    ) -> None:
        """Record a sweep and update bookkeeping."""
        self._swept_levels.add(swing_abs_idx)
        self._cooldown_map[swing_abs_idx] = bar_idx
        self._sweeps.append(sweep)
        if len(self._sweeps) > self._max_sweeps:
            self._sweeps = self._sweeps[-self._max_sweeps:]
