"""
smc_strategy.py — Combined Smart Money Concepts strategy.

Combines SwingDetector, MarketStructureTracker, FVGTracker, and
OrderBlockDetector into a unified strategy that generates signals
based on institutional order flow concepts.

Pipeline per bar:
1. update_buffer(event)
2. Compute ATR
3. Detect confirmed swings (SwingDetector)
4. Check BOS/CHOCH (MarketStructureTracker)
5. Detect new FVG (FVGTracker)
6. Detect new OB (OrderBlockDetector, triggered by BOS)
7. Update OB states
8. Update FVG states
9. Check exit conditions (priority over entry)
10. Check entry conditions

Requirement: SMC-04
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy
from src.strategy.smc.swing_detector import SwingDetector
from src.strategy.smc.structure import (
    MarketStructureTracker,
    TrendState,
    BreakType,
)
from src.strategy.smc.fvg_tracker import FVGTracker, FVGState
from src.strategy.smc.order_block import OrderBlockDetector, OBState


class SMCStrategy(BaseStrategy):
    """Smart Money Concepts strategy combining all SMC components.

    Parameters (via params dict)
    ----------
    swing_strength : int
        Fractal swing detection strength. Default: 2.
    atr_period : int
        ATR calculation period. Default: 14.
    atr_mult_threshold : float
        Displacement ATR multiplier for OB detection. Default: 1.5.
    ob_lookback_bars : int
        OB scan lookback. Default: 10.
    max_active_obs : int
        Max tracked OBs. Default: 5.
    ob_max_age_bars : int
        OB max age. Default: 100.
    max_fvgs : int
        Max tracked FVGs. Default: 20.
    fvg_max_age_bars : int
        FVG max age. Default: 100.
    fvg_min_size_atr : float
        Min FVG size as ATR multiple. Default: 0.5.
    mitigation_mode : str
        FVG mitigation mode. Default: "wick".
    warmup_bars : int
        Bars before signals can be generated. Default: 30.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1d",
        max_buffer_size: int = 500,
        params: Optional[dict] = None,
    ) -> None:
        super().__init__(
            symbol=symbol,
            timeframe=timeframe,
            max_buffer_size=max_buffer_size,
            params=params,
        )
        p = self._params

        # Components
        self._swing_detector = SwingDetector(
            strength=p.get("swing_strength", 2),
        )
        self._ms_tracker = MarketStructureTracker()
        self._fvg_tracker = FVGTracker(
            max_fvgs=p.get("max_fvgs", 20),
            max_age_bars=p.get("fvg_max_age_bars", 100),
            min_size_atr_mult=p.get("fvg_min_size_atr", 0.5),
            mitigation_mode=p.get("mitigation_mode", "wick"),
        )
        self._ob_detector = OrderBlockDetector(
            atr_mult_threshold=p.get("atr_mult_threshold", 1.5),
            ob_lookback_bars=p.get("ob_lookback_bars", 10),
            max_active_obs=p.get("max_active_obs", 5),
            ob_max_age_bars=p.get("ob_max_age_bars", 100),
        )

        # State
        self._bar_count: int = 0
        self._atr_period: int = p.get("atr_period", 14)
        self._warmup_bars: int = p.get("warmup_bars", 30)
        self._in_position: str = ""  # "long", "short", or ""
        self._current_atr: Decimal = Decimal("0")

    @property
    def trend(self) -> TrendState:
        return self._ms_tracker.trend

    @property
    def bar_count(self) -> int:
        return self._bar_count

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Run the full SMC pipeline for the current bar."""
        self.update_buffer(event)
        self._bar_count += 1

        # Compute ATR
        self._update_atr()

        # Warmup guard
        if self._bar_count < self._warmup_bars:
            return None

        # Step 1: Detect confirmed swings
        new_highs, new_lows = self._swing_detector.detect_confirmed_swings(
            self._bar_buffer, self._bar_count,
        )

        # Step 2: Register swings with structure tracker
        for sh in new_highs:
            self._ms_tracker.on_new_swing_high(sh)
        for sl in new_lows:
            self._ms_tracker.on_new_swing_low(sl)

        # Step 3: Check BOS/CHOCH
        structure_break = self._ms_tracker.on_bar_close(
            close=event.close,
            bar_idx=self._bar_count,
            timestamp=event.timestamp,
        )

        # Step 4: Detect new FVG
        if self._current_atr > 0:
            self._fvg_tracker.detect_and_register(
                self._bar_buffer, self._bar_count, self._current_atr,
            )

        # Step 5: Detect new OB (only on structure break)
        if structure_break is not None and self._current_atr > 0:
            self._ob_detector.scan_for_new_ob(
                self._bar_buffer, self._bar_count,
                self._current_atr, structure_break,
            )

        # Step 6: Update OB states
        self._ob_detector.update_ob_states(event, self._bar_count)

        # Step 7: Update FVG states
        self._fvg_tracker.update_all_states(event, self._bar_count)

        # Step 8: Exit conditions (priority over entry)
        exit_signal = self._check_exit(event, structure_break)
        if exit_signal is not None:
            return exit_signal

        # Step 9: Entry conditions
        entry_signal = self._check_entry(event)
        if entry_signal is not None:
            return entry_signal

        return None

    def _check_exit(
        self,
        event: MarketEvent,
        structure_break,
    ) -> Optional[SignalEvent]:
        """Check exit conditions."""
        if not self._in_position:
            return None

        should_exit = False

        # Exit on CHOCH against position direction
        if structure_break is not None and structure_break.break_type == BreakType.CHOCH:
            if self._in_position == "long" and structure_break.direction == "bearish":
                should_exit = True
            elif self._in_position == "short" and structure_break.direction == "bullish":
                should_exit = True

        # Exit on OB invalidation (close beyond 50%)
        if not should_exit:
            active_obs = self._ob_detector.active_obs
            if self._in_position == "long":
                # Check if any bullish OB just got invalidated
                for ob in self._ob_detector.all_obs:
                    if (ob.direction == "bullish"
                            and ob.state == OBState.INVALIDATED
                            and ob.formed_bar_idx >= self._bar_count - 5):
                        should_exit = True
                        break
            elif self._in_position == "short":
                for ob in self._ob_detector.all_obs:
                    if (ob.direction == "bearish"
                            and ob.state == OBState.INVALIDATED
                            and ob.formed_bar_idx >= self._bar_count - 5):
                        should_exit = True
                        break

        if should_exit:
            self._in_position = ""
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal("0.8"),
            )

        return None

    def _check_entry(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Check entry conditions."""
        if self._in_position:
            return None

        trend = self._ms_tracker.trend

        # --- Long Entry ---
        if trend == TrendState.UPTREND:
            bullish_obs = [
                ob for ob in self._ob_detector.active_obs
                if ob.direction == "bullish"
            ]
            for ob in bullish_obs:
                # Price in OB zone
                if event.low <= ob.ob_high and event.close >= ob.ob_low:
                    # Overlapping bullish FVG (OPEN or TOUCHED)
                    active_fvgs = self._fvg_tracker.get_active_fvgs("bullish")
                    for fvg in active_fvgs:
                        if self._zones_overlap(
                            ob.ob_low, ob.ob_high, fvg.bottom, fvg.top
                        ):
                            self._in_position = "long"
                            return SignalEvent(
                                symbol=event.symbol,
                                timestamp=event.timestamp,
                                signal_type=SignalType.LONG,
                                strength=Decimal("0.9"),
                            )

        # --- Short Entry ---
        if trend == TrendState.DOWNTREND:
            bearish_obs = [
                ob for ob in self._ob_detector.active_obs
                if ob.direction == "bearish"
            ]
            for ob in bearish_obs:
                # Price in OB zone
                if event.high >= ob.ob_low and event.close <= ob.ob_high:
                    # Overlapping bearish FVG (OPEN or TOUCHED)
                    active_fvgs = self._fvg_tracker.get_active_fvgs("bearish")
                    for fvg in active_fvgs:
                        if self._zones_overlap(
                            ob.ob_low, ob.ob_high, fvg.bottom, fvg.top
                        ):
                            self._in_position = "short"
                            return SignalEvent(
                                symbol=event.symbol,
                                timestamp=event.timestamp,
                                signal_type=SignalType.SHORT,
                                strength=Decimal("0.9"),
                            )

        return None

    @staticmethod
    def _zones_overlap(
        a_low: Decimal, a_high: Decimal,
        b_low: Decimal, b_high: Decimal,
    ) -> bool:
        """Check if two price zones overlap."""
        return a_low <= b_high and b_low <= a_high

    def _update_atr(self) -> None:
        """Compute simple ATR from the bar buffer."""
        if len(self._bar_buffer) < 2:
            return

        period = min(self._atr_period, len(self._bar_buffer) - 1)
        if period < 1:
            return

        tr_sum = Decimal("0")
        for i in range(-period, 0):
            bar = self._bar_buffer[i]
            prev_close = self._bar_buffer[i - 1].close
            tr = max(
                bar.high - bar.low,
                abs(bar.high - prev_close),
                abs(bar.low - prev_close),
            )
            tr_sum += tr

        self._current_atr = tr_sum / Decimal(str(period))
