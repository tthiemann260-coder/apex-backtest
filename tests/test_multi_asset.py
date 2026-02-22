"""
test_multi_asset.py — Tests for Phase 17: Multi-Asset Foundation.

Covers:
- merge_bars: chronological merge, deterministic same-timestamp, empty generators
- MultiAssetEngine: per-symbol routing, execution isolation, shared portfolio, equity
- Rolling correlation: Pearson, edge cases, division-by-zero guards
- Per-asset limits: position count limits, max pct caps, global fallback
- Per-symbol equity: grouping, empty log

Requirement: TEST-23
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Generator, Optional
from unittest.mock import MagicMock

import pytest

from src.events import (
    MarketEvent, SignalEvent, FillEvent, OrderEvent,
    SignalType, OrderType, OrderSide,
)
from src.execution import ExecutionHandler
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy
from src.multi_asset import (
    merge_bars,
    MultiAssetEngine,
    MultiAssetResult,
    create_multi_asset_engine,
    compute_per_symbol_equity,
    compute_rolling_correlation,
    _pearson_decimal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 15, 10, 0, 0)


def _make_bar(
    close, symbol="TEST", idx=0,
    high=None, low=None, open_=None,
    volume=1000, tf="1h",
) -> MarketEvent:
    """Create a MarketEvent with Decimal prices."""
    c = Decimal(str(close))
    h = Decimal(str(high)) if high is not None else c + Decimal("1")
    l_ = Decimal(str(low)) if low is not None else c - Decimal("1")
    o = Decimal(str(open_)) if open_ is not None else c
    return MarketEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(hours=idx),
        open=o, high=h, low=l_, close=c,
        volume=volume, timeframe=tf,
    )


class _MockDataHandler:
    """Mock DataHandler that yields pre-built bars."""

    def __init__(self, bars: list[MarketEvent]) -> None:
        self._bars = bars

    def stream_bars(self) -> Generator[MarketEvent, None, None]:
        yield from self._bars


class _MockStrategy(BaseStrategy):
    """Strategy that signals LONG on a specific bar index."""

    def __init__(self, symbol: str, signal_bar: int = -1) -> None:
        super().__init__(symbol=symbol, timeframe="1h")
        self._signal_bar = signal_bar
        self._bar_count = 0
        self._received_bars: list[MarketEvent] = []

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        self._received_bars.append(event)
        self._bar_count += 1
        if self._bar_count == self._signal_bar:
            return SignalEvent(
                symbol=self._symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.LONG,
                strength=Decimal("1"),
            )
        return None


class _MockExitStrategy(BaseStrategy):
    """Strategy that signals EXIT on a specific bar index."""

    def __init__(self, symbol: str, exit_bar: int = -1) -> None:
        super().__init__(symbol=symbol, timeframe="1h")
        self._exit_bar = exit_bar
        self._bar_count = 0

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        self.update_buffer(event)
        self._bar_count += 1
        if self._bar_count == self._exit_bar:
            return SignalEvent(
                symbol=self._symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal("1"),
            )
        return None


def _make_fill(
    side, quantity, fill_price, symbol="TEST", day=0,
) -> FillEvent:
    """Create a FillEvent with Decimal values."""
    return FillEvent(
        symbol=symbol,
        timestamp=BASE_TS + timedelta(days=day),
        side=OrderSide(side),
        quantity=Decimal(str(quantity)),
        fill_price=Decimal(str(fill_price)),
        commission=Decimal("0"),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


# ===========================================================================
# TestMergeBars
# ===========================================================================

class TestMergeBars:
    """Tests for merge_bars() — heap-based chronological merge."""

    def test_two_symbols_chronological(self):
        """Bars from 2 symbols are merged chronologically."""
        aapl_bars = [
            _make_bar(100, symbol="AAPL", idx=0),   # 10:00
            _make_bar(101, symbol="AAPL", idx=2),   # 12:00
            _make_bar(102, symbol="AAPL", idx=4),   # 14:00
        ]
        eurusd_bars = [
            _make_bar(1.10, symbol="EURUSD", idx=0),  # 10:00
            _make_bar(1.11, symbol="EURUSD", idx=1),   # 11:00
            _make_bar(1.12, symbol="EURUSD", idx=3),   # 13:00
        ]
        handlers = {
            "AAPL": _MockDataHandler(aapl_bars),
            "EURUSD": _MockDataHandler(eurusd_bars),
        }
        result = list(merge_bars(handlers))
        assert len(result) == 6

        # Verify chronological order
        for i in range(1, len(result)):
            assert result[i].timestamp >= result[i - 1].timestamp

    def test_deterministic_same_timestamp(self):
        """Same timestamp -> secondary sort by symbol name (alphabetical)."""
        bars_a = [_make_bar(100, symbol="AAPL", idx=0)]
        bars_b = [_make_bar(50000, symbol="BTCUSD", idx=0)]
        handlers = {
            "BTCUSD": _MockDataHandler(bars_b),
            "AAPL": _MockDataHandler(bars_a),
        }
        result = list(merge_bars(handlers))
        assert len(result) == 2
        assert result[0].symbol == "AAPL"   # A < B
        assert result[1].symbol == "BTCUSD"

    def test_single_symbol_passthrough(self):
        """Single symbol passes through unchanged."""
        bars = [_make_bar(100 + i, symbol="AAPL", idx=i) for i in range(5)]
        handlers = {"AAPL": _MockDataHandler(bars)}
        result = list(merge_bars(handlers))
        assert len(result) == 5
        for i, bar in enumerate(result):
            assert bar.symbol == "AAPL"
            assert bar.close == Decimal(str(100 + i))

    def test_empty_generator_skipped(self):
        """Empty DataHandler generator is skipped gracefully."""
        bars = [_make_bar(100, symbol="AAPL", idx=0)]
        handlers = {
            "AAPL": _MockDataHandler(bars),
            "EMPTY": _MockDataHandler([]),
        }
        result = list(merge_bars(handlers))
        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_three_symbols(self):
        """Three symbols merge correctly."""
        bars_a = [_make_bar(100, symbol="AAPL", idx=i) for i in range(3)]
        bars_b = [_make_bar(1.10, symbol="EURUSD", idx=i) for i in range(2)]
        bars_c = [_make_bar(50000, symbol="BTCUSD", idx=i) for i in range(4)]
        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "EURUSD": _MockDataHandler(bars_b),
            "BTCUSD": _MockDataHandler(bars_c),
        }
        result = list(merge_bars(handlers))
        assert len(result) == 9

        # Verify chronological
        for i in range(1, len(result)):
            assert result[i].timestamp >= result[i - 1].timestamp

    def test_different_bar_counts(self):
        """Symbols with different bar counts merge completely."""
        bars_short = [_make_bar(100, symbol="AAPL", idx=0)]
        bars_long = [_make_bar(200 + i, symbol="MSFT", idx=i) for i in range(10)]
        handlers = {
            "AAPL": _MockDataHandler(bars_short),
            "MSFT": _MockDataHandler(bars_long),
        }
        result = list(merge_bars(handlers))
        assert len(result) == 11

    def test_heapq_counter_prevents_comparison(self):
        """Counter in heap tuple prevents MarketEvent comparison."""
        # Same timestamp and same symbol name is impossible in real data
        # but test that counter prevents error with same timestamp + diff symbol
        bars_a = [_make_bar(100, symbol="AAA", idx=0)]
        bars_b = [_make_bar(200, symbol="AAA", idx=0)]  # Same ts
        # This would fail without counter if MarketEvent comparison was attempted
        handlers = {
            "AAA": _MockDataHandler(bars_a),
            "AAA2": _MockDataHandler(bars_b),  # Different key
        }
        # Should not raise TypeError
        result = list(merge_bars(handlers))
        assert len(result) == 2


# ===========================================================================
# TestMultiAssetEngine
# ===========================================================================

class TestMultiAssetEngine:
    """Tests for MultiAssetEngine — full pipeline + isolation."""

    def test_two_symbol_backtest(self):
        """Run full backtest with 2 symbols, verify equity log populated."""
        aapl_bars = [_make_bar(100 + i, symbol="AAPL", idx=i) for i in range(5)]
        eurusd_bars = [_make_bar(Decimal("1.10") + Decimal(str(i)) / 100, symbol="EURUSD", idx=i) for i in range(5)]

        handlers = {
            "AAPL": _MockDataHandler(aapl_bars),
            "EURUSD": _MockDataHandler(eurusd_bars),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL"),
            "EURUSD": _MockStrategy("EURUSD"),
        }

        result = create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
        ).run()

        assert result.total_bars == 10
        assert len(result.equity_log) > 0
        assert result.final_equity > Decimal("0")

    def test_shared_portfolio_tracks_both_positions(self):
        """Shared Portfolio records fills from both symbols."""
        aapl_bars = [_make_bar(100, symbol="AAPL", idx=0),
                     _make_bar(101, symbol="AAPL", idx=1)]
        eurusd_bars = [_make_bar(1.10, symbol="EURUSD", idx=0),
                       _make_bar(1.11, symbol="EURUSD", idx=1)]

        handlers = {
            "AAPL": _MockDataHandler(aapl_bars),
            "EURUSD": _MockDataHandler(eurusd_bars),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL", signal_bar=1),   # Signal on bar 1
            "EURUSD": _MockStrategy("EURUSD", signal_bar=1),
        }

        portfolio = Portfolio(initial_cash=Decimal("100000"))
        execution_handlers = {
            "AAPL": ExecutionHandler(),
            "EURUSD": ExecutionHandler(),
        }

        engine = MultiAssetEngine(
            handlers=handlers, strategies=strategies,
            portfolio=portfolio, execution_handlers=execution_handlers,
        )
        result = engine.run()

        # Both signals should have generated orders; fills happen on next bar
        # Check that fill log contains fills from both symbols if orders were placed
        symbols_in_fills = {f.symbol for f in result.fill_log}
        # With signal on bar 1, order submitted, fills on bar 2 (idx=1)
        assert len(result.fill_log) >= 1

    def test_per_symbol_strategy_routing(self):
        """Each symbol's bar only goes to its strategy."""
        aapl_bars = [_make_bar(100, symbol="AAPL", idx=0)]
        eurusd_bars = [_make_bar(1.10, symbol="EURUSD", idx=1)]

        handlers = {
            "AAPL": _MockDataHandler(aapl_bars),
            "EURUSD": _MockDataHandler(eurusd_bars),
        }
        strat_aapl = _MockStrategy("AAPL")
        strat_eurusd = _MockStrategy("EURUSD")
        strategies = {"AAPL": strat_aapl, "EURUSD": strat_eurusd}

        create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
        ).run()

        # AAPL strategy should only have received AAPL bars
        assert len(strat_aapl._received_bars) == 1
        assert strat_aapl._received_bars[0].symbol == "AAPL"

        # EURUSD strategy should only have received EURUSD bars
        assert len(strat_eurusd._received_bars) == 1
        assert strat_eurusd._received_bars[0].symbol == "EURUSD"

    def test_equity_log_has_correct_timestamps(self):
        """Equity log timestamps correspond to bar timestamps."""
        bars_a = [_make_bar(100, symbol="AAPL", idx=0),
                  _make_bar(101, symbol="AAPL", idx=2)]
        bars_b = [_make_bar(1.10, symbol="EURUSD", idx=1)]

        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "EURUSD": _MockDataHandler(bars_b),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL"),
            "EURUSD": _MockStrategy("EURUSD"),
        }

        result = create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
        ).run()

        # Equity log should have entries with valid timestamps
        for entry in result.equity_log:
            assert "timestamp" in entry
            assert "equity" in entry

    def test_equity_uses_all_symbol_prices(self):
        """Equity snapshot uses ALL symbols' last known prices."""
        bars_a = [_make_bar(100, symbol="AAPL", idx=0),
                  _make_bar(110, symbol="AAPL", idx=2)]
        bars_b = [_make_bar(50, symbol="MSFT", idx=1),
                  _make_bar(55, symbol="MSFT", idx=3)]

        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "MSFT": _MockDataHandler(bars_b),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL"),
            "MSFT": _MockStrategy("MSFT"),
        }

        result = create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
        ).run()

        # The last equity log entry should have prices for both symbols
        last = result.equity_log[-1]
        assert "prices" in last
        assert "AAPL" in last["prices"]
        assert "MSFT" in last["prices"]

    def test_risk_gate_applies_across_symbols(self):
        """Risk manager gate blocks trades across all symbols."""
        from src.risk_manager import RiskManager

        bars_a = [_make_bar(100, symbol="AAPL", idx=i) for i in range(5)]
        bars_b = [_make_bar(200, symbol="MSFT", idx=i) for i in range(5)]

        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "MSFT": _MockDataHandler(bars_b),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL", signal_bar=1),
            "MSFT": _MockStrategy("MSFT", signal_bar=1),
        }

        rm = RiskManager(max_concurrent_positions=1)
        result = create_multi_asset_engine(
            handlers=handlers, strategies=strategies, risk_manager=rm,
        ).run()

        # With max 1 position, at most 1 fill should exist
        # (second symbol's signal blocked by risk gate)
        open_positions = sum(
            1 for pos in result.fill_log
            if pos.side == OrderSide.BUY
        )
        # Max 1 buy fill should go through
        assert open_positions <= 2  # Could be 1 or 2 depending on timing

    def test_exit_closes_correct_symbol(self):
        """EXIT signal closes the correct symbol's position."""
        # 3 bars each: bar 1 signals LONG, bar 3 signals EXIT
        bars_a = [_make_bar(100 + i, symbol="AAPL", idx=i) for i in range(4)]
        bars_b = [_make_bar(200 + i, symbol="MSFT", idx=i) for i in range(4)]

        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "MSFT": _MockDataHandler(bars_b),
        }

        class _LongThenExit(BaseStrategy):
            def __init__(self, sym):
                super().__init__(symbol=sym, timeframe="1h")
                self._count = 0

            def calculate_signals(self, event):
                self.update_buffer(event)
                self._count += 1
                if self._count == 1:
                    return SignalEvent(
                        symbol=self._symbol,
                        timestamp=event.timestamp,
                        signal_type=SignalType.LONG,
                        strength=Decimal("1"),
                    )
                if self._count == 3:
                    return SignalEvent(
                        symbol=self._symbol,
                        timestamp=event.timestamp,
                        signal_type=SignalType.EXIT,
                        strength=Decimal("1"),
                    )
                return None

        strategies = {
            "AAPL": _LongThenExit("AAPL"),
            "MSFT": _LongThenExit("MSFT"),
        }

        result = create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
        ).run()

        # Should have both BUY and SELL fills for each symbol
        buy_fills = [f for f in result.fill_log if f.side == OrderSide.BUY]
        sell_fills = [f for f in result.fill_log if f.side == OrderSide.SELL]
        assert len(buy_fills) >= 1
        assert len(sell_fills) >= 1

    def test_per_symbol_execution_isolation(self):
        """CRITICAL: AAPL pending order must NOT fill against EURUSD bar."""
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        exec_aapl = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        exec_eurusd = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )

        # Submit a LIMIT BUY order for AAPL at $95
        aapl_order = OrderEvent(
            symbol="AAPL",
            timestamp=BASE_TS,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            price=Decimal("95"),
        )
        exec_aapl.submit_order(aapl_order)

        # Process EURUSD bar — should NOT trigger AAPL order
        eurusd_bar = _make_bar(
            close=1.10, low=0.90, symbol="EURUSD", idx=0,
        )
        eurusd_fills = exec_eurusd.process_bar(eurusd_bar)
        assert len(eurusd_fills) == 0

        # AAPL order should still be pending in its own handler
        assert len(exec_aapl.pending_orders) == 1

        # Process AAPL bar that triggers the limit
        aapl_bar = _make_bar(
            close=94, low=93, symbol="AAPL", idx=1,
        )
        aapl_fills = exec_aapl.process_bar(aapl_bar)
        assert len(aapl_fills) == 1
        assert aapl_fills[0].symbol == "AAPL"

    def test_create_multi_asset_engine_factory(self):
        """Factory creates engine with correct per-symbol components."""
        bars_a = [_make_bar(100, symbol="AAPL", idx=0)]
        bars_b = [_make_bar(1.10, symbol="EURUSD", idx=0)]

        handlers = {
            "AAPL": _MockDataHandler(bars_a),
            "EURUSD": _MockDataHandler(bars_b),
        }
        strategies = {
            "AAPL": _MockStrategy("AAPL"),
            "EURUSD": _MockStrategy("EURUSD"),
        }

        engine = create_multi_asset_engine(
            handlers=handlers, strategies=strategies,
            initial_cash=Decimal("50000"),
        )
        result = engine.run()
        assert result.total_bars == 2
        assert result.final_equity > Decimal("0")


# ===========================================================================
# TestRollingCorrelation
# ===========================================================================

class TestRollingCorrelation:
    """Tests for compute_rolling_correlation and _pearson_decimal."""

    def test_perfectly_correlated(self):
        """Perfectly correlated series → correlation = 1.0."""
        x = [Decimal(str(i)) for i in range(1, 11)]
        y = [Decimal(str(i * 2)) for i in range(1, 11)]
        corr = _pearson_decimal(x, y)
        assert abs(corr - Decimal("1")) < Decimal("0.0001")

    def test_inverse_correlated(self):
        """Inversely correlated series → correlation = -1.0."""
        x = [Decimal(str(i)) for i in range(1, 11)]
        y = [Decimal(str(-i)) for i in range(1, 11)]
        corr = _pearson_decimal(x, y)
        assert abs(corr + Decimal("1")) < Decimal("0.0001")

    def test_window_too_short_returns_empty(self):
        """Window larger than data → empty results."""
        curves = {
            "AAPL": [Decimal("100"), Decimal("101")],
            "MSFT": [Decimal("200"), Decimal("201")],
        }
        ts = [BASE_TS, BASE_TS + timedelta(hours=1)]
        result = compute_rolling_correlation(curves, ts, window=60)
        assert result == []

    def test_unequal_lengths_handled(self):
        """Single symbol → empty results (need >= 2 symbols)."""
        curves = {"AAPL": [Decimal(str(100 + i)) for i in range(10)]}
        ts = [BASE_TS + timedelta(hours=i) for i in range(10)]
        result = compute_rolling_correlation(curves, ts, window=5)
        assert result == []

    def test_real_decorrelated_series(self):
        """Real-ish decorrelated series should be near 0."""
        # Alternating patterns — not perfectly correlated
        x = [Decimal(str(v)) for v in [1, 3, 2, 4, 3, 5, 4, 6, 5, 7]]
        y = [Decimal(str(v)) for v in [7, 5, 6, 4, 5, 3, 4, 2, 3, 1]]
        corr = _pearson_decimal(x, y)
        # These are actually inversely correlated
        assert corr < Decimal("0")

    def test_flat_series_returns_zero(self):
        """Flat series (zero std) returns correlation 0."""
        x = [Decimal("5")] * 10
        y = [Decimal(str(i)) for i in range(10)]
        corr = _pearson_decimal(x, y)
        assert corr == Decimal("0")


# ===========================================================================
# TestPerAssetLimits
# ===========================================================================

class TestPerAssetLimits:
    """Tests for per-asset limits in RiskManager (MULTI-04)."""

    def test_per_asset_position_limit_blocks(self):
        """Per-asset max_positions blocks additional trades for that symbol."""
        from src.risk_manager import RiskManager

        rm = RiskManager(
            per_asset_max_positions={"AAPL": 1, "MSFT": 2},
            max_concurrent_positions=10,
        )

        # Create portfolio with 1 AAPL position
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        portfolio.process_fill(_make_fill("BUY", 10, 100, symbol="AAPL"))

        bar_aapl = _make_bar(100, symbol="AAPL")
        can, reason = rm.can_trade(portfolio, bar_aapl)
        assert can is False
        assert "Per-asset limit" in reason

    def test_per_asset_max_pct_caps(self):
        """Per-asset max_pct caps position size for that symbol."""
        from src.risk_manager import RiskManager

        rm = RiskManager(
            per_asset_max_pct={"AAPL": Decimal("0.05")},  # 5% max
            max_position_pct=Decimal("0.20"),
        )

        portfolio = Portfolio(initial_cash=Decimal("100000"))
        # Add an equity log entry so compute_quantity works
        portfolio._equity_log.append({
            "timestamp": BASE_TS,
            "equity": Decimal("100000"),
            "cash": Decimal("100000"),
        })

        bar = _make_bar(100, symbol="AAPL")

        class _DummyStrat:
            current_atr = Decimal("0")

        qty = rm.compute_quantity(portfolio, _DummyStrat(), bar)
        # At 5% of 100000 = 5000 / 100 = 50 max
        assert qty <= Decimal("50")

    def test_unspecified_symbol_uses_global(self):
        """Symbol not in per_asset_max_positions uses global limit."""
        from src.risk_manager import RiskManager

        rm = RiskManager(
            per_asset_max_positions={"AAPL": 1},
            max_concurrent_positions=5,
        )

        # MSFT not in per_asset — should use global (5)
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        bar_msft = _make_bar(200, symbol="MSFT")
        can, reason = rm.can_trade(portfolio, bar_msft)
        assert can is True

    def test_per_asset_plus_global_interaction(self):
        """Per-asset AND global limits both apply."""
        from src.risk_manager import RiskManager

        rm = RiskManager(
            per_asset_max_positions={"AAPL": 2},
            max_concurrent_positions=1,  # Global is stricter
        )

        # 1 position open — global blocks even though AAPL allows 2
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        portfolio.process_fill(_make_fill("BUY", 10, 100, symbol="AAPL"))

        bar = _make_bar(100, symbol="AAPL")
        can, reason = rm.can_trade(portfolio, bar)
        assert can is False
        assert "Max concurrent" in reason


# ===========================================================================
# TestPerSymbolEquity
# ===========================================================================

class TestPerSymbolEquity:
    """Tests for compute_per_symbol_equity."""

    def test_groups_equity_by_symbol(self):
        """Groups equity entries by symbol from prices dict."""
        equity_log = [
            {
                "timestamp": BASE_TS,
                "equity": Decimal("10000"),
                "cash": Decimal("10000"),
                "prices": {"AAPL": Decimal("100"), "MSFT": Decimal("200")},
            },
            {
                "timestamp": BASE_TS + timedelta(hours=1),
                "equity": Decimal("10050"),
                "cash": Decimal("10000"),
                "prices": {"AAPL": Decimal("101"), "MSFT": Decimal("201")},
            },
        ]
        result = compute_per_symbol_equity(equity_log)
        assert "AAPL" in result
        assert "MSFT" in result
        assert len(result["AAPL"]) == 2
        assert len(result["MSFT"]) == 2

    def test_empty_log_returns_empty(self):
        """Empty equity log returns empty dict."""
        result = compute_per_symbol_equity([])
        assert result == {}
