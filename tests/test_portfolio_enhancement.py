"""
test_portfolio_enhancement.py — Tests for Phase 12 (Portfolio Enhancement).

Covers:
- PortfolioRouter: multi-strategy routing, weighted sizing, attribution
- Benchmark: buy-and-hold equity curve, Alpha/Beta/IR calculation
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from src.events import (
    MarketEvent, SignalEvent, FillEvent,
    SignalType, OrderSide, OrderType,
)
from src.portfolio_router import (
    PortfolioRouter,
    StrategyAttribution,
    MultiStrategyResult,
)
from src.benchmark import (
    compute_benchmark_equity,
    compute_benchmark_metrics,
    BenchmarkMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 1, 9, 30)


def make_bar(idx: int, close: str, vol: int = 1000) -> MarketEvent:
    return MarketEvent(
        symbol="TEST",
        timestamp=BASE_TS + timedelta(days=idx),
        open=Decimal(close),
        high=Decimal(str(float(close) + 1)),
        low=Decimal(str(float(close) - 1)),
        close=Decimal(close),
        volume=vol,
        timeframe="1d",
    )


def make_bars(n: int, base: float = 100.0, trend: float = 0.5) -> list[MarketEvent]:
    bars = []
    for i in range(n):
        price = base + i * trend
        bars.append(make_bar(i, f"{price:.2f}"))
    return bars


# ===========================================================================
# PortfolioRouter Tests
# ===========================================================================


class TestPortfolioRouter:

    def test_basic_multi_strategy(self):
        """Two strategies generate signals on shared portfolio."""
        bars = make_bars(20)

        # Mock strategies
        strat_a = MagicMock()
        strat_a.calculate_signals.return_value = None

        strat_b = MagicMock()
        strat_b.calculate_signals.return_value = None

        # Mock data handler
        mock_dh = MagicMock()
        mock_dh.stream_bars.return_value = iter(bars)

        router = PortfolioRouter(
            strategies={"strat_a": strat_a, "strat_b": strat_b},
            weights={"strat_a": 0.5, "strat_b": 0.5},
            data_handler=mock_dh,
        )
        result = router.run()

        assert isinstance(result, MultiStrategyResult)
        assert result.total_bars == 20
        assert "strat_a" in result.attributions
        assert "strat_b" in result.attributions

    def test_weighted_sizing(self):
        """Weight affects position size calculation."""
        bar = make_bar(0, "100")

        mock_dh = MagicMock()
        mock_dh.stream_bars.return_value = iter([])

        router = PortfolioRouter(
            strategies={"a": MagicMock()},
            weights={"a": 0.5},
            data_handler=mock_dh,
        )

        # Full weight = 10% of equity / price
        # 50% weight = 5% of equity / price
        # 10000 * 0.5 * 0.10 / 100 = 5 shares
        qty = router._calculate_weighted_quantity(bar, Decimal("0.5"))
        assert qty == Decimal("5")

    def test_attribution_tracking(self):
        """Strategy attribution correctly counts signals."""
        bars = make_bars(5)

        signal = SignalEvent(
            symbol="TEST",
            timestamp=BASE_TS,
            signal_type=SignalType.LONG,
            strength=Decimal("0.8"),
        )

        strat_a = MagicMock()
        strat_a.calculate_signals.side_effect = [signal, None, None, None, None]

        mock_dh = MagicMock()
        mock_dh.stream_bars.return_value = iter(bars)

        router = PortfolioRouter(
            strategies={"strat_a": strat_a},
            weights={"strat_a": 1.0},
            data_handler=mock_dh,
        )
        result = router.run()

        assert result.attributions["strat_a"].signal_count == 1

    def test_compute_strategy_pnl(self):
        """PnL computation from attributed fills."""
        fills = [
            FillEvent("TEST", BASE_TS, OrderSide.BUY, Decimal("10"),
                      Decimal("100"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=1), OrderSide.SELL, Decimal("10"),
                      Decimal("110"), Decimal("1"), Decimal("0"), Decimal("0")),
        ]
        pnl = PortfolioRouter._compute_strategy_pnl(fills)
        # (110 - 100) * 10 - 2 = 98
        assert pnl == Decimal("98")

    def test_empty_fills_pnl(self):
        pnl = PortfolioRouter._compute_strategy_pnl([])
        assert pnl == Decimal("0")

    def test_zero_weight(self):
        """Zero weight produces zero quantity."""
        bar = make_bar(0, "100")
        mock_dh = MagicMock()
        mock_dh.stream_bars.return_value = iter([])
        router = PortfolioRouter(
            strategies={"a": MagicMock()},
            weights={"a": 0.0},
            data_handler=mock_dh,
        )
        qty = router._calculate_weighted_quantity(bar, Decimal("0"))
        assert qty == Decimal("0")

    def test_zero_price_bar(self):
        """Zero price bar produces zero quantity."""
        bar = make_bar(0, "0")
        mock_dh = MagicMock()
        mock_dh.stream_bars.return_value = iter([])
        router = PortfolioRouter(
            strategies={"a": MagicMock()},
            weights={"a": 1.0},
            data_handler=mock_dh,
        )
        qty = router._calculate_weighted_quantity(bar, Decimal("1"))
        assert qty == Decimal("0")


# ===========================================================================
# Benchmark Tests
# ===========================================================================


class TestBenchmarkEquity:

    def test_buy_and_hold_flat(self):
        """Flat price → equity stays constant."""
        bars = [make_bar(i, "100") for i in range(10)]
        equity = compute_benchmark_equity(bars)
        assert len(equity) == 10
        assert equity[0]["equity"] == Decimal("10000")
        assert equity[-1]["equity"] == Decimal("10000")

    def test_buy_and_hold_uptrend(self):
        """Price doubles → equity doubles."""
        bars = [make_bar(0, "100"), make_bar(1, "200")]
        equity = compute_benchmark_equity(bars)
        assert float(equity[-1]["equity"]) == pytest.approx(20000.0, rel=1e-6)

    def test_empty_bars(self):
        assert compute_benchmark_equity([]) == []

    def test_zero_price_bar(self):
        bars = [make_bar(0, "0")]
        assert compute_benchmark_equity(bars) == []

    def test_custom_initial_equity(self):
        bars = [make_bar(0, "100"), make_bar(1, "110")]
        equity = compute_benchmark_equity(bars, Decimal("50000"))
        # 50000 / 100 = 500 shares × 110 = 55000
        assert float(equity[-1]["equity"]) == pytest.approx(55000.0, rel=1e-6)


class TestBenchmarkMetrics:

    def _make_equity_log(self, equities: list[float]) -> list[dict]:
        return [
            {"timestamp": BASE_TS + timedelta(days=i), "equity": Decimal(str(e))}
            for i, e in enumerate(equities)
        ]

    def test_identical_curves(self):
        """Strategy = Benchmark → alpha=0, beta=1, correlation=1."""
        equities = [10000, 10100, 10200, 10300, 10400, 10500]
        strat = self._make_equity_log(equities)
        bench = self._make_equity_log(equities)

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.beta == pytest.approx(1.0, abs=0.01)
        assert metrics.correlation == pytest.approx(1.0, abs=0.01)
        assert abs(metrics.alpha) < 0.1

    def test_strategy_outperforms(self):
        """Strategy grows faster → positive alpha."""
        strat = self._make_equity_log([10000, 10200, 10500, 10900, 11400])
        bench = self._make_equity_log([10000, 10050, 10100, 10150, 10200])

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.strategy_return_pct > metrics.benchmark_return_pct
        assert metrics.alpha > 0

    def test_short_series(self):
        """With < 2 bars, returns zeros."""
        strat = self._make_equity_log([10000])
        bench = self._make_equity_log([10000])

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.alpha == 0.0
        assert metrics.beta == 0.0

    def test_empty_logs(self):
        metrics = compute_benchmark_metrics([], [])
        assert metrics.alpha == 0.0
        assert metrics.benchmark_return_pct == 0.0

    def test_negative_beta(self):
        """Strategy moves opposite to benchmark → negative beta."""
        strat = self._make_equity_log([10000, 10200, 10000, 10200, 10000])
        bench = self._make_equity_log([10000, 9800, 10000, 9800, 10000])

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.beta < 0

    def test_information_ratio_sign(self):
        """Outperforming strategy has positive IR."""
        strat = self._make_equity_log([10000, 10200, 10400, 10600, 10800])
        bench = self._make_equity_log([10000, 10050, 10100, 10150, 10200])

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.information_ratio > 0

    def test_returns_pct(self):
        """Total return percentages are correct."""
        strat = self._make_equity_log([10000, 11000])
        bench = self._make_equity_log([10000, 10500])

        metrics = compute_benchmark_metrics(strat, bench)
        assert metrics.strategy_return_pct == pytest.approx(10.0, rel=0.01)
        assert metrics.benchmark_return_pct == pytest.approx(5.0, rel=0.01)


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestPortfolioEnhancementImports:

    def test_all_modules_importable(self):
        import src.portfolio_router
        import src.benchmark
