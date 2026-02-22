"""
ict_strategy.py — ICT Enhanced Liquidity strategy.

Combines all SMC components (SwingDetector, MarketStructureTracker, FVGTracker,
OrderBlockDetector) with ICT-specific modules (LiquiditySweepDetector,
InducementDetector, KillZoneFilter, Premium/Discount OTE zones) into a unified
strategy that gates entry on institutional order-flow confluence.

Pipeline per bar (14 steps):
1.  update_buffer(event) + bar_count++
2.  Compute ATR
3.  Warmup guard
4.  Detect confirmed swings (SwingDetector)
5.  Register swings with MarketStructureTracker
6.  Check BOS/CHOCH
7.  Detect new FVG
8.  Detect new OB (on structure break)
9.  Check for liquidity sweeps (LiquiditySweepDetector)
10. Feed bar + detect inducement + check IDM cleared (InducementDetector)
11. Update OB + FVG states
12. Exit check (CHOCH, OB invalidation — same as SMCStrategy)
13. ICT entry filters (kill zone, premium/discount, sweep, IDM)
14. Entry check (OB + FVG confluence gated by ICT filters)

Requirement: ICT-05
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
from src.strategy.smc.liquidity_sweep import LiquiditySweepDetector
from src.strategy.smc.inducement import InducementDetector
from src.strategy.smc.kill_zone import KillZoneFilter, SessionType
from src.strategy.smc.premium_discount import compute_premium_discount, in_ote_zone


class ICTStrategy(BaseStrategy):
    """ICT Enhanced Liquidity strategy combining SMC + ICT components.

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
    sweep_min_depth_atr : float
        Min sweep depth as ATR multiple. Default: 0.1.
    sweep_cooldown_bars : int
        Per-level sweep cooldown. Default: 10.
    idm_secondary_strength : int
        Fractal strength for IDM swing detection. Default: 1.
    require_sweep : bool
        Require liquidity sweep before entry. Default: True.
    require_idm : bool
        Require IDM clearance before entry. Default: False.
    require_kill_zone : bool
        Only enter during kill zone sessions. Default: True.
    require_ote : bool
        Only enter in OTE zone. Default: True.
    active_sessions : list[str]
        Active kill zone sessions. Default: ["LONDON_OPEN", "NY_OPEN", "NY_CLOSE"].
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1h",
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

        # --- SMC Components ---
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

        # --- ICT Components ---
        self._sweep_detector = LiquiditySweepDetector(
            min_depth_atr_mult=p.get("sweep_min_depth_atr", 0.1),
            cooldown_bars=p.get("sweep_cooldown_bars", 10),
        )
        self._idm_detector = InducementDetector(
            secondary_strength=p.get("idm_secondary_strength", 1),
        )

        # Parse active sessions from string list to SessionType enums
        raw_sessions = p.get(
            "active_sessions",
            ["LONDON_OPEN", "NY_OPEN", "NY_CLOSE"],
        )
        active_sessions = [SessionType(s) for s in raw_sessions]
        self._kz_filter = KillZoneFilter(active_sessions=active_sessions)

        # --- ICT Filter Flags ---
        self._require_sweep: bool = p.get("require_sweep", True)
        self._require_idm: bool = p.get("require_idm", False)
        self._require_kill_zone: bool = p.get("require_kill_zone", True)
        self._require_ote: bool = p.get("require_ote", True)

        # --- State ---
        self._bar_count: int = 0
        self._atr_period: int = p.get("atr_period", 14)
        self._warmup_bars: int = p.get("warmup_bars", 30)
        self._in_position: str = ""  # "long", "short", or ""
        self._current_atr: Decimal = Decimal("0")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def trend(self) -> TrendState:
        return self._ms_tracker.trend

    @property
    def bar_count(self) -> int:
        return self._bar_count

    @property
    def current_atr(self) -> Decimal:
        """Current ATR value (for RiskManager integration)."""
        return self._current_atr

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Run the full ICT pipeline for the current bar."""
        # Step 1: Buffer + bar count
        self.update_buffer(event)
        self._bar_count += 1

        # Step 2: Compute ATR
        self._update_atr()

        # Step 3: Warmup guard
        if self._bar_count < self._warmup_bars:
            return None

        # Step 4: Detect confirmed swings
        new_highs, new_lows = self._swing_detector.detect_confirmed_swings(
            self._bar_buffer, self._bar_count,
        )

        # Step 5: Register swings with structure tracker
        for sh in new_highs:
            self._ms_tracker.on_new_swing_high(sh)
        for sl in new_lows:
            self._ms_tracker.on_new_swing_low(sl)

        # Step 6: Check BOS/CHOCH
        structure_break = self._ms_tracker.on_bar_close(
            close=event.close,
            bar_idx=self._bar_count,
            timestamp=event.timestamp,
        )

        # Step 7: Detect new FVG
        if self._current_atr > 0:
            self._fvg_tracker.detect_and_register(
                self._bar_buffer, self._bar_count, self._current_atr,
            )

        # Step 8: Detect new OB (only on structure break)
        if structure_break is not None and self._current_atr > 0:
            self._ob_detector.scan_for_new_ob(
                self._bar_buffer, self._bar_count,
                self._current_atr, structure_break,
            )

        # Step 9: Check for liquidity sweeps
        if self._current_atr > 0:
            self._sweep_detector.check_for_sweeps(
                event,
                self._swing_detector.swing_highs,
                self._swing_detector.swing_lows,
                self._current_atr,
                self._bar_count,
            )

        # Step 10: Feed bar to IDM detector + detect inducement + check clearance
        self._idm_detector.feed_bar(self._bar_buffer, self._bar_count)
        if structure_break is not None:
            self._idm_detector.detect_inducement(
                self._swing_detector.swing_highs,
                self._swing_detector.swing_lows,
                structure_break,
                self._bar_count,
            )
        self._idm_detector.check_idm_cleared(event, self._bar_count)

        # Step 11: Update OB + FVG states
        self._ob_detector.update_ob_states(event, self._bar_count)
        self._fvg_tracker.update_all_states(event, self._bar_count)

        # Step 12: Exit conditions (priority over entry)
        exit_signal = self._check_exit(event, structure_break)
        if exit_signal is not None:
            return exit_signal

        # Steps 13-14: ICT-filtered entry check
        entry_signal = self._check_entry(event)
        if entry_signal is not None:
            return entry_signal

        return None

    # ------------------------------------------------------------------
    # Exit logic (same as SMCStrategy)
    # ------------------------------------------------------------------

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
            if self._in_position == "long":
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

    # ------------------------------------------------------------------
    # Entry logic with ICT filters
    # ------------------------------------------------------------------

    def _check_entry(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Check entry conditions gated by ICT filters."""
        if self._in_position:
            return None

        # Step 13a: Kill Zone filter (applies to both long and short)
        if self._require_kill_zone and not self._kz_filter.is_kill_zone(event.timestamp):
            return None

        trend = self._ms_tracker.trend
        swing_highs = self._swing_detector.swing_highs
        swing_lows = self._swing_detector.swing_lows

        # --- Long Entry ---
        if trend == TrendState.UPTREND:
            signal = self._check_long_entry(event, swing_highs, swing_lows)
            if signal is not None:
                return signal

        # --- Short Entry ---
        if trend == TrendState.DOWNTREND:
            signal = self._check_short_entry(event, swing_highs, swing_lows)
            if signal is not None:
                return signal

        return None

    def _check_long_entry(
        self,
        event: MarketEvent,
        swing_highs: list,
        swing_lows: list,
    ) -> Optional[SignalEvent]:
        """Check long entry with ICT filters + OB/FVG confluence."""
        # Step 13b: Premium/Discount OTE filter
        if self._require_ote and swing_highs and swing_lows:
            pd_zone = compute_premium_discount(
                swing_highs[-1].price,
                swing_lows[-1].price,
            )
            if not in_ote_zone(event.close, pd_zone, "long"):
                return None

        # Step 13c: Sweep filter
        if self._require_sweep and self._sweep_detector.last_bullish_sweep is None:
            return None

        # Step 13d: IDM filter
        if self._require_idm and not self._idm_detector.has_cleared_idm("bullish"):
            return None

        # Step 14: Core SMC confluence (OB zone + FVG overlap)
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
                        ob.ob_low, ob.ob_high, fvg.bottom, fvg.top,
                    ):
                        self._in_position = "long"
                        return SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type=SignalType.LONG,
                            strength=Decimal("0.9"),
                        )

        return None

    def _check_short_entry(
        self,
        event: MarketEvent,
        swing_highs: list,
        swing_lows: list,
    ) -> Optional[SignalEvent]:
        """Check short entry with ICT filters + OB/FVG confluence."""
        # Step 13b: Premium/Discount OTE filter
        if self._require_ote and swing_highs and swing_lows:
            pd_zone = compute_premium_discount(
                swing_highs[-1].price,
                swing_lows[-1].price,
            )
            if not in_ote_zone(event.close, pd_zone, "short"):
                return None

        # Step 13c: Sweep filter
        if self._require_sweep and self._sweep_detector.last_bearish_sweep is None:
            return None

        # Step 13d: IDM filter
        if self._require_idm and not self._idm_detector.has_cleared_idm("bearish"):
            return None

        # Step 14: Core SMC confluence (OB zone + FVG overlap)
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
                        ob.ob_low, ob.ob_high, fvg.bottom, fvg.top,
                    ):
                        self._in_position = "short"
                        return SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type=SignalType.SHORT,
                            strength=Decimal("0.9"),
                        )

        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
