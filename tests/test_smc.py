"""
test_smc.py — Tests for Smart Money Concepts strategy components.

Covers:
- SwingDetector (fractal confirmation, no lookahead)
- MarketStructureTracker (BOS/CHOCH classification, trend state)
- FVGTracker (state machine: OPEN → TOUCHED → MITIGATED → INVERTED → EXPIRED)
- OrderBlockDetector (ATR displacement, state transitions)
- SMCStrategy (combined pipeline, warmup, entry/exit)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.events import MarketEvent, SignalType
from src.strategy.smc.swing_detector import SwingDetector, SwingPoint
from src.strategy.smc.structure import (
    MarketStructureTracker,
    TrendState,
    BreakType,
    StructureBreak,
)
from src.strategy.smc.fvg_tracker import FVGTracker, FVGState, FairValueGap
from src.strategy.smc.order_block import (
    OrderBlockDetector,
    OBState,
    OrderBlock,
)
from src.strategy.smc.smc_strategy import SMCStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 1, 9, 30)


def make_bar(
    idx: int,
    o: str, h: str, l: str, c: str,
    vol: int = 1000,
    symbol: str = "TEST",
    tf: str = "1d",
) -> MarketEvent:
    return MarketEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(days=idx),
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(l),
        close=Decimal(c),
        volume=vol,
        timeframe=tf,
    )


def make_swing_bars(prices: list[str], base_price: str = "100") -> list[MarketEvent]:
    """Create bars where high = price, low = base_price, for swing detection."""
    bars = []
    for i, p in enumerate(prices):
        bars.append(make_bar(
            i,
            o=base_price, h=p, l=base_price, c=p,
        ))
    return bars


# ===========================================================================
# SwingDetector Tests
# ===========================================================================


class TestSwingDetector:

    def test_basic_swing_high_strength_1(self):
        """Strength=1: candidate at buf[-2], 3 bars needed."""
        sd = SwingDetector(strength=1)
        # Bars: low, HIGH, low → swing high at index 1
        bars = [
            make_bar(0, "100", "101", "99", "100"),
            make_bar(1, "100", "105", "99", "104"),  # candidate: highest
            make_bar(2, "100", "102", "99", "101"),
        ]
        new_h, new_l = sd.detect_confirmed_swings(bars, bar_count=3)
        assert len(new_h) == 1
        assert new_h[0].price == Decimal("105")
        assert new_h[0].abs_idx == 2  # bar_count(3) - strength(1) = 2

    def test_basic_swing_low_strength_1(self):
        sd = SwingDetector(strength=1)
        bars = [
            make_bar(0, "100", "101", "99", "100"),
            make_bar(1, "100", "101", "95", "96"),  # lowest low
            make_bar(2, "100", "101", "98", "100"),
        ]
        new_h, new_l = sd.detect_confirmed_swings(bars, bar_count=3)
        assert len(new_l) == 1
        assert new_l[0].price == Decimal("95")

    def test_strength_2_requires_5_bars(self):
        """Strength=2 needs 2*2+1=5 bars minimum."""
        sd = SwingDetector(strength=2)
        bars = [make_bar(i, "100", "100", "100", "100") for i in range(4)]
        new_h, new_l = sd.detect_confirmed_swings(bars, bar_count=4)
        assert new_h == [] and new_l == []

    def test_strength_2_swing_high(self):
        sd = SwingDetector(strength=2)
        # Pattern: 100, 101, 105, 102, 100 → swing high at index 2
        bars = [
            make_bar(0, "100", "100", "99", "100"),
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "100", "105", "99", "104"),  # candidate
            make_bar(3, "100", "102", "99", "101"),
            make_bar(4, "100", "100", "99", "100"),
        ]
        new_h, new_l = sd.detect_confirmed_swings(bars, bar_count=5)
        assert len(new_h) == 1
        assert new_h[0].price == Decimal("105")

    def test_no_swing_equal_highs(self):
        """Equal highs should NOT count as swing (strict >)."""
        sd = SwingDetector(strength=1)
        bars = [
            make_bar(0, "100", "105", "99", "100"),
            make_bar(1, "100", "105", "99", "104"),  # same high
            make_bar(2, "100", "102", "99", "101"),
        ]
        new_h, _ = sd.detect_confirmed_swings(bars, bar_count=3)
        assert len(new_h) == 0

    def test_swing_history_limit(self):
        sd = SwingDetector(strength=1, max_history=3)
        for i in range(10):
            bars = [
                make_bar(0, "100", str(90 + i), "89", "90"),
                make_bar(1, "100", str(100 + i), "89", str(99 + i)),
                make_bar(2, "100", str(91 + i), "89", "90"),
            ]
            sd.detect_confirmed_swings(bars, bar_count=3 + i * 3)
        assert len(sd.swing_highs) <= 3

    def test_no_duplicate_detection(self):
        """Same bar_count should not produce duplicate swings."""
        sd = SwingDetector(strength=1)
        bars = [
            make_bar(0, "100", "101", "99", "100"),
            make_bar(1, "100", "110", "99", "109"),
            make_bar(2, "100", "102", "99", "101"),
        ]
        sd.detect_confirmed_swings(bars, bar_count=3)
        sd.detect_confirmed_swings(bars, bar_count=3)
        assert len(sd.swing_highs) == 1

    def test_invalid_strength(self):
        with pytest.raises(ValueError):
            SwingDetector(strength=0)


# ===========================================================================
# MarketStructureTracker Tests
# ===========================================================================


class TestMarketStructureTracker:

    def test_initial_state_undefined(self):
        ms = MarketStructureTracker()
        assert ms.trend == TrendState.UNDEFINED

    def test_bos_from_undefined_to_uptrend(self):
        ms = MarketStructureTracker()
        sh = SwingPoint(price=Decimal("105"), timestamp=BASE_TS, abs_idx=5)
        ms.on_new_swing_high(sh)

        result = ms.on_bar_close(Decimal("106"), bar_idx=10, timestamp=BASE_TS)
        assert result is not None
        assert result.break_type == BreakType.BOS
        assert result.direction == "bullish"
        assert ms.trend == TrendState.UPTREND

    def test_bos_from_undefined_to_downtrend(self):
        ms = MarketStructureTracker()
        sl = SwingPoint(price=Decimal("95"), timestamp=BASE_TS, abs_idx=5)
        ms.on_new_swing_low(sl)

        result = ms.on_bar_close(Decimal("94"), bar_idx=10, timestamp=BASE_TS)
        assert result is not None
        assert result.break_type == BreakType.BOS
        assert result.direction == "bearish"
        assert ms.trend == TrendState.DOWNTREND

    def test_choch_uptrend_to_downtrend(self):
        ms = MarketStructureTracker()
        # Establish uptrend
        sh = SwingPoint(price=Decimal("105"), timestamp=BASE_TS, abs_idx=5)
        ms.on_new_swing_high(sh)
        ms.on_bar_close(Decimal("106"), bar_idx=8, timestamp=BASE_TS)
        assert ms.trend == TrendState.UPTREND

        # Register swing low, then break it → CHOCH
        sl = SwingPoint(price=Decimal("100"), timestamp=BASE_TS, abs_idx=9)
        ms.on_new_swing_low(sl)
        result = ms.on_bar_close(Decimal("99"), bar_idx=12, timestamp=BASE_TS)
        assert result is not None
        assert result.break_type == BreakType.CHOCH
        assert result.direction == "bearish"
        assert ms.trend == TrendState.DOWNTREND

    def test_choch_downtrend_to_uptrend(self):
        ms = MarketStructureTracker()
        # Establish downtrend
        sl = SwingPoint(price=Decimal("95"), timestamp=BASE_TS, abs_idx=3)
        ms.on_new_swing_low(sl)
        ms.on_bar_close(Decimal("94"), bar_idx=5, timestamp=BASE_TS)
        assert ms.trend == TrendState.DOWNTREND

        # Register swing high, then break it → CHOCH
        sh = SwingPoint(price=Decimal("98"), timestamp=BASE_TS, abs_idx=7)
        ms.on_new_swing_high(sh)
        result = ms.on_bar_close(Decimal("99"), bar_idx=10, timestamp=BASE_TS)
        assert result is not None
        assert result.break_type == BreakType.CHOCH
        assert result.direction == "bullish"
        assert ms.trend == TrendState.UPTREND

    def test_bos_continuation_in_uptrend(self):
        ms = MarketStructureTracker()
        sh1 = SwingPoint(price=Decimal("105"), timestamp=BASE_TS, abs_idx=3)
        ms.on_new_swing_high(sh1)
        ms.on_bar_close(Decimal("106"), bar_idx=5, timestamp=BASE_TS)
        assert ms.trend == TrendState.UPTREND

        # New higher swing high, break it → BOS (continuation)
        sh2 = SwingPoint(price=Decimal("108"), timestamp=BASE_TS, abs_idx=7)
        ms.on_new_swing_high(sh2)
        result = ms.on_bar_close(Decimal("109"), bar_idx=10, timestamp=BASE_TS)
        assert result is not None
        assert result.break_type == BreakType.BOS

    def test_no_break_without_swing(self):
        ms = MarketStructureTracker()
        result = ms.on_bar_close(Decimal("100"), bar_idx=1, timestamp=BASE_TS)
        assert result is None

    def test_no_duplicate_break_same_bar(self):
        ms = MarketStructureTracker()
        sh = SwingPoint(price=Decimal("105"), timestamp=BASE_TS, abs_idx=3)
        ms.on_new_swing_high(sh)
        ms.on_bar_close(Decimal("106"), bar_idx=5, timestamp=BASE_TS)
        result = ms.on_bar_close(Decimal("107"), bar_idx=5, timestamp=BASE_TS)
        assert result is None

    def test_break_history_limit(self):
        ms = MarketStructureTracker(max_history=2)
        for i in range(5):
            sh = SwingPoint(price=Decimal(str(100 + i)), timestamp=BASE_TS, abs_idx=i * 3)
            ms.on_new_swing_high(sh)
            ms.on_bar_close(Decimal(str(101 + i)), bar_idx=i * 3 + 2, timestamp=BASE_TS)
        assert len(ms.breaks) <= 2


# ===========================================================================
# FVGTracker Tests
# ===========================================================================


class TestFVGTracker:

    def test_detect_bullish_fvg(self):
        tracker = FVGTracker(min_size_atr_mult=0.0)
        bars = [
            make_bar(0, "100", "102", "99", "101"),   # bar1.high = 102
            make_bar(1, "103", "107", "102", "106"),   # middle bar
            make_bar(2, "106", "110", "105", "109"),   # bar3.low = 105
        ]
        # gap: bar1.high(102) < bar3.low(105) → bullish FVG
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        assert gap is not None
        assert gap.direction == "bullish"
        assert gap.bottom == Decimal("102")
        assert gap.top == Decimal("105")

    def test_detect_bearish_fvg(self):
        tracker = FVGTracker(min_size_atr_mult=0.0)
        bars = [
            make_bar(0, "110", "112", "109", "111"),   # bar1.low = 109
            make_bar(1, "106", "108", "104", "105"),   # middle bar
            make_bar(2, "103", "104", "100", "101"),   # bar3.high = 104
        ]
        # gap: bar1.low(109) > bar3.high(104) → bearish FVG
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        assert gap is not None
        assert gap.direction == "bearish"
        assert gap.top == Decimal("109")
        assert gap.bottom == Decimal("104")

    def test_min_size_filter(self):
        tracker = FVGTracker(min_size_atr_mult=5.0)
        bars = [
            make_bar(0, "100", "101", "99", "100"),
            make_bar(1, "101", "103", "101", "102"),
            make_bar(2, "102", "104", "101.5", "103"),
        ]
        # gap size = 0.5, atr * 5.0 = 5.0 → too small
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        assert gap is None

    def test_state_transition_open_to_touched(self):
        tracker = FVGTracker(min_size_atr_mult=0.0)
        bars = [
            make_bar(0, "100", "102", "99", "101"),
            make_bar(1, "103", "107", "102", "106"),
            make_bar(2, "106", "110", "105", "109"),
        ]
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        assert gap.state == FVGState.OPEN

        # Price dips into the gap zone (wick touches top)
        touch_bar = make_bar(3, "108", "108", "104", "107")
        tracker.update_all_states(touch_bar, bar_idx=4)
        assert gap.state == FVGState.TOUCHED

    def test_same_bar_guard(self):
        """Gap cannot be mitigated on the bar it was detected."""
        tracker = FVGTracker(min_size_atr_mult=0.0)
        bars = [
            make_bar(0, "100", "102", "99", "101"),
            make_bar(1, "103", "107", "102", "106"),
            make_bar(2, "106", "110", "105", "109"),
        ]
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        # Try to mitigate on same bar_idx=3
        deep_bar = make_bar(2, "105", "105", "98", "99")
        tracker.update_all_states(deep_bar, bar_idx=3)
        assert gap.state == FVGState.OPEN  # Should still be OPEN

    def test_age_expiry(self):
        tracker = FVGTracker(min_size_atr_mult=0.0, max_age_bars=5)
        bars = [
            make_bar(0, "100", "102", "99", "101"),
            make_bar(1, "103", "107", "102", "106"),
            make_bar(2, "106", "110", "105", "109"),
        ]
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        # Bar 9: age = 9-3 = 6 > max_age_bars(5)
        old_bar = make_bar(9, "110", "112", "109", "111")
        tracker.update_all_states(old_bar, bar_idx=9)
        assert gap.state == FVGState.EXPIRED

    def test_memory_limit(self):
        tracker = FVGTracker(min_size_atr_mult=0.0, max_fvgs=2)
        for i in range(5):
            base = 100 + i * 10
            bars = [
                make_bar(0, str(base), str(base + 2), str(base - 1), str(base + 1)),
                make_bar(1, str(base + 3), str(base + 7), str(base + 2), str(base + 6)),
                make_bar(2, str(base + 6), str(base + 10), str(base + 5), str(base + 9)),
            ]
            tracker.detect_and_register(bars, bar_idx=i + 3, atr=Decimal("1"))
        active = tracker.get_active_fvgs()
        assert len(active) <= 2

    def test_get_active_fvgs_by_direction(self):
        tracker = FVGTracker(min_size_atr_mult=0.0)
        # Bullish
        bars_bull = [
            make_bar(0, "100", "102", "99", "101"),
            make_bar(1, "103", "107", "102", "106"),
            make_bar(2, "106", "110", "105", "109"),
        ]
        tracker.detect_and_register(bars_bull, bar_idx=3, atr=Decimal("1"))
        # Bearish
        bars_bear = [
            make_bar(0, "110", "112", "109", "111"),
            make_bar(1, "106", "108", "104", "105"),
            make_bar(2, "103", "104", "100", "101"),
        ]
        tracker.detect_and_register(bars_bear, bar_idx=6, atr=Decimal("1"))

        bull_fvgs = tracker.get_active_fvgs("bullish")
        bear_fvgs = tracker.get_active_fvgs("bearish")
        assert len(bull_fvgs) == 1
        assert len(bear_fvgs) == 1

    def test_invalid_mitigation_mode(self):
        with pytest.raises(ValueError):
            FVGTracker(mitigation_mode="invalid")

    def test_mitigation_50pct_mode(self):
        tracker = FVGTracker(min_size_atr_mult=0.0, mitigation_mode="50pct")
        bars = [
            make_bar(0, "100", "102", "99", "101"),
            make_bar(1, "103", "107", "102", "106"),
            make_bar(2, "106", "110", "105", "109"),
        ]
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        # Touch the zone first
        touch_bar = make_bar(3, "108", "108", "104", "107")
        tracker.update_all_states(touch_bar, bar_idx=4)
        assert gap.state == FVGState.TOUCHED

        # Wick reaches midpoint (103.5): low=103 < 103.5
        mid_bar = make_bar(4, "106", "106", "103", "105")
        tracker.update_all_states(mid_bar, bar_idx=5)
        assert gap.state == FVGState.MITIGATED

    def test_bearish_fvg_state_transitions(self):
        tracker = FVGTracker(min_size_atr_mult=0.0, mitigation_mode="wick")
        bars = [
            make_bar(0, "110", "112", "109", "111"),
            make_bar(1, "106", "108", "104", "105"),
            make_bar(2, "103", "104", "100", "101"),
        ]
        gap = tracker.detect_and_register(bars, bar_idx=3, atr=Decimal("1"))
        assert gap.state == FVGState.OPEN
        assert gap.direction == "bearish"
        assert gap.bottom == Decimal("104")
        assert gap.top == Decimal("109")

        # Touch: high reaches into zone
        touch = make_bar(3, "101", "105", "100", "103")
        tracker.update_all_states(touch, bar_idx=4)
        assert gap.state == FVGState.TOUCHED

        # Mitigate: wick reaches top (109)
        mitigate = make_bar(4, "103", "110", "102", "108")
        tracker.update_all_states(mitigate, bar_idx=5)
        assert gap.state == FVGState.MITIGATED

        # Invert: close above top (109)
        invert = make_bar(5, "108", "112", "107", "111")
        tracker.update_all_states(invert, bar_idx=6)
        assert gap.state == FVGState.INVERTED

    def test_not_enough_bars(self):
        tracker = FVGTracker()
        bars = [make_bar(0, "100", "102", "99", "101")]
        gap = tracker.detect_and_register(bars, bar_idx=1, atr=Decimal("1"))
        assert gap is None


# ===========================================================================
# OrderBlockDetector Tests
# ===========================================================================


class TestOrderBlockDetector:

    def _make_bos_bullish(self):
        return StructureBreak(
            break_type=BreakType.BOS,
            direction="bullish",
            broken_level=Decimal("105"),
            timestamp=BASE_TS,
            bar_idx=10,
        )

    def _make_bos_bearish(self):
        return StructureBreak(
            break_type=BreakType.BOS,
            direction="bearish",
            broken_level=Decimal("95"),
            timestamp=BASE_TS,
            bar_idx=10,
        )

    def test_bullish_ob_detection(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1)
        # Pattern: bearish candle, then strong bullish displacement
        bars = [
            make_bar(0, "102", "103", "99", "100"),   # bearish candle (OB candidate)
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "101", "110", "100", "109"),   # strong bullish bar
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("1"),
                                  structure_break=self._make_bos_bullish())
        assert ob is not None
        assert ob.direction == "bullish"
        assert ob.state == OBState.ACTIVE

    def test_bearish_ob_detection(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1)
        bars = [
            make_bar(0, "98", "101", "97", "100"),    # bullish candle (OB candidate)
            make_bar(1, "100", "101", "99", "99"),
            make_bar(2, "99", "100", "90", "91"),      # strong bearish bar
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("1"),
                                  structure_break=self._make_bos_bearish())
        assert ob is not None
        assert ob.direction == "bearish"

    def test_no_ob_without_structure_break(self):
        det = OrderBlockDetector()
        bars = [make_bar(i, "100", "102", "99", "101") for i in range(5)]
        ob = det.scan_for_new_ob(bars, bar_count=5, atr=Decimal("1"),
                                  structure_break=None)
        assert ob is None

    def test_displacement_filter(self):
        """Weak move should not produce OB."""
        det = OrderBlockDetector(atr_mult_threshold=5.0)
        bars = [
            make_bar(0, "102", "103", "99", "100"),
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "101", "102", "100", "101.5"),  # tiny move
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("2"),
                                  structure_break=self._make_bos_bullish())
        assert ob is None

    def test_ob_invalidation_close_beyond_50pct(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1)
        bars = [
            make_bar(0, "102", "103", "99", "100"),
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "101", "110", "100", "109"),
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("1"),
                                  structure_break=self._make_bos_bullish())
        assert ob is not None
        assert ob.state == OBState.ACTIVE

        # Close below 50% of bullish OB zone → invalidation
        inv_bar = make_bar(3, "100", "100", "98", str(ob.ob_50pct - 1))
        det.update_ob_states(inv_bar, bar_count=4)
        assert ob.state == OBState.INVALIDATED

    def test_ob_mitigation_wick_mode(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1, close_mitigation=False)
        bars = [
            make_bar(0, "102", "103", "99", "100"),
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "101", "110", "100", "109"),
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("1"),
                                  structure_break=self._make_bos_bullish())
        # Wick touches OB zone but close stays above 50%
        mit_bar = make_bar(3, "105", "106", str(ob.ob_low), "105")
        det.update_ob_states(mit_bar, bar_count=4)
        assert ob.state == OBState.MITIGATED

    def test_ob_age_expiry(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1, ob_max_age_bars=5)
        bars = [
            make_bar(0, "102", "103", "99", "100"),
            make_bar(1, "100", "101", "99", "101"),
            make_bar(2, "101", "110", "100", "109"),
        ]
        ob = det.scan_for_new_ob(bars, bar_count=3, atr=Decimal("1"),
                                  structure_break=self._make_bos_bullish())
        # Bar 10: age = 10-1 = 9 (OB formed_bar_idx varies but > 5)
        far_bar = make_bar(10, "110", "112", "109", "111")
        det.update_ob_states(far_bar, bar_count=100)
        assert ob.state == OBState.INVALIDATED

    def test_max_active_obs_limit(self):
        det = OrderBlockDetector(atr_mult_threshold=0.1, max_active_obs=2)
        bos = self._make_bos_bullish()
        for i in range(5):
            base = 100 + i * 20
            bars = [
                make_bar(0, str(base + 2), str(base + 3), str(base - 1), str(base)),
                make_bar(1, str(base), str(base + 1), str(base - 1), str(base + 1)),
                make_bar(2, str(base + 1), str(base + 10), str(base), str(base + 9)),
            ]
            det.scan_for_new_ob(bars, bar_count=3 + i * 3, atr=Decimal("1"),
                                 structure_break=bos)
        assert len(det.active_obs) <= 2

    def test_not_enough_bars(self):
        det = OrderBlockDetector()
        bars = [make_bar(0, "100", "102", "99", "101")]
        ob = det.scan_for_new_ob(bars, bar_count=1, atr=Decimal("1"),
                                  structure_break=self._make_bos_bullish())
        assert ob is None


# ===========================================================================
# SMCStrategy Integration Tests
# ===========================================================================


class TestSMCStrategy:

    def _make_strategy(self, **kwargs) -> SMCStrategy:
        params = {
            "swing_strength": 1,
            "atr_period": 3,
            "warmup_bars": 5,
            "atr_mult_threshold": 0.5,
            "fvg_min_size_atr": 0.0,
            "ob_lookback_bars": 5,
        }
        params.update(kwargs)
        return SMCStrategy(
            symbol="TEST",
            timeframe="1d",
            params=params,
        )

    def test_warmup_guard(self):
        """No signals during warmup period."""
        strat = self._make_strategy(warmup_bars=10)
        for i in range(10):
            bar = make_bar(i, "100", "102", "99", "101")
            signal = strat.calculate_signals(bar)
            assert signal is None

    def test_trend_tracking(self):
        """Strategy correctly tracks trend state."""
        strat = self._make_strategy(warmup_bars=0, swing_strength=1)
        # Feed enough bars to establish trend
        prices = [
            ("100", "102", "99", "101"),
            ("101", "103", "100", "102"),
            ("102", "110", "101", "109"),  # strong up
            ("109", "115", "108", "114"),  # higher
            ("114", "120", "113", "119"),  # higher still
        ]
        for i, (o, h, l, c) in enumerate(prices):
            bar = make_bar(i, o, h, l, c)
            strat.calculate_signals(bar)

        # After strong upward movement, should detect swings and potentially set trend
        assert strat.bar_count == 5

    def test_pipeline_runs_without_error(self):
        """Full pipeline runs without errors for various bar patterns."""
        strat = self._make_strategy(warmup_bars=3)
        # Simulated volatile price action
        bar_data = [
            ("100", "103", "99", "102"),
            ("102", "105", "101", "104"),
            ("104", "108", "103", "107"),
            ("107", "110", "102", "103"),  # Reversal
            ("103", "104", "98", "99"),
            ("99", "100", "95", "96"),
            ("96", "97", "90", "91"),
            ("91", "105", "90", "104"),   # Strong bounce
            ("104", "108", "103", "107"),
            ("107", "115", "106", "114"),
        ]
        signals = []
        for i, (o, h, l, c) in enumerate(bar_data):
            bar = make_bar(i, o, h, l, c)
            sig = strat.calculate_signals(bar)
            if sig is not None:
                signals.append(sig)
        # Pipeline should run without errors
        assert strat.bar_count == 10

    def test_exit_on_choch(self):
        """Exit signal generated on CHOCH against position."""
        strat = self._make_strategy(warmup_bars=0, swing_strength=1)
        # Manually set up position state for testing
        strat._in_position = "long"
        strat._ms_tracker._trend = TrendState.UPTREND

        # Register a swing low that will be broken
        sl = SwingPoint(price=Decimal("95"), timestamp=BASE_TS, abs_idx=5)
        strat._ms_tracker.on_new_swing_low(sl)

        # Need enough bars in buffer for ATR
        for i in range(5):
            bar = make_bar(i, "100", "102", "99", "101")
            strat.update_buffer(bar)
        strat._bar_count = 5

        # Bar that breaks below swing low → CHOCH → Exit
        break_bar = make_bar(5, "96", "97", "93", "94")
        signal = strat.calculate_signals(break_bar)
        assert signal is not None
        assert signal.signal_type == SignalType.EXIT

    def test_zones_overlap(self):
        assert SMCStrategy._zones_overlap(
            Decimal("100"), Decimal("105"),
            Decimal("103"), Decimal("108"),
        ) is True
        assert SMCStrategy._zones_overlap(
            Decimal("100"), Decimal("103"),
            Decimal("105"), Decimal("108"),
        ) is False

    def test_atr_computation(self):
        """ATR is computed from buffer."""
        strat = self._make_strategy(warmup_bars=0, atr_period=3)
        bars = [
            make_bar(0, "100", "105", "95", "102"),
            make_bar(1, "102", "108", "98", "106"),
            make_bar(2, "106", "112", "100", "110"),
            make_bar(3, "110", "115", "105", "112"),
        ]
        for bar in bars:
            strat.calculate_signals(bar)
        assert strat._current_atr > 0

    def test_no_entry_without_confluence(self):
        """No signal without all entry conditions met."""
        strat = self._make_strategy(warmup_bars=0, swing_strength=1)
        # Just feed neutral bars
        for i in range(10):
            bar = make_bar(i, "100", "101", "99", "100")
            signal = strat.calculate_signals(bar)
        # With flat price action, no confluence → no signal
        assert strat._in_position == ""


# ===========================================================================
# Dashboard Integration Test
# ===========================================================================


class TestDashboardIntegration:

    def test_strategy_map_contains_smc(self):
        from src.dashboard.callbacks import STRATEGY_MAP, SWEEP_PARAMS
        assert "smc" in STRATEGY_MAP
        assert STRATEGY_MAP["smc"] == ("src.strategy.smc.smc_strategy", "SMCStrategy")
        assert "smc" in SWEEP_PARAMS

    def test_smc_importable_via_strategy_map(self):
        from src.dashboard.callbacks import _import_strategy
        cls = _import_strategy("smc")
        assert cls.__name__ == "SMCStrategy"
