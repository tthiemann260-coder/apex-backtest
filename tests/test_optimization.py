"""
test_optimization.py — Tests for the optimization engine (Phase 11).

Tests cover:
- Walk-Forward Validation (OPT-01)
- Parameter Sensitivity Analysis (OPT-02)
- Monte Carlo Trade Shuffling (OPT-03)
- Robustness Report (OPT-04)
- No state leakage between WFO windows (TEST-11)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from src.events import MarketEvent, FillEvent, OrderSide
from src.optimization.walk_forward import (
    WFOResult, WFOWindow, _BarSliceHandler,
    run_walk_forward,
)
from src.optimization.sensitivity import (
    SensitivityResult, SensitivityPoint,
    run_sensitivity_analysis,
)
from src.optimization.monte_carlo import (
    MCResult, MCPermutation,
    run_monte_carlo,
    _pair_fills_to_pnls,
    _simulate_equity_curve,
)
from src.optimization.robustness import (
    RobustnessReport,
    compute_robustness,
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


def make_fill(
    idx: int,
    side: OrderSide,
    price: str,
    qty: str = "10",
    commission: str = "1",
) -> FillEvent:
    return FillEvent(
        symbol="TEST",
        timestamp=BASE_TS + timedelta(days=idx),
        side=side,
        quantity=Decimal(qty),
        fill_price=Decimal(price),
        commission=Decimal(commission),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


def make_bars(n: int, base: float = 100.0, trend: float = 0.1) -> list[MarketEvent]:
    """Generate n bars with gentle uptrend."""
    bars = []
    for i in range(n):
        price = base + i * trend
        bars.append(make_bar(i, f"{price:.2f}"))
    return bars


# ===========================================================================
# BarSliceHandler Tests
# ===========================================================================


class TestBarSliceHandler:

    def test_streams_all_bars(self):
        bars = make_bars(5)
        handler = _BarSliceHandler(bars, "TEST", "1d")
        streamed = list(handler.stream_bars())
        assert len(streamed) == 5
        assert handler.symbol == "TEST"
        assert handler.timeframe == "1d"

    def test_empty_slice(self):
        handler = _BarSliceHandler([], "TEST", "1d")
        assert list(handler.stream_bars()) == []


# ===========================================================================
# Monte Carlo Tests
# ===========================================================================


class TestPairFillsToPnls:

    def test_basic_round_trip(self):
        fills = [
            make_fill(0, OrderSide.BUY, "100"),
            make_fill(1, OrderSide.SELL, "110"),
        ]
        pnls, equity = _pair_fills_to_pnls(fills, Decimal("10000"))
        assert len(pnls) == 1
        # PnL = (110 - 100) * 10 - 2 (commissions) = 98
        assert pnls[0] == Decimal("98")
        assert equity == Decimal("10098")

    def test_short_round_trip(self):
        fills = [
            make_fill(0, OrderSide.SELL, "110"),
            make_fill(1, OrderSide.BUY, "100"),
        ]
        pnls, equity = _pair_fills_to_pnls(fills, Decimal("10000"))
        assert len(pnls) == 1
        # PnL = (110 - 100) * 10 - 2 = 98
        assert pnls[0] == Decimal("98")

    def test_multiple_trades(self):
        fills = [
            make_fill(0, OrderSide.BUY, "100"),
            make_fill(1, OrderSide.SELL, "105"),
            make_fill(2, OrderSide.BUY, "103"),
            make_fill(3, OrderSide.SELL, "108"),
        ]
        pnls, _ = _pair_fills_to_pnls(fills, Decimal("10000"))
        assert len(pnls) == 2

    def test_empty_fills(self):
        pnls, equity = _pair_fills_to_pnls([], Decimal("10000"))
        assert pnls == []
        assert equity == Decimal("10000")

    def test_unpaired_fill(self):
        fills = [make_fill(0, OrderSide.BUY, "100")]
        pnls, _ = _pair_fills_to_pnls(fills, Decimal("10000"))
        assert len(pnls) == 0


class TestSimulateEquityCurve:

    def test_basic_equity(self):
        final, max_dd = _simulate_equity_curve([100.0, -50.0, 200.0], 10000.0)
        assert final == 10250.0

    def test_drawdown_calculation(self):
        # Equity: 10000 → 10100 → 9900 → 10200
        # Peak at 10100, DD = (10100-9900)/10100 ≈ 1.98%
        final, max_dd = _simulate_equity_curve([100.0, -200.0, 300.0], 10000.0)
        assert max_dd > 0
        assert final == 10200.0

    def test_no_drawdown(self):
        final, max_dd = _simulate_equity_curve([100.0, 100.0, 100.0], 10000.0)
        assert max_dd == 0.0
        assert final == 10300.0


class TestRunMonteCarlo:

    def test_basic_mc(self):
        fills = [
            make_fill(0, OrderSide.BUY, "100"),
            make_fill(1, OrderSide.SELL, "110"),
            make_fill(2, OrderSide.BUY, "105"),
            make_fill(3, OrderSide.SELL, "115"),
        ]
        result = run_monte_carlo(fills, n_permutations=100, seed=42)
        assert result.n_permutations == 100
        assert result.n_trades == 2
        assert result.original_final_equity > 0
        assert result.p5_equity <= result.p95_equity
        assert 0 <= result.equity_percentile <= 100

    def test_single_trade(self):
        fills = [
            make_fill(0, OrderSide.BUY, "100"),
            make_fill(1, OrderSide.SELL, "110"),
        ]
        result = run_monte_carlo(fills, n_permutations=100)
        assert result.n_permutations == 0  # Not enough trades
        assert result.n_trades == 1

    def test_empty_fills(self):
        result = run_monte_carlo([], n_permutations=100)
        assert result.n_trades == 0
        assert result.n_permutations == 0

    def test_reproducible_with_seed(self):
        fills = [
            make_fill(0, OrderSide.BUY, "100"),
            make_fill(1, OrderSide.SELL, "110"),
            make_fill(2, OrderSide.BUY, "105"),
            make_fill(3, OrderSide.SELL, "115"),
            make_fill(4, OrderSide.BUY, "108"),
            make_fill(5, OrderSide.SELL, "120"),
        ]
        r1 = run_monte_carlo(fills, n_permutations=50, seed=123)
        r2 = run_monte_carlo(fills, n_permutations=50, seed=123)
        assert r1.p5_equity == r2.p5_equity
        assert r1.p95_equity == r2.p95_equity


# ===========================================================================
# Sensitivity Tests
# ===========================================================================


class TestSensitivity:

    def test_basic_sensitivity(self):
        """Test with mocked engine to avoid data loading."""
        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
            {"timestamp": BASE_TS + timedelta(days=1), "equity": Decimal("10100"), "cash": Decimal("10100")},
        ]
        mock_result.fill_log = []

        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.sensitivity.DataHandler"), \
             patch("src.optimization.sensitivity.create_engine", return_value=mock_engine), \
             patch("src.optimization.sensitivity._import_strategy_class") as mock_cls:
            mock_cls.return_value = MagicMock()

            result = run_sensitivity_analysis(
                symbol="TEST",
                strategy_name="reversal",
                base_params={"sma_period": 20, "rsi_period": 14},
                perturbations=[-10.0, 0.0, 10.0],
            )

        assert isinstance(result, SensitivityResult)
        # 2 params × 3 perturbations = 6 points
        assert len(result.points) == 6
        assert "sma_period" in result.param_cv
        assert "rsi_period" in result.param_cv
        assert 0 <= result.overall_stability <= 1.0

    def test_empty_params(self):
        with patch("src.optimization.sensitivity._import_strategy_class"):
            result = run_sensitivity_analysis(
                symbol="TEST",
                strategy_name="reversal",
                base_params={},
            )
        assert len(result.points) == 0
        assert result.overall_stability == 0.0

    def test_non_numeric_params_skipped(self):
        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
        ]
        mock_result.fill_log = []
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.sensitivity.DataHandler"), \
             patch("src.optimization.sensitivity.create_engine", return_value=mock_engine), \
             patch("src.optimization.sensitivity._import_strategy_class") as mock_cls:
            mock_cls.return_value = MagicMock()

            result = run_sensitivity_analysis(
                symbol="TEST",
                strategy_name="reversal",
                base_params={"name": "test", "period": 20},
                perturbations=[0.0, 10.0],
            )
        # Only "period" is numeric
        assert len(result.points) == 2

    def test_zero_param_skipped(self):
        """Parameters with value 0 should be skipped (can't perturb 0)."""
        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
        ]
        mock_result.fill_log = []
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.sensitivity.DataHandler"), \
             patch("src.optimization.sensitivity.create_engine", return_value=mock_engine), \
             patch("src.optimization.sensitivity._import_strategy_class") as mock_cls:
            mock_cls.return_value = MagicMock()

            result = run_sensitivity_analysis(
                symbol="TEST",
                strategy_name="reversal",
                base_params={"zero_param": 0, "good_param": 10},
                perturbations=[0.0, 10.0],
            )
        # Only good_param is numeric and non-zero
        assert len(result.points) == 2


# ===========================================================================
# Walk-Forward Tests
# ===========================================================================


class TestWalkForward:

    def test_basic_wfo_with_mocks(self):
        """Test WFO with mocked data and engine."""
        bars = make_bars(100, base=100.0, trend=0.5)

        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
            {"timestamp": BASE_TS + timedelta(days=1), "equity": Decimal("10200"), "cash": Decimal("10200")},
        ]
        mock_result.fill_log = []

        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.walk_forward._load_all_bars", return_value=bars), \
             patch("src.optimization.walk_forward._import_strategy_class") as mock_cls, \
             patch("src.optimization.walk_forward.create_engine", return_value=mock_engine):
            mock_cls.return_value = MagicMock()

            result = run_walk_forward(
                symbol="TEST",
                strategy_name="reversal",
                train_bars=50,
                test_bars=20,
            )

        assert isinstance(result, WFOResult)
        assert len(result.windows) > 0
        assert result.total_oos_bars > 0

    def test_not_enough_bars(self):
        """Not enough bars for any window."""
        bars = make_bars(10)

        with patch("src.optimization.walk_forward._load_all_bars", return_value=bars), \
             patch("src.optimization.walk_forward._import_strategy_class"):
            result = run_walk_forward(
                symbol="TEST",
                strategy_name="reversal",
                train_bars=50,
                test_bars=20,
            )
        assert len(result.windows) == 0
        assert result.mean_oos_sharpe == 0.0

    def test_window_count(self):
        """Verify correct number of windows generated."""
        bars = make_bars(200)

        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
        ]
        mock_result.fill_log = []
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.walk_forward._load_all_bars", return_value=bars), \
             patch("src.optimization.walk_forward._import_strategy_class") as mock_cls, \
             patch("src.optimization.walk_forward.create_engine", return_value=mock_engine):
            mock_cls.return_value = MagicMock()

            result = run_walk_forward(
                symbol="TEST",
                strategy_name="reversal",
                train_bars=50,
                test_bars=25,
                step_bars=25,
            )

        # 200 bars, train=50, test=25, step=25
        # Window 0: train[0:50], test[50:75]
        # Window 1: train[25:75], test[75:100]
        # ...continues until can't fit
        expected_windows = (200 - 50 - 25) // 25 + 1
        assert len(result.windows) == expected_windows

    def test_no_state_leakage_between_windows(self):
        """TEST-11: Each window gets a fresh strategy instance."""
        bars = make_bars(200)
        strategy_instances = []

        original_cls = MagicMock()
        def track_instances(*args, **kwargs):
            instance = MagicMock()
            strategy_instances.append(instance)
            return instance
        original_cls.side_effect = track_instances

        mock_result = MagicMock()
        mock_result.equity_log = [
            {"timestamp": BASE_TS, "equity": Decimal("10000"), "cash": Decimal("10000")},
        ]
        mock_result.fill_log = []
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.optimization.walk_forward._load_all_bars", return_value=bars), \
             patch("src.optimization.walk_forward._import_strategy_class", return_value=original_cls), \
             patch("src.optimization.walk_forward.create_engine", return_value=mock_engine):

            result = run_walk_forward(
                symbol="TEST",
                strategy_name="reversal",
                train_bars=50,
                test_bars=25,
            )

        # Each window runs IS + OOS = 2 strategy instances per window
        n_windows = len(result.windows)
        assert len(strategy_instances) == n_windows * 2
        # All instances are distinct objects
        ids = [id(s) for s in strategy_instances]
        assert len(set(ids)) == len(ids)


# ===========================================================================
# Robustness Report Tests
# ===========================================================================


class TestRobustnessReport:

    def _make_wfo(self, efficiency: float = 0.8) -> WFOResult:
        return WFOResult(
            windows=[
                WFOWindow(0, 100, 25, 1.5, 1.2, 10.0, 8.0, efficiency),
                WFOWindow(1, 100, 25, 1.3, 1.0, 8.0, 6.0, efficiency),
            ],
            mean_oos_sharpe=1.1,
            mean_efficiency=efficiency,
            total_oos_bars=50,
        )

    def _make_mc(self, p5_equity: float = 10500.0) -> MCResult:
        return MCResult(
            n_permutations=100,
            n_trades=20,
            original_final_equity=11000.0,
            original_max_dd_pct=5.0,
            p5_equity=p5_equity,
            p50_equity=10800.0,
            p95_equity=11200.0,
            p5_max_dd=3.0,
            p50_max_dd=5.0,
            p95_max_dd=8.0,
            equity_percentile=75.0,
        )

    def _make_sensitivity(self, stability: float = 0.7) -> SensitivityResult:
        return SensitivityResult(
            points=[],
            param_cv={"param1": 0.1, "param2": 0.2},
            overall_stability=stability,
            baseline_sharpe=1.5,
        )

    def test_all_pass(self):
        report = compute_robustness(
            wfo=self._make_wfo(0.8),
            mc=self._make_mc(10500.0),
            sensitivity=self._make_sensitivity(0.7),
        )
        assert report.overall_pass is True
        assert report.wfo_pass is True
        assert report.mc_pass is True
        assert report.sensitivity_pass is True
        assert report.score > 0

    def test_wfo_fails(self):
        report = compute_robustness(
            wfo=self._make_wfo(0.3),
            mc=self._make_mc(10500.0),
            sensitivity=self._make_sensitivity(0.7),
        )
        assert report.wfo_pass is False
        assert report.overall_pass is False

    def test_mc_fails(self):
        report = compute_robustness(
            wfo=self._make_wfo(0.8),
            mc=self._make_mc(9000.0),  # Below initial equity
            sensitivity=self._make_sensitivity(0.7),
        )
        assert report.mc_pass is False
        assert report.overall_pass is False

    def test_sensitivity_fails(self):
        report = compute_robustness(
            wfo=self._make_wfo(0.8),
            mc=self._make_mc(10500.0),
            sensitivity=self._make_sensitivity(0.3),
        )
        assert report.sensitivity_pass is False
        assert report.overall_pass is False

    def test_score_range(self):
        report = compute_robustness(
            wfo=self._make_wfo(1.0),
            mc=self._make_mc(11000.0),
            sensitivity=self._make_sensitivity(1.0),
        )
        assert 0 <= report.score <= 100

    def test_empty_wfo(self):
        empty_wfo = WFOResult(windows=[], mean_oos_sharpe=0.0, mean_efficiency=0.0, total_oos_bars=0)
        report = compute_robustness(
            wfo=empty_wfo,
            mc=self._make_mc(10500.0),
            sensitivity=self._make_sensitivity(0.7),
        )
        assert report.wfo_pass is False

    def test_few_mc_trades(self):
        few_trades = MCResult(
            n_permutations=0, n_trades=1,
            original_final_equity=10100.0, original_max_dd_pct=0.0,
            p5_equity=10100.0, p50_equity=10100.0, p95_equity=10100.0,
        )
        report = compute_robustness(
            wfo=self._make_wfo(0.8),
            mc=few_trades,
            sensitivity=self._make_sensitivity(0.7),
        )
        assert report.mc_pass is False


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestOptimizationImports:

    def test_all_modules_importable(self):
        import src.optimization
        import src.optimization.walk_forward
        import src.optimization.sensitivity
        import src.optimization.monte_carlo
        import src.optimization.robustness
