"""Tests for BacktestEngine — event orchestration, sweep isolation, causality."""

from __future__ import annotations

import csv
import tempfile
import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.data_handler import DataHandler
from src.engine import BacktestEngine, BacktestResult, create_engine
from src.events import (
    FillEvent, MarketEvent, SignalEvent, SignalType,
    OrderEvent, OrderSide,
)
from src.execution import ExecutionHandler
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_test_csv(rows: list[dict], filepath: Path) -> None:
    """Write OHLCV CSV file."""
    fieldnames = ["Date", "Open", "High", "Low", "Close", "Volume"]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _make_500_bar_csv(tmp_path: Path) -> Path:
    """Create a 500-bar CSV with a clear trend for testing."""
    import math
    filepath = tmp_path / "test_500.csv"
    rows = []
    price = 100.0
    for i in range(500):
        price += 0.1 * math.sin(i * 0.1)  # oscillating up
        rows.append({
            "Date": f"2024-01-{1 + i // 24:02d} {i % 24:02d}:00:00",
            "Open": f"{price - 0.1:.2f}",
            "High": f"{price + 0.5:.2f}",
            "Low": f"{price - 0.5:.2f}",
            "Close": f"{price:.2f}",
            "Volume": 1000,
        })
    _create_test_csv(rows, filepath)
    return filepath


class _AlwaysLongStrategy(BaseStrategy):
    """Strategy that goes LONG on bar 5, EXIT on bar 10."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bar_count = 0

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        self._bar_count += 1

        if self._bar_count == 5:
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.LONG,
                strength=Decimal("0.8"),
            )
        if self._bar_count == 10:
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal("0.5"),
            )
        return None


class _NeverTradeStrategy(BaseStrategy):
    """Strategy that never generates signals."""

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        return None


# ===========================================================================
# TestEngineOrchestration
# ===========================================================================

class TestEngineOrchestration:
    """EDA-03: Engine dispatches events without own trading logic."""

    def test_engine_completes_without_exception(self, tmp_path):
        """Full backtest run on 500-bar dataset completes."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        assert isinstance(result, BacktestResult)
        assert result.total_bars == 500

    def test_engine_produces_equity_log(self, tmp_path):
        """Engine produces equity log with one entry per bar."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        assert len(result.equity_log) == 500

    def test_engine_produces_fills(self, tmp_path):
        """Engine produces fill events when strategy trades."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        # Should have at least 2 fills: entry + exit
        assert len(result.fill_log) >= 2

    def test_engine_no_trades_no_fills(self, tmp_path):
        """Engine with passive strategy produces no fills."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        assert len(result.fill_log) == 0
        assert result.total_bars == 500


# ===========================================================================
# TestCausality
# ===========================================================================

class TestCausality:
    """Causality check: events flow in correct causal order."""

    def test_event_timestamps_non_decreasing(self, tmp_path):
        """All event timestamps are non-decreasing across the event log."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        timestamps = [e.timestamp for e in result.event_log]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Causality violation at index {i}: "
                f"{timestamps[i]} < {timestamps[i-1]}"
            )

    def test_fill_after_signal(self, tmp_path):
        """Fills never occur before their generating signal."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        first_signal_time = None
        first_fill_time = None
        for e in result.event_log:
            if isinstance(e, SignalEvent) and first_signal_time is None:
                first_signal_time = e.timestamp
            if isinstance(e, FillEvent) and first_fill_time is None:
                first_fill_time = e.timestamp

        if first_signal_time and first_fill_time:
            assert first_fill_time >= first_signal_time


# ===========================================================================
# TestSweepIsolation
# ===========================================================================

class TestSweepIsolation:
    """EDA-04: Each sweep iteration gets fresh components."""

    def test_create_engine_returns_fresh_instance(self, tmp_path):
        """create_engine() returns a new BacktestEngine each call."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh1 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s1 = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        dh2 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s2 = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")

        engine1 = create_engine(dh1, s1)
        engine2 = create_engine(dh2, s2)

        assert engine1 is not engine2

    def test_consecutive_runs_identical_results(self, tmp_path):
        """Two consecutive runs with same params produce identical equity logs."""
        csv_path = _make_500_bar_csv(tmp_path)

        dh1 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s1 = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine1 = create_engine(dh1, s1)
        result1 = engine1.run()

        dh2 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s2 = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine2 = create_engine(dh2, s2)
        result2 = engine2.run()

        assert len(result1.equity_log) == len(result2.equity_log)
        for e1, e2 in zip(result1.equity_log, result2.equity_log):
            assert e1["equity"] == e2["equity"]

    def test_no_state_leakage_between_runs(self, tmp_path):
        """State from run 1 doesn't leak into run 2."""
        csv_path = _make_500_bar_csv(tmp_path)

        # Run 1: with trades
        dh1 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s1 = _AlwaysLongStrategy(symbol="TEST", timeframe="1d")
        engine1 = create_engine(dh1, s1)
        result1 = engine1.run()

        # Run 2: no trades (fresh engine)
        dh2 = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        s2 = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine2 = create_engine(dh2, s2)
        result2 = engine2.run()

        # Run 2 should have no fills (not contaminated by run 1)
        assert len(result2.fill_log) == 0


# ===========================================================================
# TestBacktestResult
# ===========================================================================

class TestBacktestResult:
    """BacktestResult data integrity."""

    def test_result_has_final_equity(self, tmp_path):
        """BacktestResult includes final equity."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        assert result.final_equity > Decimal("0")

    def test_result_equity_is_decimal(self, tmp_path):
        """Final equity is Decimal."""
        csv_path = _make_500_bar_csv(tmp_path)
        dh = DataHandler(symbol="TEST", csv_path=csv_path, source="csv")
        strategy = _NeverTradeStrategy(symbol="TEST", timeframe="1d")
        engine = create_engine(dh, strategy)

        result = engine.run()

        assert isinstance(result.final_equity, Decimal)
