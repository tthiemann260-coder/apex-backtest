"""Tests for Strategy Layer — BaseStrategy, Reversal, Breakout, FVG."""

from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy
from src.strategy.reversal import ReversalStrategy
from src.strategy.breakout import BreakoutStrategy
from src.strategy.fvg import FVGStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    close: str = "100.00",
    high: str = "101.00",
    low: str = "99.00",
    open_: str = "100.00",
    volume: int = 1000,
    day_offset: int = 0,
) -> MarketEvent:
    """Create a MarketEvent with configurable price."""
    return MarketEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, 15 + day_offset, 10, 0),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        timeframe="1d",
    )


class _DummyStrategy(BaseStrategy):
    """Minimal concrete strategy for testing BaseStrategy."""

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        # Simple: emit LONG if close > 100, else None
        if event.close > Decimal("100"):
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.LONG,
                strength=Decimal("0.8"),
            )
        return None


# ===========================================================================
# TestBaseStrategyAbstraction
# ===========================================================================

class TestBaseStrategyAbstraction:
    """STRAT-01: BaseStrategy is ABC, cannot be instantiated directly."""

    def test_base_strategy_is_abstract(self):
        """Instantiating BaseStrategy directly raises TypeError."""
        with pytest.raises(TypeError):
            BaseStrategy(symbol="TEST", timeframe="1d")

    def test_concrete_strategy_instantiates(self):
        """Subclass with calculate_signals can be instantiated."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        assert strategy is not None

    def test_calculate_signals_returns_signal_or_none(self):
        """calculate_signals returns SignalEvent or None."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        bar_above = _make_bar(close="101.00")
        bar_below = _make_bar(close="99.00")

        result_signal = strategy.calculate_signals(bar_above)
        result_none = strategy.calculate_signals(bar_below)

        assert isinstance(result_signal, SignalEvent)
        assert result_none is None

    def test_calculate_signals_receives_market_event(self):
        """calculate_signals is called with a MarketEvent."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        bar = _make_bar()
        # Should not raise — method accepts MarketEvent
        strategy.calculate_signals(bar)


# ===========================================================================
# TestRollingBuffer
# ===========================================================================

class TestRollingBuffer:
    """STRAT-08: Strategy maintains a rolling buffer of historical bars."""

    def test_buffer_starts_empty(self):
        """Buffer has no bars before any event is processed."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        assert len(strategy.bars) == 0

    def test_buffer_grows_with_events(self):
        """Buffer size increases with each bar processed."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        for i in range(5):
            bar = _make_bar(day_offset=i)
            strategy.update_buffer(bar)
        assert len(strategy.bars) == 5

    def test_buffer_respects_max_size(self):
        """Oldest bars are dropped when buffer exceeds max_buffer_size."""
        strategy = _DummyStrategy(
            symbol="TEST", timeframe="1d", max_buffer_size=3,
        )
        for i in range(10):
            bar = _make_bar(day_offset=i)
            strategy.update_buffer(bar)
        assert len(strategy.bars) == 3
        # Most recent bar should be the last one added
        assert strategy.bars[-1].timestamp.day == 24  # 15 + 9

    def test_buffer_contains_only_past_bars(self):
        """All bars in buffer have timestamps <= current bar."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        bars = [_make_bar(day_offset=i) for i in range(5)]
        for bar in bars:
            strategy.update_buffer(bar)

        # After processing bar at day_offset=4, all buffer bars should be <= that timestamp
        current = bars[-1].timestamp
        for buffered_bar in strategy.bars:
            assert buffered_bar.timestamp <= current


# ===========================================================================
# TestParameterInjection
# ===========================================================================

class TestParameterInjection:
    """STRAT-07: Parameters injected at instantiation."""

    def test_custom_params_stored(self):
        """Custom parameters passed at init are accessible."""
        strategy = _DummyStrategy(
            symbol="TEST", timeframe="1d",
            params={"sma_period": 20, "rsi_threshold": 30},
        )
        assert strategy.params["sma_period"] == 20
        assert strategy.params["rsi_threshold"] == 30

    def test_default_params(self):
        """Strategy works with empty params dict (defaults)."""
        strategy = _DummyStrategy(symbol="TEST", timeframe="1d")
        assert strategy.params == {}

    def test_params_immutable_during_run(self):
        """Params dict cannot be modified externally during a run."""
        strategy = _DummyStrategy(
            symbol="TEST", timeframe="1d",
            params={"sma_period": 20},
        )
        # Get a copy — modifying it shouldn't affect strategy
        params_copy = strategy.params
        params_copy["sma_period"] = 999
        assert strategy.params["sma_period"] == 20


# ---------------------------------------------------------------------------
# Helpers for concrete strategy tests
# ---------------------------------------------------------------------------

def _generate_trending_bars(
    start_price: float = 100.0,
    count: int = 200,
    trend: str = "up",
    volatility: float = 1.0,
) -> list[MarketEvent]:
    """Generate a synthetic bar series with a clear trend."""
    import math
    bars = []
    price = start_price
    for i in range(count):
        if trend == "up":
            price += volatility * 0.2
        elif trend == "down":
            price -= volatility * 0.2
        else:
            price = start_price + volatility * 2 * math.sin(i * 0.3)

        noise = volatility * math.sin(i * 1.7) * 0.5
        open_ = price + noise * 0.3
        high = max(price, open_) + abs(noise) + 0.1
        low = min(price, open_) - abs(noise) - 0.1
        close = price + noise * 0.1

        day = 1 + i // 1440
        hour = (i // 60) % 24
        minute = i % 60
        bars.append(MarketEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, day, hour, minute),
            open=Decimal(str(round(open_, 2))),
            high=Decimal(str(round(high, 2))),
            low=Decimal(str(round(low, 2))),
            close=Decimal(str(round(close, 2))),
            volume=1000 + i * 10,
            timeframe="1d",
        ))
    return bars


def _generate_rsi_extreme_bars(direction: str = "oversold", count: int = 50) -> list[MarketEvent]:
    """Generate bars that push RSI to extreme levels."""
    bars = []
    price = 100.0
    for i in range(count):
        if direction == "oversold":
            if i < 30:
                price -= 0.8
            else:
                price += 0.1
        else:
            if i < 30:
                price += 0.8
            else:
                price -= 0.1

        open_ = price + 0.1
        high = price + 0.5
        low = price - 0.5
        close = price

        bars.append(MarketEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 10, i),
            open=Decimal(str(round(open_, 2))),
            high=Decimal(str(round(high, 2))),
            low=Decimal(str(round(low, 2))),
            close=Decimal(str(round(close, 2))),
            volume=1000,
            timeframe="1d",
        ))
    return bars


def _generate_breakout_bars(count: int = 50) -> list[MarketEvent]:
    """Generate bars: consolidation then breakout."""
    import math
    bars = []
    for i in range(count):
        if i < 30:
            price = 100.0 + math.sin(i * 0.5) * 0.8
            vol = 500
        else:
            price = 101.0 + (i - 30) * 0.5
            vol = 2000

        open_ = price - 0.1
        high = price + 0.3
        low = price - 0.3
        close = price

        bars.append(MarketEvent(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1, 10, i),
            open=Decimal(str(round(open_, 2))),
            high=Decimal(str(round(high, 2))),
            low=Decimal(str(round(low, 2))),
            close=Decimal(str(round(close, 2))),
            volume=vol,
            timeframe="1d",
        ))
    return bars


def _generate_fvg_bars() -> list[MarketEvent]:
    """Generate bars that create a bullish FVG and then fill it."""
    return [
        MarketEvent(
            symbol="TEST", timestamp=datetime(2024, 1, 1, 10, 0),
            open=Decimal("99"), high=Decimal("100"), low=Decimal("98"),
            close=Decimal("99.5"), volume=1000, timeframe="1d",
        ),
        MarketEvent(
            symbol="TEST", timestamp=datetime(2024, 1, 1, 10, 1),
            open=Decimal("100"), high=Decimal("105"), low=Decimal("99.5"),
            close=Decimal("104"), volume=2000, timeframe="1d",
        ),
        MarketEvent(
            symbol="TEST", timestamp=datetime(2024, 1, 1, 10, 2),
            open=Decimal("104"), high=Decimal("106"), low=Decimal("103"),
            close=Decimal("105"), volume=1500, timeframe="1d",
        ),
        MarketEvent(
            symbol="TEST", timestamp=datetime(2024, 1, 1, 10, 3),
            open=Decimal("105"), high=Decimal("105"), low=Decimal("101"),
            close=Decimal("102"), volume=1000, timeframe="1d",
        ),
        MarketEvent(
            symbol="TEST", timestamp=datetime(2024, 1, 1, 10, 4),
            open=Decimal("102"), high=Decimal("107"), low=Decimal("101.5"),
            close=Decimal("106"), volume=1200, timeframe="1d",
        ),
    ]


# ===========================================================================
# TestReversalStrategy
# ===========================================================================

class TestReversalStrategy:
    """STRAT-04: Reversal (Mean Reversion) strategy."""

    def test_reversal_instantiates(self):
        s = ReversalStrategy(symbol="AAPL", timeframe="1d")
        assert s.symbol == "AAPL"

    def test_reversal_custom_params(self):
        s = ReversalStrategy(
            symbol="AAPL", timeframe="1d",
            params={"rsi_period": 10, "rsi_oversold": 25},
        )
        assert s.params["rsi_period"] == 10
        assert s.params["rsi_oversold"] == 25

    def test_reversal_no_signal_insufficient_bars(self):
        s = ReversalStrategy(symbol="AAPL", timeframe="1d")
        result = s.calculate_signals(_make_bar())
        assert result is None

    def test_reversal_generates_long_on_oversold(self):
        s = ReversalStrategy(
            symbol="TEST", timeframe="1d",
            params={"rsi_period": 14, "rsi_oversold": 30, "sma_period": 5},
        )
        bars = _generate_rsi_extreme_bars(direction="oversold", count=50)
        signals = []
        for bar in bars:
            sig = s.calculate_signals(bar)
            if sig is not None:
                signals.append(sig)
        assert len(signals) > 0
        long_signals = [s for s in signals if s.signal_type == SignalType.LONG]
        assert len(long_signals) > 0

    def test_reversal_signal_has_correct_symbol(self):
        s = ReversalStrategy(
            symbol="TEST", timeframe="1d",
            params={"rsi_period": 14, "rsi_oversold": 30, "sma_period": 5},
        )
        for bar in _generate_rsi_extreme_bars(direction="oversold", count=50):
            sig = s.calculate_signals(bar)
            if sig is not None:
                assert sig.symbol == "TEST"
                break

    def test_reversal_strength_is_decimal(self):
        s = ReversalStrategy(
            symbol="TEST", timeframe="1d",
            params={"rsi_period": 14, "rsi_oversold": 30, "sma_period": 5},
        )
        for bar in _generate_rsi_extreme_bars(direction="oversold", count=50):
            sig = s.calculate_signals(bar)
            if sig is not None:
                assert isinstance(sig.strength, Decimal)
                break


# ===========================================================================
# TestBreakoutStrategy
# ===========================================================================

class TestBreakoutStrategy:
    """STRAT-05: Breakout/Momentum strategy."""

    def test_breakout_instantiates(self):
        s = BreakoutStrategy(symbol="AAPL", timeframe="1d")
        assert s.symbol == "AAPL"

    def test_breakout_custom_params(self):
        s = BreakoutStrategy(
            symbol="AAPL", timeframe="1d",
            params={"lookback": 10, "volume_factor": 2.0},
        )
        assert s.params["lookback"] == 10

    def test_breakout_no_signal_insufficient_bars(self):
        s = BreakoutStrategy(symbol="AAPL", timeframe="1d")
        result = s.calculate_signals(_make_bar())
        assert result is None

    def test_breakout_generates_signal_on_breakout(self):
        s = BreakoutStrategy(
            symbol="TEST", timeframe="1d",
            params={"lookback": 20, "volume_factor": 1.5},
        )
        signals = []
        for bar in _generate_breakout_bars(count=50):
            sig = s.calculate_signals(bar)
            if sig is not None:
                signals.append(sig)
        assert len(signals) > 0
        long_signals = [s for s in signals if s.signal_type == SignalType.LONG]
        assert len(long_signals) > 0

    def test_breakout_signal_strength_is_decimal(self):
        s = BreakoutStrategy(
            symbol="TEST", timeframe="1d",
            params={"lookback": 20, "volume_factor": 1.5},
        )
        for bar in _generate_breakout_bars(count=50):
            sig = s.calculate_signals(bar)
            if sig is not None:
                assert isinstance(sig.strength, Decimal)
                break


# ===========================================================================
# TestFVGStrategy
# ===========================================================================

class TestFVGStrategy:
    """STRAT-06: Fair Value Gap (ICT 3-Candle) strategy."""

    def test_fvg_instantiates(self):
        s = FVGStrategy(symbol="AAPL", timeframe="1d")
        assert s.symbol == "AAPL"

    def test_fvg_custom_params(self):
        s = FVGStrategy(
            symbol="AAPL", timeframe="1d",
            params={"max_open_gaps": 3, "min_gap_size_pct": 0.5},
        )
        assert s.params["max_open_gaps"] == 3

    def test_fvg_no_signal_insufficient_bars(self):
        s = FVGStrategy(symbol="AAPL", timeframe="1d")
        result = s.calculate_signals(_make_bar())
        assert result is None

    def test_fvg_detects_bullish_gap_and_signals(self):
        s = FVGStrategy(
            symbol="TEST", timeframe="1d",
            params={"min_gap_size_pct": 0.1},
        )
        signals = []
        for bar in _generate_fvg_bars():
            sig = s.calculate_signals(bar)
            if sig is not None:
                signals.append(sig)
        assert len(signals) > 0
        long_signals = [s for s in signals if s.signal_type == SignalType.LONG]
        assert len(long_signals) > 0

    def test_fvg_signal_strength_is_decimal(self):
        s = FVGStrategy(
            symbol="TEST", timeframe="1d",
            params={"min_gap_size_pct": 0.1},
        )
        for bar in _generate_fvg_bars():
            sig = s.calculate_signals(bar)
            if sig is not None:
                assert isinstance(sig.strength, Decimal)
                break


# ===========================================================================
# TestSignalTypes
# ===========================================================================

class TestSignalTypes:
    """STRAT-02: Signals restricted to LONG, SHORT, EXIT."""

    def test_signal_type_long(self):
        assert SignalType.LONG is not None

    def test_signal_type_short(self):
        assert SignalType.SHORT is not None

    def test_signal_type_exit(self):
        assert SignalType.EXIT is not None

    def test_only_three_signal_types(self):
        assert len(SignalType) == 3


# ===========================================================================
# TestHistoricalOnlyAccess
# ===========================================================================

class TestHistoricalOnlyAccess:
    """STRAT-08: Strategies only see historical data."""

    def test_strategy_buffer_is_copy(self):
        s = _DummyStrategy(symbol="TEST", timeframe="1d")
        for i in range(5):
            s.update_buffer(_make_bar(day_offset=i))
        external_bars = s.bars
        external_bars.clear()
        assert len(s.bars) == 5

    def test_200_bar_run_no_exception(self):
        """All three strategies handle 200-bar synthetic dataset."""
        strategies = [
            ReversalStrategy(
                symbol="TEST", timeframe="1d",
                params={"rsi_period": 14, "rsi_oversold": 30, "sma_period": 5},
            ),
            BreakoutStrategy(
                symbol="TEST", timeframe="1d",
                params={"lookback": 20, "volume_factor": 1.5},
            ),
            FVGStrategy(
                symbol="TEST", timeframe="1d",
                params={"min_gap_size_pct": 0.05},
            ),
        ]
        bars = _generate_trending_bars(count=200)
        for strategy in strategies:
            for bar in bars:
                strategy.calculate_signals(bar)
