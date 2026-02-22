"""
test_regime.py — Tests for Phase 15: Regime Detection.

Covers:
- ATRRegimeClassifier (warmup, stable ATR, HIGH spike, LOW narrow, properties, empty buffer)
- ADXClassifier (warmup, strong uptrend, range, thresholds, DI values, downtrend, zero-range, properties)
- RegimeClassifier (STRONG_TREND, RANGING_NORMAL, frozen dataclass, bullish_pressure, property)
- RegimeGatedStrategy (pass-through, suppression, inner always called, current_regime, engine compat)

Requirement: TEST-21
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from typing import Optional

import pytest

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy
from src.strategy.regime.atr_regime import ATRRegimeClassifier, VolatilityRegime
from src.strategy.regime.adx_classifier import ADXClassifier, TrendStrength
from src.strategy.regime.classifier import (
    RegimeClassifier,
    RegimeType,
    MarketRegime,
)
from src.strategy.regime.gated_strategy import (
    RegimeGatedStrategy,
    create_regime_gated_ict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 15, 10, 0, 0)


def _make_bar(
    high, low, open_, close, idx=0,
    symbol="TEST", volume=1000, tf="1h",
) -> MarketEvent:
    """Create a MarketEvent with Decimal prices and indexed timestamp."""
    return MarketEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(hours=idx),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
        timeframe=tf,
    )


def _make_indexed_bar(idx: int, price: float, spread: float = 1.0) -> MarketEvent:
    """Create a bar centered around `price` with given spread."""
    return _make_bar(
        high=price + spread,
        low=price - spread,
        open_=price - spread * 0.3,
        close=price + spread * 0.3,
        idx=idx,
    )


class _MockAlwaysLongStrategy(BaseStrategy):
    """Mock strategy that always returns LONG signal."""

    def __init__(self) -> None:
        super().__init__(symbol="TEST", timeframe="1h")
        self.call_count = 0

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        self.call_count += 1
        return SignalEvent(
            symbol=event.symbol,
            timestamp=event.timestamp,
            signal_type=SignalType.LONG,
            strength=Decimal("0.9"),
        )


class _MockNeverSignalStrategy(BaseStrategy):
    """Mock strategy that never signals."""

    def __init__(self) -> None:
        super().__init__(symbol="TEST", timeframe="1h")
        self.call_count = 0

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        self.call_count += 1
        return None


# ---------------------------------------------------------------------------
# TestATRRegimeClassifier
# ---------------------------------------------------------------------------

class TestATRRegimeClassifier:
    """Tests for ATRRegimeClassifier (REG-01)."""

    def test_warmup_returns_normal(self):
        """During warmup (< atr_period history), regime = NORMAL."""
        clf = ATRRegimeClassifier(atr_period=14, regime_lookback=50)
        buf = [_make_indexed_bar(i, 100, 1.0) for i in range(5)]
        result = clf.update(buf)
        assert result == VolatilityRegime.NORMAL

    def test_stable_atr_returns_normal(self):
        """Consistent bars produce NORMAL regime."""
        clf = ATRRegimeClassifier(atr_period=5, regime_lookback=20)
        buf = [_make_indexed_bar(i, 100, 1.0) for i in range(30)]
        for end in range(6, len(buf) + 1):
            clf.update(buf[:end])
        assert clf.regime == VolatilityRegime.NORMAL

    def test_high_spike_detected(self):
        """Sudden volatility spike → HIGH regime."""
        clf = ATRRegimeClassifier(atr_period=5, regime_lookback=20)
        # 25 stable bars
        buf = [_make_indexed_bar(i, 100, 1.0) for i in range(25)]
        for end in range(6, 26):
            clf.update(buf[:end])

        # Inject high-volatility bars (spread 10x)
        for i in range(25, 35):
            buf.append(_make_indexed_bar(i, 100, 10.0))
            clf.update(buf)

        assert clf.regime == VolatilityRegime.HIGH

    def test_low_narrow_detected(self):
        """Compressed volatility after wide period → LOW regime."""
        clf = ATRRegimeClassifier(
            atr_period=5, regime_lookback=20,
            low_threshold=Decimal("0.75"), high_threshold=Decimal("1.50"),
        )
        # 20 wide bars
        buf = [_make_indexed_bar(i, 100, 5.0) for i in range(20)]
        for end in range(6, 21):
            clf.update(buf[:end])

        # Then very narrow bars
        for i in range(20, 35):
            buf.append(_make_indexed_bar(i, 100, 0.1))
            clf.update(buf)

        assert clf.regime == VolatilityRegime.LOW

    def test_properties(self):
        """Properties return correct values."""
        clf = ATRRegimeClassifier(atr_period=5)
        buf = [_make_indexed_bar(i, 100, 1.0) for i in range(10)]
        clf.update(buf)
        assert clf.regime == VolatilityRegime.NORMAL
        assert clf.current_atr >= Decimal("0")

    def test_empty_buffer(self):
        """Empty or single-bar buffer → NORMAL, ATR = 0."""
        clf = ATRRegimeClassifier()
        assert clf.update([]) == VolatilityRegime.NORMAL
        assert clf.current_atr == Decimal("0")

        single = [_make_indexed_bar(0, 100, 1.0)]
        assert clf.update(single) == VolatilityRegime.NORMAL

    def test_regime_property_consistency(self):
        """Returned value matches .regime property."""
        clf = ATRRegimeClassifier(atr_period=5)
        buf = [_make_indexed_bar(i, 100, 1.0) for i in range(10)]
        result = clf.update(buf)
        assert result == clf.regime


# ---------------------------------------------------------------------------
# TestADXClassifier
# ---------------------------------------------------------------------------

class TestADXClassifier:
    """Tests for ADXClassifier (REG-02)."""

    def test_warmup_returns_zero(self):
        """Before Phase A completes, ADX = 0."""
        clf = ADXClassifier(period=14)
        bars = [_make_indexed_bar(i, 100, 1.0) for i in range(5)]
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.adx == Decimal("0")

    def test_strong_uptrend_high_adx(self):
        """Steady uptrend should produce high ADX eventually."""
        clf = ADXClassifier(period=5)
        # Strong uptrend: price goes 100 → 200
        bars = [_make_indexed_bar(i, 100 + i * 3, 1.0) for i in range(50)]
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.adx > Decimal("20")
        assert clf.classify() in (TrendStrength.TRENDING, TrendStrength.STRONG_TREND, TrendStrength.WEAK_TREND)

    def test_range_low_adx(self):
        """Sideways market should produce low ADX."""
        clf = ADXClassifier(period=5)
        # Alternating up/down bars around 100
        bars = []
        for i in range(50):
            offset = 1 if i % 2 == 0 else -1
            bars.append(_make_indexed_bar(i, 100 + offset, 0.5))
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.adx < Decimal("30")

    def test_classify_thresholds(self):
        """Verify classification thresholds are respected."""
        clf = ADXClassifier(period=14)
        # Manually check classify logic
        clf._adx = Decimal("10")
        assert clf.classify() == TrendStrength.RANGING
        clf._adx = Decimal("22")
        assert clf.classify() == TrendStrength.WEAK_TREND
        clf._adx = Decimal("30")
        assert clf.classify() == TrendStrength.TRENDING
        clf._adx = Decimal("50")
        assert clf.classify() == TrendStrength.STRONG_TREND

    def test_di_values_uptrend(self):
        """+DI > -DI in uptrend."""
        clf = ADXClassifier(period=5)
        bars = [_make_indexed_bar(i, 100 + i * 2, 1.0) for i in range(30)]
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.plus_di > clf.minus_di

    def test_di_values_downtrend(self):
        """-DI > +DI in downtrend."""
        clf = ADXClassifier(period=5)
        bars = [_make_indexed_bar(i, 200 - i * 2, 1.0) for i in range(30)]
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.minus_di > clf.plus_di

    def test_zero_range_bars(self):
        """Zero-range bars (open=high=low=close) don't crash."""
        clf = ADXClassifier(period=5)
        bars = [_make_bar(100, 100, 100, 100, idx=i) for i in range(20)]
        for i in range(1, len(bars)):
            clf.update(bars[i], bars[i - 1])
        assert clf.adx == Decimal("0")

    def test_property_consistency(self):
        """adx property returns consistent value after update."""
        clf = ADXClassifier(period=5)
        bars = [_make_indexed_bar(i, 100 + i, 1.0) for i in range(20)]
        result = Decimal("0")
        for i in range(1, len(bars)):
            result = clf.update(bars[i], bars[i - 1])
        assert result == clf.adx


# ---------------------------------------------------------------------------
# TestRegimeClassifier
# ---------------------------------------------------------------------------

class TestRegimeClassifier:
    """Tests for composite RegimeClassifier (REG-03)."""

    def _feed_bars(self, clf, bars):
        """Feed a sequence of bars into the classifier."""
        for i, bar in enumerate(bars):
            buf = bars[:i + 1]
            clf.update(bar, buf)

    def test_strong_trend_classification(self):
        """Strong trending bars produce a trending-family regime."""
        clf = RegimeClassifier(atr_period=5, adx_period=5, regime_lookback=20)
        bars = [_make_indexed_bar(i, 100 + i * 3, 1.0) for i in range(50)]
        self._feed_bars(clf, bars)
        regime = clf.regime
        assert regime is not None
        assert regime.regime_type in (
            RegimeType.STRONG_TREND, RegimeType.MODERATE_TREND, RegimeType.WEAK_TREND,
        )

    def test_ranging_classification(self):
        """Flat range produces RANGING_* or CHOPPY."""
        clf = RegimeClassifier(atr_period=5, adx_period=5, regime_lookback=20)
        bars = []
        for i in range(50):
            offset = 0.5 if i % 2 == 0 else -0.5
            bars.append(_make_indexed_bar(i, 100 + offset, 0.5))
        self._feed_bars(clf, bars)
        regime = clf.regime
        assert regime is not None
        assert regime.regime_type in (
            RegimeType.RANGING_LOW, RegimeType.RANGING_NORMAL, RegimeType.CHOPPY,
            RegimeType.WEAK_TREND,
        )

    def test_frozen_dataclass(self):
        """MarketRegime is immutable."""
        clf = RegimeClassifier(atr_period=5, adx_period=5)
        bars = [_make_indexed_bar(i, 100 + i, 1.0) for i in range(20)]
        self._feed_bars(clf, bars)
        regime = clf.regime
        assert regime is not None
        with pytest.raises(AttributeError):
            regime.adx = Decimal("99")  # type: ignore[misc]

    def test_bullish_pressure(self):
        """Uptrend sets bullish_pressure=True."""
        clf = RegimeClassifier(atr_period=5, adx_period=5)
        bars = [_make_indexed_bar(i, 100 + i * 3, 1.0) for i in range(30)]
        self._feed_bars(clf, bars)
        regime = clf.regime
        assert regime is not None
        assert regime.bullish_pressure is True

    def test_regime_property_before_update(self):
        """Before any update, regime is None."""
        clf = RegimeClassifier()
        assert clf.regime is None


# ---------------------------------------------------------------------------
# TestRegimeGatedStrategy
# ---------------------------------------------------------------------------

class TestRegimeGatedStrategy:
    """Tests for RegimeGatedStrategy (REG-04)."""

    def test_signal_passed_through(self):
        """Signal is forwarded when regime is in allowed set."""
        inner = _MockAlwaysLongStrategy()
        gated = RegimeGatedStrategy(
            inner_strategy=inner,
            allowed_regimes=list(RegimeType),  # allow ALL regimes
        )
        # Feed enough bars to produce a regime
        for i in range(5):
            bar = _make_indexed_bar(i, 100 + i, 1.0)
            result = gated.calculate_signals(bar)

        # With all regimes allowed, inner signal should pass through
        assert result is not None
        assert result.signal_type == SignalType.LONG

    def test_signal_suppressed_when_blocked(self):
        """Signal is suppressed when regime is not in allowed set."""
        inner = _MockAlwaysLongStrategy()
        # Only allow STRONG_TREND — unlikely in 5 bars
        gated = RegimeGatedStrategy(
            inner_strategy=inner,
            allowed_regimes=[RegimeType.STRONG_TREND],
            atr_period=5,
            adx_period=5,
        )
        # Feed a few bars — regime won't be STRONG_TREND in warmup
        bar = _make_indexed_bar(0, 100, 1.0)
        result = gated.calculate_signals(bar)
        # During warmup regime defaults to RANGING_NORMAL → blocked
        assert result is None

    def test_inner_always_called(self):
        """Inner strategy is always called even when gated."""
        inner = _MockAlwaysLongStrategy()
        gated = RegimeGatedStrategy(
            inner_strategy=inner,
            allowed_regimes=[],  # block everything
        )
        for i in range(10):
            bar = _make_indexed_bar(i, 100, 1.0)
            gated.calculate_signals(bar)

        assert inner.call_count == 10

    def test_current_regime_property(self):
        """current_regime property returns MarketRegime after update."""
        inner = _MockNeverSignalStrategy()
        gated = RegimeGatedStrategy(
            inner_strategy=inner,
            allowed_regimes=list(RegimeType),
        )
        assert gated.current_regime is None

        for i in range(5):
            bar = _make_indexed_bar(i, 100 + i, 1.0)
            gated.calculate_signals(bar)

        assert gated.current_regime is not None
        assert isinstance(gated.current_regime, MarketRegime)

    def test_create_regime_gated_ict_factory(self):
        """Factory function produces a usable RegimeGatedStrategy."""
        strategy = create_regime_gated_ict(
            symbol="TEST",
            timeframe="1h",
            params={"atr_period": 10, "adx_period": 10},
        )
        assert isinstance(strategy, RegimeGatedStrategy)
        assert strategy.symbol == "TEST"
        assert strategy.timeframe == "1h"

        # Should not crash with a bar
        bar = _make_indexed_bar(0, 100, 1.0)
        result = strategy.calculate_signals(bar)
        assert result is None  # warmup
