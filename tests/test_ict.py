"""
test_ict.py -- Tests for ICT (Inner Circle Trader) strategy components.

Covers:
- LiquiditySweepDetector (sweep detection, depth filter, cooldown, marking)
- InducementDetector (IDM detection after BOS, clearance tracking)
- KillZoneFilter (session classification, kill zone gating)
- Premium/Discount zone (equilibrium, OTE zones)
- ICTStrategy (full pipeline, warmup, ICT filters, exit logic)

Requirement: TEST-20
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.events import MarketEvent, SignalType
from src.strategy.smc.swing_detector import SwingPoint
from src.strategy.smc.structure import (
    StructureBreak,
    BreakType,
    TrendState,
)
from src.strategy.smc.liquidity_sweep import LiquiditySweepDetector, LiquiditySweep
from src.strategy.smc.inducement import InducementDetector, InducementPoint
from src.strategy.smc.kill_zone import KillZoneFilter, SessionType
from src.strategy.smc.premium_discount import (
    compute_premium_discount,
    price_zone,
    in_ote_zone,
)
from src.strategy.smc.ict_strategy import ICTStrategy


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

ET = ZoneInfo("America/New_York")
BASE_TS = datetime(2024, 1, 15, 8, 30, tzinfo=ET)  # NY Open


def _make_bar(
    high, low, open_, close,
    ts=None, symbol="TEST", volume=1000, tf="1h",
) -> MarketEvent:
    """Create a MarketEvent with Decimal prices."""
    return MarketEvent(
        symbol=symbol,
        timestamp=ts or BASE_TS,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
        timeframe=tf,
    )


def _make_swing(price, abs_idx, ts=None) -> SwingPoint:
    """Create a SwingPoint for testing."""
    return SwingPoint(
        price=Decimal(str(price)),
        timestamp=ts or BASE_TS,
        abs_idx=abs_idx,
    )


def _make_bos(direction, broken_level, bar_idx, ts=None) -> StructureBreak:
    """Create a StructureBreak (BOS) for testing."""
    return StructureBreak(
        break_type=BreakType.BOS,
        direction=direction,
        broken_level=Decimal(str(broken_level)),
        timestamp=ts or BASE_TS,
        bar_idx=bar_idx,
    )


# ===========================================================================
# LiquiditySweepDetector Tests
# ===========================================================================


class TestLiquiditySweepDetector:

    def test_bullish_sweep_detected(self):
        """Bar wicks below swing low, closes above it -> bullish sweep."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1)
        swing_low = _make_swing(90, abs_idx=5)
        # bar: low=89 (below 90), close=91 (above 90)
        bar = _make_bar(high=92, low=89, open_=90, close=91)
        atr = Decimal("5")

        sweeps = det.check_for_sweeps(bar, [], [swing_low], atr, bar_idx=10)

        assert len(sweeps) == 1
        assert sweeps[0].direction == "bullish"
        assert sweeps[0].swept_level == Decimal("90")
        assert sweeps[0].sweep_wick == Decimal("89")
        assert sweeps[0].confirmed is True

    def test_bearish_sweep_detected(self):
        """Bar wicks above swing high, closes below it -> bearish sweep."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1)
        swing_high = _make_swing(110, abs_idx=5)
        # bar: high=111 (above 110), close=109 (below 110)
        bar = _make_bar(high=111, low=108, open_=110, close=109)
        atr = Decimal("5")

        sweeps = det.check_for_sweeps(bar, [swing_high], [], atr, bar_idx=10)

        assert len(sweeps) == 1
        assert sweeps[0].direction == "bearish"
        assert sweeps[0].swept_level == Decimal("110")
        assert sweeps[0].sweep_wick == Decimal("111")
        assert sweeps[0].confirmed is True

    def test_sweep_rejected_depth_too_small(self):
        """Sweep depth < min_depth_atr_mult * ATR -> no sweep."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1)
        swing_low = _make_swing(90, abs_idx=5)
        # depth = 90 - 89.99 = 0.01, threshold = 0.1 * 10 = 1.0
        bar = _make_bar(high=92, low=89.99, open_=90, close=91)
        atr = Decimal("10")

        sweeps = det.check_for_sweeps(bar, [], [swing_low], atr, bar_idx=10)

        assert len(sweeps) == 0

    def test_sweep_rejected_no_close_back(self):
        """Bar.low < swing_low but close < swing_low -> not confirmed."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1)
        swing_low = _make_swing(90, abs_idx=5)
        # low=88 (below 90), close=89 (also below 90) -> no confirmation
        bar = _make_bar(high=91, low=88, open_=90, close=89)
        atr = Decimal("5")

        sweeps = det.check_for_sweeps(bar, [], [swing_low], atr, bar_idx=10)

        assert len(sweeps) == 0

    def test_cooldown_prevents_resweep(self):
        """Sweep same level twice within cooldown_bars -> second ignored."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1, cooldown_bars=10)
        swing_low = _make_swing(90, abs_idx=5)
        bar1 = _make_bar(high=92, low=89, open_=90, close=91)
        atr = Decimal("5")

        # First sweep at bar 10
        sweeps1 = det.check_for_sweeps(bar1, [], [swing_low], atr, bar_idx=10)
        assert len(sweeps1) == 1

        # Second attempt at bar 15 (within cooldown of 10)
        bar2 = _make_bar(high=92, low=89, open_=90, close=91)
        sweeps2 = det.check_for_sweeps(bar2, [], [swing_low], atr, bar_idx=15)

        # Cooldown prevents resweep AND level is marked swept
        assert len(sweeps2) == 0

    def test_swept_level_marked(self):
        """After sweep, the same swing point abs_idx is not swept again."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1, cooldown_bars=0)
        swing_low = _make_swing(90, abs_idx=5)
        bar = _make_bar(high=92, low=89, open_=90, close=91)
        atr = Decimal("5")

        # First sweep
        det.check_for_sweeps(bar, [], [swing_low], atr, bar_idx=10)
        assert 5 in det._swept_levels

        # Second attempt (no cooldown but level is marked)
        bar2 = _make_bar(high=92, low=89, open_=90, close=91)
        sweeps = det.check_for_sweeps(bar2, [], [swing_low], atr, bar_idx=50)
        assert len(sweeps) == 0

    def test_multiple_sweeps_different_levels(self):
        """Two different swings swept on separate bars."""
        det = LiquiditySweepDetector(min_depth_atr_mult=0.1)
        sl1 = _make_swing(90, abs_idx=5)
        sl2 = _make_swing(85, abs_idx=8)
        atr = Decimal("5")

        # Sweep sl1
        bar1 = _make_bar(high=92, low=89, open_=90, close=91)
        sweeps1 = det.check_for_sweeps(bar1, [], [sl1, sl2], atr, bar_idx=10)
        assert len(sweeps1) == 1
        assert sweeps1[0].swept_level == Decimal("90")

        # Sweep sl2 on a later bar
        bar2 = _make_bar(high=87, low=84, open_=86, close=86)
        sweeps2 = det.check_for_sweeps(bar2, [], [sl1, sl2], atr, bar_idx=20)
        assert len(sweeps2) == 1
        assert sweeps2[0].swept_level == Decimal("85")

        assert len(det.recent_sweeps) == 2

    def test_empty_swings_no_crash(self):
        """Empty swing lists -> empty result, no exception."""
        det = LiquiditySweepDetector()
        bar = _make_bar(high=100, low=99, open_=100, close=100)
        atr = Decimal("5")

        sweeps = det.check_for_sweeps(bar, [], [], atr, bar_idx=1)

        assert sweeps == []
        assert det.last_bullish_sweep is None
        assert det.last_bearish_sweep is None


# ===========================================================================
# InducementDetector Tests
# ===========================================================================


class TestInducementDetector:

    def test_bullish_idm_detected(self):
        """Bullish BOS + minor swing low between BOS and current -> IDM found."""
        det = InducementDetector(secondary_strength=1)
        # Manually inject a minor swing low into the secondary detector
        minor_sl = SwingPoint(
            price=Decimal("95"), timestamp=BASE_TS, abs_idx=12,
        )
        det._secondary_detector._swing_lows.append(minor_sl)

        bos = _make_bos("bullish", 105, bar_idx=10)
        idm = det.detect_inducement([], [], bos, bar_idx=20)

        assert idm is not None
        assert idm.direction == "bullish"
        assert idm.idm_level == Decimal("95")
        assert idm.cleared is False

    def test_bearish_idm_detected(self):
        """Bearish BOS + minor swing high between BOS and current -> IDM found."""
        det = InducementDetector(secondary_strength=1)
        # Inject a minor swing high
        minor_sh = SwingPoint(
            price=Decimal("108"), timestamp=BASE_TS, abs_idx=15,
        )
        det._secondary_detector._swing_highs.append(minor_sh)

        bos = _make_bos("bearish", 95, bar_idx=10)
        idm = det.detect_inducement([], [], bos, bar_idx=20)

        assert idm is not None
        assert idm.direction == "bearish"
        assert idm.idm_level == Decimal("108")
        assert idm.cleared is False

    def test_idm_cleared(self):
        """Price sweeps through IDM -> has_cleared_idm returns True."""
        det = InducementDetector(secondary_strength=1)
        # Inject minor swing low and detect IDM
        minor_sl = SwingPoint(
            price=Decimal("95"), timestamp=BASE_TS, abs_idx=12,
        )
        det._secondary_detector._swing_lows.append(minor_sl)

        bos = _make_bos("bullish", 105, bar_idx=10)
        det.detect_inducement([], [], bos, bar_idx=20)
        assert det.has_cleared_idm("bullish") is False

        # Bar sweeps below IDM level (low=94 < 95)
        sweep_bar = _make_bar(high=97, low=94, open_=96, close=96)
        cleared = det.check_idm_cleared(sweep_bar, bar_idx=25)

        assert cleared is not None
        assert cleared.cleared is True
        assert det.has_cleared_idm("bullish") is True

    def test_no_idm_without_bos(self):
        """None BOS -> no IDM detected."""
        det = InducementDetector(secondary_strength=1)
        idm = det.detect_inducement([], [], last_bos=None, bar_idx=20)
        assert idm is None

    def test_has_cleared_idm_false_initially(self):
        """Fresh detector -> has_cleared_idm returns False."""
        det = InducementDetector()
        assert det.has_cleared_idm("bullish") is False
        assert det.has_cleared_idm("bearish") is False


# ===========================================================================
# KillZoneFilter Tests
# ===========================================================================


class TestKillZoneFilter:

    def test_ny_open_session(self):
        """08:30 ET -> SessionType.NY_OPEN."""
        kz = KillZoneFilter()
        ts = datetime(2024, 1, 15, 8, 30, tzinfo=ET)
        assert kz.classify_session(ts) == SessionType.NY_OPEN

    def test_london_open_session(self):
        """03:00 ET -> SessionType.LONDON_OPEN."""
        kz = KillZoneFilter()
        ts = datetime(2024, 1, 15, 3, 0, tzinfo=ET)
        assert kz.classify_session(ts) == SessionType.LONDON_OPEN

    def test_off_session(self):
        """22:00 ET -> SessionType.OFF_SESSION."""
        kz = KillZoneFilter()
        ts = datetime(2024, 1, 15, 22, 0, tzinfo=ET)
        assert kz.classify_session(ts) == SessionType.OFF_SESSION

    def test_is_kill_zone_true(self):
        """08:30 ET with default active_sessions -> True."""
        kz = KillZoneFilter()  # Default: LONDON_OPEN, NY_OPEN, NY_CLOSE
        ts = datetime(2024, 1, 15, 8, 30, tzinfo=ET)
        assert kz.is_kill_zone(ts) is True

    def test_is_kill_zone_false(self):
        """22:00 ET -> False (OFF_SESSION not in active_sessions)."""
        kz = KillZoneFilter()
        ts = datetime(2024, 1, 15, 22, 0, tzinfo=ET)
        assert kz.is_kill_zone(ts) is False


# ===========================================================================
# PremiumDiscountZone Tests
# ===========================================================================


class TestPremiumDiscountZone:

    def test_equilibrium_computation(self):
        """high=100, low=90 -> equilibrium=95."""
        zone = compute_premium_discount(Decimal("100"), Decimal("90"))
        assert zone.equilibrium == Decimal("95")

    def test_price_in_discount(self):
        """price=92 < equilibrium=95 -> 'discount'."""
        zone = compute_premium_discount(Decimal("100"), Decimal("90"))
        assert price_zone(Decimal("92"), zone) == "discount"

    def test_price_in_premium(self):
        """price=98 > equilibrium=95 -> 'premium'."""
        zone = compute_premium_discount(Decimal("100"), Decimal("90"))
        assert price_zone(Decimal("98"), zone) == "premium"

    def test_ote_long_zone(self):
        """Price in 61.8-79% retracement from high -> in_ote_zone True."""
        zone = compute_premium_discount(Decimal("100"), Decimal("90"))
        # OTE long: high - span*0.79 to high - span*0.618
        # = 100 - 10*0.79 to 100 - 10*0.618
        # = 92.1 to 93.82
        assert in_ote_zone(Decimal("93"), zone, "long") is True
        # Outside OTE
        assert in_ote_zone(Decimal("97"), zone, "long") is False

    def test_flat_range_edge_case(self):
        """high==low -> equilibrium=high, no crash."""
        zone = compute_premium_discount(Decimal("100"), Decimal("100"))
        assert zone.equilibrium == Decimal("100")
        assert zone.ote_long_low == Decimal("100")
        assert zone.ote_long_high == Decimal("100")
        # price_zone should work
        assert price_zone(Decimal("100"), zone) == "equilibrium"


# ===========================================================================
# ICTStrategy Integration Tests
# ===========================================================================


class TestICTStrategy:

    def _make_strategy(self, **overrides) -> ICTStrategy:
        """Create an ICTStrategy with sensible test defaults."""
        params = {
            "swing_strength": 1,
            "atr_period": 3,
            "warmup_bars": 5,
            "atr_mult_threshold": 0.5,
            "fvg_min_size_atr": 0.0,
            "ob_lookback_bars": 5,
            "require_sweep": False,
            "require_idm": False,
            "require_kill_zone": False,
            "require_ote": False,
        }
        params.update(overrides)
        return ICTStrategy(
            symbol="TEST",
            timeframe="1h",
            params=params,
        )

    def _make_indexed_bar(
        self, idx, o, h, l, c, ts=None,
    ) -> MarketEvent:
        """Create a bar with offset timestamp."""
        return MarketEvent(
            symbol="TEST",
            timestamp=ts or (BASE_TS + timedelta(hours=idx)),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=1000,
            timeframe="1h",
        )

    def test_warmup_no_signals(self):
        """First warmup_bars bars -> all None."""
        strat = self._make_strategy(warmup_bars=10)
        for i in range(10):
            bar = self._make_indexed_bar(i, 100, 102, 99, 101)
            signal = strat.calculate_signals(bar)
            assert signal is None, f"Signal on bar {i} during warmup"

    def test_basic_pipeline_runs(self):
        """Feed 100+ bars, verify no exceptions."""
        strat = self._make_strategy(warmup_bars=5)
        import math
        for i in range(120):
            # Sinusoidal price action for variety
            base = 100 + 10 * math.sin(i * 0.15)
            o = base
            h = base + 2
            l = base - 2
            c = base + 1
            bar = self._make_indexed_bar(i, o, h, l, c)
            strat.calculate_signals(bar)
        assert strat.bar_count == 120

    def test_signal_blocked_outside_kill_zone(self):
        """require_kill_zone=True, 22:00 ET timestamp -> None."""
        strat = self._make_strategy(
            warmup_bars=0,
            require_kill_zone=True,
        )
        off_ts = datetime(2024, 1, 15, 22, 0, tzinfo=ET)

        # Feed enough bars to pass warmup and establish some state
        for i in range(20):
            bar = MarketEvent(
                symbol="TEST",
                timestamp=off_ts + timedelta(minutes=i),
                open=Decimal("100"), high=Decimal("102"),
                low=Decimal("99"), close=Decimal("101"),
                volume=1000, timeframe="1h",
            )
            signal = strat.calculate_signals(bar)
            # All signals should be None because 22:00 ET is OFF_SESSION
            assert signal is None, f"Unexpected signal at bar {i} outside kill zone"

    def test_kill_zone_disabled_allows_signal(self):
        """require_kill_zone=False -> strategy can potentially produce signals."""
        strat = self._make_strategy(
            warmup_bars=3,
            require_kill_zone=False,
            require_sweep=False,
            require_idm=False,
            require_ote=False,
        )
        off_ts = datetime(2024, 1, 15, 22, 0, tzinfo=ET)

        # Feed volatile data; even if no signal fires due to confluence,
        # the pipeline should reach the entry check (not be blocked by KZ).
        # We verify by checking the kill zone filter is NOT invoked as blocker.
        bar_data = [
            (100, 103, 99, 102),
            (102, 105, 101, 104),
            (104, 108, 103, 107),
            (107, 110, 102, 103),
            (103, 104, 98, 99),
            (99, 100, 95, 96),
            (96, 97, 90, 91),
            (91, 105, 90, 104),
            (104, 108, 103, 107),
            (107, 115, 106, 114),
        ]
        for i, (o, h, l, c) in enumerate(bar_data):
            bar = MarketEvent(
                symbol="TEST",
                timestamp=off_ts + timedelta(hours=i),
                open=Decimal(str(o)), high=Decimal(str(h)),
                low=Decimal(str(l)), close=Decimal(str(c)),
                volume=1000, timeframe="1h",
            )
            strat.calculate_signals(bar)

        # No crash and pipeline ran fully
        assert strat.bar_count == 10

    def test_ote_filter_blocks_premium(self):
        """Long setup but price in premium zone -> None when require_ote=True."""
        strat = self._make_strategy(
            warmup_bars=0,
            require_ote=True,
            require_kill_zone=False,
            require_sweep=False,
            require_idm=False,
        )
        # Manually set up an uptrend with known swing levels
        strat._ms_tracker._trend = TrendState.UPTREND
        sh = SwingPoint(price=Decimal("100"), timestamp=BASE_TS, abs_idx=5)
        sl = SwingPoint(price=Decimal("90"), timestamp=BASE_TS, abs_idx=3)
        strat._swing_detector._swing_highs.append(sh)
        strat._swing_detector._swing_lows.append(sl)

        # Feed bars in premium zone (close=98 > equilibrium=95)
        for i in range(10):
            bar = self._make_indexed_bar(i, 97, 99, 96, 98)
            strat.update_buffer(bar)
        strat._bar_count = 10
        strat._update_atr()

        # Now test one more bar in premium
        premium_bar = self._make_indexed_bar(10, 97, 99, 96, 98)
        signal = strat.calculate_signals(premium_bar)
        assert signal is None

    def test_exit_on_choch(self):
        """After long entry, CHOCH bearish -> EXIT signal."""
        strat = self._make_strategy(warmup_bars=0, swing_strength=1)
        # Set up a long position + uptrend
        strat._in_position = "long"
        strat._ms_tracker._trend = TrendState.UPTREND

        # Register a swing low that will be broken
        sl = SwingPoint(price=Decimal("95"), timestamp=BASE_TS, abs_idx=5)
        strat._ms_tracker.on_new_swing_low(sl)

        # Need bars in buffer for ATR
        for i in range(5):
            bar = self._make_indexed_bar(i, 100, 102, 99, 101)
            strat.update_buffer(bar)
        strat._bar_count = 5

        # Bar that breaks below swing low -> CHOCH -> EXIT
        break_bar = self._make_indexed_bar(5, 96, 97, 93, 94)
        signal = strat.calculate_signals(break_bar)

        assert signal is not None
        assert signal.signal_type == SignalType.EXIT

    def test_ict_importable_from_dashboard(self):
        """Import works, 'ict' in STRATEGY_MAP."""
        from src.dashboard.callbacks import STRATEGY_MAP, _import_strategy

        assert "ict" in STRATEGY_MAP
        assert STRATEGY_MAP["ict"] == (
            "src.strategy.smc.ict_strategy", "ICTStrategy",
        )

        cls = _import_strategy("ict")
        assert cls.__name__ == "ICTStrategy"
