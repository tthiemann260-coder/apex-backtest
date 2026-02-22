"""Tests for Metrics — Sharpe, Sortino, MDD, Calmar, PnL, Trade Stats."""

from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal

from src.events import FillEvent, OrderSide
from src.metrics import (
    MetricsComputationError,
    MetricsResult,
    compute,
    _compute_max_drawdown,
    _compute_cagr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_equity_log(equities: list[str]) -> list[dict]:
    """Create a simple equity log from a list of equity values."""
    from datetime import timedelta
    base = datetime(2024, 1, 1, 10, 0)
    log = []
    for i, eq in enumerate(equities):
        log.append({
            "timestamp": base + timedelta(hours=i),
            "equity": Decimal(eq),
            "cash": Decimal(eq),
        })
    return log


def _make_equity_log_with_position(
    equities: list[str], cash_values: list[str],
) -> list[dict]:
    """Create equity log where cash != equity (position open)."""
    log = []
    for i, (eq, cash) in enumerate(zip(equities, cash_values)):
        log.append({
            "timestamp": datetime(2024, 1, 1 + i, 10, 0),
            "equity": Decimal(eq),
            "cash": Decimal(cash),
        })
    return log


def _make_fill(
    side: OrderSide,
    fill_price: str,
    quantity: str = "100",
    commission: str = "0",
    day: int = 1,
) -> FillEvent:
    return FillEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(fill_price),
        commission=Decimal(commission),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


# ===========================================================================
# TestPnLMetrics
# ===========================================================================

class TestPnLMetrics:
    """METR-01: Net PnL, Total Return %, CAGR."""

    def test_net_pnl_positive(self):
        """Positive PnL when equity increases."""
        log = _make_equity_log(["10000", "10500", "11000"])
        result = compute(log, [], initial_equity=Decimal("10000"))
        assert result.net_pnl == Decimal("1000")

    def test_net_pnl_negative(self):
        """Negative PnL when equity decreases."""
        log = _make_equity_log(["10000", "9500", "9000"])
        result = compute(log, [], initial_equity=Decimal("10000"))
        assert result.net_pnl == Decimal("-1000")

    def test_total_return_pct(self):
        """Total return percentage calculation."""
        log = _make_equity_log(["10000", "12000"])
        result = compute(log, [], initial_equity=Decimal("10000"))
        assert result.total_return_pct == Decimal("20")

    def test_cagr_2_year_run(self):
        """CAGR for 2-year run: $10000 → $14400 = 20% per year."""
        # 504 daily bars ≈ 2 years (252 * 2)
        equities = ["10000"] + ["14400"] * 503
        log = _make_equity_log(equities)
        result = compute(log, [], timeframe="1d", initial_equity=Decimal("10000"))
        # CAGR should be approximately 0.2 (20%)
        assert abs(result.cagr - Decimal("0.2")) < Decimal("0.01")


# ===========================================================================
# TestSharpeRatio
# ===========================================================================

class TestSharpeRatio:
    """METR-02: Sharpe Ratio with correct annualization."""

    def test_sharpe_returns_decimal(self):
        """Sharpe Ratio is Decimal."""
        log = _make_equity_log(["10000", "10100", "10200", "10300"])
        result = compute(log, [])
        assert isinstance(result.sharpe_ratio, Decimal)

    def test_sharpe_positive_for_uptrend(self):
        """Positive Sharpe for consistent uptrend."""
        equities = [str(10000 + i * 10) for i in range(100)]
        log = _make_equity_log(equities)
        result = compute(log, [])
        assert result.sharpe_ratio > Decimal("0")

    def test_sharpe_zero_for_flat(self):
        """Zero Sharpe for flat equity curve."""
        log = _make_equity_log(["10000"] * 20)
        result = compute(log, [])
        assert result.sharpe_ratio == Decimal("0")


# ===========================================================================
# TestSortinoRatio
# ===========================================================================

class TestSortinoRatio:
    """METR-03: Sortino Ratio."""

    def test_sortino_returns_decimal(self):
        """Sortino Ratio is Decimal."""
        equities = [str(10000 + i * 10 - (5 if i % 3 == 0 else 0)) for i in range(50)]
        log = _make_equity_log(equities)
        result = compute(log, [])
        assert isinstance(result.sortino_ratio, Decimal)


# ===========================================================================
# TestMaxDrawdown
# ===========================================================================

class TestMaxDrawdown:
    """METR-04: Maximum Drawdown."""

    def test_max_drawdown_10_bar_sequence(self):
        """Hand-computed 10-bar equity sequence drawdown."""
        # Peak at 110, trough at 90, DD = 20 (18.18%)
        equities = [
            Decimal("100"), Decimal("105"), Decimal("110"),
            Decimal("100"), Decimal("95"), Decimal("90"),
            Decimal("92"), Decimal("98"), Decimal("105"),
            Decimal("108"),
        ]
        max_dd, max_dd_pct, duration = _compute_max_drawdown(equities)
        assert max_dd == Decimal("20")
        # 20/110 * 100 ≈ 18.18%
        assert max_dd_pct > Decimal("18")
        assert max_dd_pct < Decimal("19")

    def test_drawdown_duration(self):
        """Drawdown duration counted in bars."""
        equities = [
            Decimal("100"), Decimal("110"), Decimal("105"),
            Decimal("100"), Decimal("95"), Decimal("110"),
        ]
        _, _, duration = _compute_max_drawdown(equities)
        # Duration: bars 2→4 = 3 bars underwater
        assert duration >= 3

    def test_no_drawdown_monotonic_up(self):
        """Zero drawdown for monotonically increasing equity."""
        equities = [Decimal(str(100 + i)) for i in range(10)]
        max_dd, max_dd_pct, _ = _compute_max_drawdown(equities)
        assert max_dd == Decimal("0")


# ===========================================================================
# TestCalmarRatio
# ===========================================================================

class TestCalmarRatio:
    """METR-05: Calmar Ratio = CAGR / Max Drawdown %."""

    def test_calmar_returns_decimal(self):
        """Calmar Ratio is Decimal."""
        equities = [str(10000 + i * 10 - (50 if i == 5 else 0)) for i in range(50)]
        log = _make_equity_log(equities)
        result = compute(log, [])
        assert isinstance(result.calmar_ratio, Decimal)


# ===========================================================================
# TestTradeStats
# ===========================================================================

class TestTradeStats:
    """METR-06, METR-07: Trade statistics."""

    def test_win_rate_all_winners(self):
        """100% win rate when all trades profitable."""
        fills = [
            _make_fill(OrderSide.BUY, "50.00", day=1),
            _make_fill(OrderSide.SELL, "55.00", day=2),
            _make_fill(OrderSide.BUY, "53.00", day=3),
            _make_fill(OrderSide.SELL, "58.00", day=4),
        ]
        log = _make_equity_log(["10000", "10500", "10400", "10900"])
        result = compute(log, fills)
        assert result.win_rate == Decimal("100")

    def test_trade_count(self):
        """Trade count matches paired fills."""
        fills = [
            _make_fill(OrderSide.BUY, "50.00", day=1),
            _make_fill(OrderSide.SELL, "55.00", day=2),
        ]
        log = _make_equity_log(["10000", "10500"])
        result = compute(log, fills)
        assert result.trade_count == 1

    def test_no_trades_zero_stats(self):
        """Zero stats when no trades."""
        log = _make_equity_log(["10000", "10000"])
        result = compute(log, [])
        assert result.trade_count == 0
        assert result.win_rate == Decimal("0")


# ===========================================================================
# TestExposure
# ===========================================================================

class TestExposure:
    """METR-08: Total Exposure Time."""

    def test_zero_exposure_no_positions(self):
        """0% exposure when never in the market."""
        log = _make_equity_log(["10000"] * 10)
        result = compute(log, [])
        assert result.total_exposure_pct == Decimal("0")

    def test_partial_exposure(self):
        """Partial exposure when position held for some bars."""
        equities = ["10000", "10000", "10100", "10200", "10000"]
        cash = ["10000", "10000", "5000", "5000", "10000"]
        log = _make_equity_log_with_position(equities, cash)
        result = compute(log, [])
        # 2 out of 5 bars in market = 40%
        assert result.total_exposure_pct == Decimal("40")


# ===========================================================================
# TestMetricsResult
# ===========================================================================

class TestMetricsResult:
    """MetricsResult dataclass integrity."""

    def test_all_fields_populated(self):
        """All MetricsResult fields are populated."""
        log = _make_equity_log(["10000", "10100", "10200"])
        result = compute(log, [])
        assert result.net_pnl is not None
        assert result.sharpe_ratio is not None
        assert result.max_drawdown is not None
        assert result.win_rate is not None

    def test_empty_equity_log_raises(self):
        """Empty equity log raises MetricsComputationError."""
        with pytest.raises(MetricsComputationError):
            compute([], [])

    def test_result_is_metrics_result(self):
        """compute() returns MetricsResult."""
        log = _make_equity_log(["10000", "10100"])
        result = compute(log, [])
        assert isinstance(result, MetricsResult)
