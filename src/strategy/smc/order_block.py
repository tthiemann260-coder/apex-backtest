"""
order_block.py — Order Block detection for SMC.

An Order Block (OB) is the last opposing candle before a displacement move
that breaks market structure (BOS). Detection is BOS-triggered to avoid
false positives.

Design:
- ATR-based displacement filter: move >= atr * threshold to qualify.
- OB formed at buf[-k] (past), confirmed at buf[-1] (current BOS bar).
- States: ACTIVE → MITIGATED or INVALIDATED.
- Invalidation: close beyond 50% Mean Threshold of OB zone.
- No lookahead bias: OB candle is always in the past relative to BOS.

Requirement: SMC-01
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from src.events import MarketEvent
from src.strategy.smc.swing_detector import SwingPoint
from src.strategy.smc.structure import MarketStructureTracker, StructureBreak


class OBState(Enum):
    ACTIVE = "ACTIVE"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"


@dataclass
class OrderBlock:
    """Mutable Order Block with state tracking."""
    direction: str  # "bullish" or "bearish"
    ob_high: Decimal
    ob_low: Decimal
    ob_50pct: Decimal
    formed_bar_idx: int
    state: OBState = OBState.ACTIVE

    @property
    def zone_size(self) -> Decimal:
        return self.ob_high - self.ob_low


class OrderBlockDetector:
    """Detect and manage Order Blocks triggered by BOS events.

    Parameters
    ----------
    atr_mult_threshold : float
        Displacement must be >= ATR * this factor. Default: 1.5.
    ob_lookback_bars : int
        How many bars back to scan for the opposing candle. Default: 10.
    max_active_obs : int
        Maximum active OBs to track. Default: 5.
    ob_max_age_bars : int
        OBs older than this auto-invalidate. Default: 100.
    close_mitigation : bool
        If True, mitigation requires close in zone. If False, wick suffices. Default: False.
    """

    def __init__(
        self,
        atr_mult_threshold: float = 1.5,
        ob_lookback_bars: int = 10,
        max_active_obs: int = 5,
        ob_max_age_bars: int = 100,
        close_mitigation: bool = False,
    ) -> None:
        self._atr_mult = Decimal(str(atr_mult_threshold))
        self._ob_lookback = ob_lookback_bars
        self._max_active = max_active_obs
        self._ob_max_age = ob_max_age_bars
        self._close_mitigation = close_mitigation
        self._order_blocks: list[OrderBlock] = []

    @property
    def active_obs(self) -> list[OrderBlock]:
        return [ob for ob in self._order_blocks if ob.state == OBState.ACTIVE]

    @property
    def all_obs(self) -> list[OrderBlock]:
        return list(self._order_blocks)

    def scan_for_new_ob(
        self,
        bar_buffer: list[MarketEvent],
        bar_count: int,
        atr: Decimal,
        structure_break: Optional[StructureBreak] = None,
    ) -> Optional[OrderBlock]:
        """Scan for a new Order Block after a BOS event.

        Only called when a BOS has just been confirmed. Scans backward
        through the buffer to find the last opposing candle before the
        displacement move.

        Parameters
        ----------
        bar_buffer : list[MarketEvent]
            Rolling bar buffer.
        bar_count : int
            Current absolute bar index.
        atr : Decimal
            Current ATR value.
        structure_break : Optional[StructureBreak]
            The BOS/CHOCH that triggered this scan. If None, skip.

        Returns
        -------
        Optional[OrderBlock]
            Newly detected OB, or None.
        """
        if structure_break is None:
            return None

        if len(bar_buffer) < 3:
            return None

        current_bar = bar_buffer[-1]

        # Determine displacement direction from the structure break
        if structure_break.direction == "bullish":
            return self._scan_bullish_ob(bar_buffer, bar_count, atr, current_bar)
        else:
            return self._scan_bearish_ob(bar_buffer, bar_count, atr, current_bar)

    def _scan_bullish_ob(
        self,
        buf: list[MarketEvent],
        bar_count: int,
        atr: Decimal,
        current: MarketEvent,
    ) -> Optional[OrderBlock]:
        """Find bullish OB: last bearish candle before upward displacement."""
        # Check displacement: current close vs recent low
        lookback = min(self._ob_lookback, len(buf) - 1)
        scan_start = max(0, len(buf) - 1 - lookback)

        # Find recent swing low in lookback window
        recent_low = min(bar.low for bar in buf[scan_start:])
        displacement = current.close - recent_low

        if displacement < atr * self._atr_mult:
            return None

        # Find last bearish candle (close < open) before the up-move
        for i in range(len(buf) - 2, scan_start - 1, -1):
            bar = buf[i]
            if bar.close < bar.open:  # Bearish candle = the OB
                ob_idx = bar_count - (len(buf) - 1 - i)
                ob = OrderBlock(
                    direction="bullish",
                    ob_high=bar.high,
                    ob_low=bar.low,
                    ob_50pct=(bar.high + bar.low) / 2,
                    formed_bar_idx=ob_idx,
                )
                self._order_blocks.append(ob)
                self._enforce_limits(bar_count)
                return ob

        return None

    def _scan_bearish_ob(
        self,
        buf: list[MarketEvent],
        bar_count: int,
        atr: Decimal,
        current: MarketEvent,
    ) -> Optional[OrderBlock]:
        """Find bearish OB: last bullish candle before downward displacement."""
        lookback = min(self._ob_lookback, len(buf) - 1)
        scan_start = max(0, len(buf) - 1 - lookback)

        recent_high = max(bar.high for bar in buf[scan_start:])
        displacement = recent_high - current.close

        if displacement < atr * self._atr_mult:
            return None

        # Find last bullish candle (close > open) before the down-move
        for i in range(len(buf) - 2, scan_start - 1, -1):
            bar = buf[i]
            if bar.close > bar.open:  # Bullish candle = the OB
                ob_idx = bar_count - (len(buf) - 1 - i)
                ob = OrderBlock(
                    direction="bearish",
                    ob_high=bar.high,
                    ob_low=bar.low,
                    ob_50pct=(bar.high + bar.low) / 2,
                    formed_bar_idx=ob_idx,
                )
                self._order_blocks.append(ob)
                self._enforce_limits(bar_count)
                return ob

        return None

    def update_ob_states(self, event: MarketEvent, bar_count: int) -> None:
        """Update all OB states based on current bar.

        - Mitigation: price returns to OB zone (wick or close mode).
        - Invalidation: close beyond 50% Mean Threshold.
        - Age expiry: OBs older than max_age bars.
        """
        for ob in self._order_blocks:
            if ob.state != OBState.ACTIVE:
                continue

            # Age expiry
            age = bar_count - ob.formed_bar_idx
            if age > self._ob_max_age:
                ob.state = OBState.INVALIDATED
                continue

            if ob.direction == "bullish":
                self._update_bullish_ob(ob, event)
            else:
                self._update_bearish_ob(ob, event)

    def _update_bullish_ob(self, ob: OrderBlock, event: MarketEvent) -> None:
        """Update a bullish OB (support zone)."""
        # Invalidation: close below 50% of OB zone
        if event.close < ob.ob_50pct:
            ob.state = OBState.INVALIDATED
            return

        # Mitigation: price touches OB zone
        if self._close_mitigation:
            if event.close <= ob.ob_high and event.close >= ob.ob_low:
                ob.state = OBState.MITIGATED
        else:
            if event.low <= ob.ob_high and event.low >= ob.ob_low:
                ob.state = OBState.MITIGATED

    def _update_bearish_ob(self, ob: OrderBlock, event: MarketEvent) -> None:
        """Update a bearish OB (resistance zone)."""
        # Invalidation: close above 50% of OB zone
        if event.close > ob.ob_50pct:
            ob.state = OBState.INVALIDATED
            return

        # Mitigation: price touches OB zone
        if self._close_mitigation:
            if event.close >= ob.ob_low and event.close <= ob.ob_high:
                ob.state = OBState.MITIGATED
        else:
            if event.high >= ob.ob_low and event.high <= ob.ob_high:
                ob.state = OBState.MITIGATED

    def _enforce_limits(self, bar_count: int) -> None:
        """Remove oldest active OBs if exceeding max limit."""
        active = self.active_obs
        while len(active) > self._max_active:
            # Invalidate oldest active
            oldest = min(active, key=lambda ob: ob.formed_bar_idx)
            oldest.state = OBState.INVALIDATED
            active = self.active_obs

        # Prune invalidated/mitigated that are old
        self._order_blocks = [
            ob for ob in self._order_blocks
            if ob.state == OBState.ACTIVE or bar_count - ob.formed_bar_idx <= self._ob_max_age
        ]
