"""
test_analytics.py — Tests for Phase 9 Advanced Analytics.

Tests cover:
- ADV-01: Monthly Returns Heatmap computation
- ADV-02: Rolling Sharpe Ratio
- ADV-03: Rolling Drawdown
- ADV-04: Trade Breakdown by Hour
- ADV-05: Trade Breakdown by Weekday
- ADV-06: Trade Breakdown by Session
- ADV-07: MAE (Max Adverse Excursion)
- ADV-08: MFE (Max Favorable Excursion)
- ADV-09: Commission Sensitivity Sweep (structure only, no network)
- Chart builder functions
- Serialization/deserialization
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from src.analytics import (
    compute_monthly_returns,
    compute_rolling_sharpe,
    compute_rolling_drawdown,
    compute_trade_breakdown,
    compute_mae_mfe,
    _pair_fills_to_trades,
    _get_session,
)
from src.events import FillEvent, OrderSide


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_equity_log(
    start: datetime,
    equities: list,
    freq_days: int = 1,
) -> list[dict]:
    """Build an equity_log from a list of equity values."""
    log = []
    for i, eq in enumerate(equities):
        ts = start + timedelta(days=i * freq_days)
        log.append({
            "timestamp": ts,
            "equity": Decimal(str(eq)),
            "cash": Decimal(str(eq)),
            "price": Decimal(str(100 + i)),
        })
    return log


def _make_fill(
    symbol: str,
    timestamp: datetime,
    side: OrderSide,
    quantity: float,
    fill_price: float,
    commission: float = 1.0,
) -> FillEvent:
    """Helper to create a FillEvent."""
    return FillEvent(
        symbol=symbol,
        timestamp=timestamp,
        side=side,
        quantity=Decimal(str(quantity)),
        fill_price=Decimal(str(fill_price)),
        commission=Decimal(str(commission)),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


# ---------------------------------------------------------------------------
# ADV-01: Monthly Returns
# ---------------------------------------------------------------------------

class TestMonthlyReturns:
    def test_basic_monthly_returns(self):
        """Monthly returns correctly computed across months."""
        log = [
            {"timestamp": datetime(2024, 1, 31), "equity": Decimal("10000")},
            {"timestamp": datetime(2024, 2, 28), "equity": Decimal("10500")},
            {"timestamp": datetime(2024, 3, 31), "equity": Decimal("10200")},
        ]
        result = compute_monthly_returns(log)
        assert 2024 in result
        # Feb return: (10500-10000)/10000 * 100 = 5.0
        assert result[2024][2] == Decimal("5.0") * Decimal("100") / Decimal("100")
        feb_ret = (Decimal("10500") - Decimal("10000")) / Decimal("10000") * Decimal("100")
        assert result[2024][2] == feb_ret
        # Mar return: (10200-10500)/10500 * 100 = -2.857...
        mar_ret = (Decimal("10200") - Decimal("10500")) / Decimal("10500") * Decimal("100")
        assert result[2024][3] == mar_ret

    def test_empty_log_returns_empty(self):
        assert compute_monthly_returns([]) == {}

    def test_single_entry_returns_empty(self):
        log = [{"timestamp": datetime(2024, 1, 15), "equity": Decimal("10000")}]
        assert compute_monthly_returns(log) == {}

    def test_multi_year_returns(self):
        """Returns span across years correctly."""
        log = [
            {"timestamp": datetime(2023, 12, 31), "equity": Decimal("10000")},
            {"timestamp": datetime(2024, 1, 31), "equity": Decimal("10100")},
            {"timestamp": datetime(2024, 2, 28), "equity": Decimal("10300")},
        ]
        result = compute_monthly_returns(log)
        assert 2024 in result
        assert 1 in result[2024]
        assert 2 in result[2024]

    def test_multiple_entries_per_month_uses_last(self):
        """Only the last entry per month is used."""
        log = [
            {"timestamp": datetime(2024, 1, 10), "equity": Decimal("10000")},
            {"timestamp": datetime(2024, 1, 20), "equity": Decimal("10050")},
            {"timestamp": datetime(2024, 1, 31), "equity": Decimal("10100")},
            {"timestamp": datetime(2024, 2, 28), "equity": Decimal("10200")},
        ]
        result = compute_monthly_returns(log)
        # Should use 10100 (Jan last) and 10200 (Feb last)
        expected = (Decimal("10200") - Decimal("10100")) / Decimal("10100") * Decimal("100")
        assert result[2024][2] == expected

    def test_same_month_entries_returns_empty(self):
        """All entries in same month → only 1 sorted key → returns empty."""
        log = [
            {"timestamp": datetime(2024, 1, 5), "equity": Decimal("10000")},
            {"timestamp": datetime(2024, 1, 15), "equity": Decimal("10100")},
            {"timestamp": datetime(2024, 1, 25), "equity": Decimal("10200")},
        ]
        result = compute_monthly_returns(log)
        assert result == {}

    def test_zero_equity_prev_month(self):
        """Zero equity in previous month → return = 0 (no division by zero)."""
        log = [
            {"timestamp": datetime(2024, 1, 31), "equity": Decimal("0")},
            {"timestamp": datetime(2024, 2, 28), "equity": Decimal("10000")},
        ]
        result = compute_monthly_returns(log)
        assert result[2024][2] == Decimal("0")


# ---------------------------------------------------------------------------
# ADV-02: Rolling Sharpe
# ---------------------------------------------------------------------------

class TestRollingSharpe:
    def test_basic_rolling_sharpe(self):
        """Rolling Sharpe computed with correct window size."""
        start = datetime(2024, 1, 1)
        # 25 bars → 24 returns → window=20 → 5 output points
        equities = [10000 + i * 10 for i in range(25)]
        log = _make_equity_log(start, equities)

        result = compute_rolling_sharpe(log, window=20, timeframe="1d")
        assert len(result) == 5  # 24 returns - 20 + 1 = 5
        assert "timestamp" in result[0]
        assert "rolling_sharpe" in result[0]

    def test_too_few_bars_returns_empty(self):
        start = datetime(2024, 1, 1)
        equities = [10000 + i * 10 for i in range(10)]
        log = _make_equity_log(start, equities)

        result = compute_rolling_sharpe(log, window=20)
        assert result == []

    def test_constant_equity_returns_zero_sharpe(self):
        """Flat equity → zero std → sharpe=0."""
        start = datetime(2024, 1, 1)
        equities = [10000] * 25
        log = _make_equity_log(start, equities)

        result = compute_rolling_sharpe(log, window=20)
        for point in result:
            assert point["rolling_sharpe"] == 0.0

    def test_positive_returns_positive_sharpe(self):
        """Consistently rising equity → positive Sharpe."""
        start = datetime(2024, 1, 1)
        equities = [10000 + i * 50 for i in range(25)]
        log = _make_equity_log(start, equities)

        result = compute_rolling_sharpe(log, window=20)
        assert all(point["rolling_sharpe"] > 0 for point in result)

    def test_zero_equity_in_series(self):
        """Zero equity → return = 0.0 (no crash)."""
        start = datetime(2024, 1, 1)
        equities = [10000] * 10 + [0] + [10000] * 14
        log = _make_equity_log(start, equities)

        result = compute_rolling_sharpe(log, window=20)
        assert len(result) > 0  # Should not crash


# ---------------------------------------------------------------------------
# ADV-03: Rolling Drawdown
# ---------------------------------------------------------------------------

class TestRollingDrawdown:
    def test_basic_rolling_drawdown(self):
        """Rolling drawdown computed with correct window size."""
        start = datetime(2024, 1, 1)
        equities = [10000, 10100, 10050, 10200, 10150, 10300, 10250,
                     10400, 10350, 10500, 10000, 10100, 10200, 10300,
                     10400, 10500, 10600, 10700, 10800, 10900, 11000]
        log = _make_equity_log(start, equities)

        result = compute_rolling_drawdown(log, window=10)
        assert len(result) == 12  # 21 - 10 + 1
        assert "timestamp" in result[0]
        assert "rolling_drawdown_pct" in result[0]

    def test_rising_equity_zero_drawdown(self):
        """Monotonically rising equity → drawdown = 0."""
        start = datetime(2024, 1, 1)
        equities = [10000 + i * 100 for i in range(15)]
        log = _make_equity_log(start, equities)

        result = compute_rolling_drawdown(log, window=10)
        for point in result:
            assert point["rolling_drawdown_pct"] == 0.0

    def test_drawdown_is_negative(self):
        """Drawdowns are expressed as negative percentages."""
        start = datetime(2024, 1, 1)
        # Goes up then down significantly
        equities = [10000, 11000, 12000, 10000, 9000, 8000,
                     7000, 6000, 7000, 8000, 9000]
        log = _make_equity_log(start, equities)

        result = compute_rolling_drawdown(log, window=5)
        # At least one should be negative
        min_dd = min(p["rolling_drawdown_pct"] for p in result)
        assert min_dd < 0

    def test_too_few_bars_returns_empty(self):
        start = datetime(2024, 1, 1)
        equities = [10000, 10100, 10200]
        log = _make_equity_log(start, equities)

        result = compute_rolling_drawdown(log, window=10)
        assert result == []


# ---------------------------------------------------------------------------
# ADV-04/05/06: Trade Breakdown
# ---------------------------------------------------------------------------

class TestTradeBreakdown:
    def _make_trade_fills(self):
        """Create fills that form complete trades at different times."""
        fills = [
            # Trade 1: Mon 10am, win
            _make_fill("AAPL", datetime(2024, 1, 1, 10, 0), OrderSide.BUY, 10, 100),
            _make_fill("AAPL", datetime(2024, 1, 1, 14, 0), OrderSide.SELL, 10, 105),
            # Trade 2: Wed 15pm, loss
            _make_fill("AAPL", datetime(2024, 1, 3, 15, 0), OrderSide.BUY, 10, 110),
            _make_fill("AAPL", datetime(2024, 1, 3, 16, 0), OrderSide.SELL, 10, 108),
            # Trade 3: Fri 9am, win
            _make_fill("AAPL", datetime(2024, 1, 5, 9, 0), OrderSide.BUY, 10, 95),
            _make_fill("AAPL", datetime(2024, 1, 5, 11, 0), OrderSide.SELL, 10, 100),
        ]
        return fills

    def test_breakdown_by_hour(self):
        """Trade breakdown by hour counts correctly."""
        fills = self._make_trade_fills()
        result = compute_trade_breakdown(fills)

        by_hour = result["by_hour"]
        assert len(by_hour) >= 1
        hours = {h["hour"] for h in by_hour}
        assert 10 in hours  # Trade 1 entry hour

    def test_breakdown_by_weekday(self):
        """Trade breakdown by weekday has correct day names."""
        fills = self._make_trade_fills()
        result = compute_trade_breakdown(fills)

        by_weekday = result["by_weekday"]
        assert len(by_weekday) >= 1
        names = {d["weekday_name"] for d in by_weekday}
        # 2024-01-01 is Monday, 2024-01-03 is Wednesday, 2024-01-05 is Friday
        assert "Mon" in names
        assert "Wed" in names
        assert "Fri" in names

    def test_breakdown_by_session(self):
        """Trade breakdown by session classifies correctly."""
        fills = self._make_trade_fills()
        result = compute_trade_breakdown(fills)

        by_session = result["by_session"]
        sessions = {s["session"] for s in by_session}
        # Trade 1 at 10am → Morning, Trade 2 at 15pm → Afternoon
        assert "Morning" in sessions
        assert "Afternoon" in sessions

    def test_win_loss_counts(self):
        """Win/loss counts match PnL signs."""
        fills = self._make_trade_fills()
        result = compute_trade_breakdown(fills)

        total_wins = sum(h["win_count"] for h in result["by_hour"])
        total_losses = sum(h["loss_count"] for h in result["by_hour"])
        assert total_wins == 2  # Trades 1 and 3 are wins
        assert total_losses == 1  # Trade 2 is a loss

    def test_empty_fills_returns_empty(self):
        result = compute_trade_breakdown([])
        assert result["by_hour"] == []
        assert result["by_weekday"] == []
        assert result["by_session"] == []

    def test_session_mapping(self):
        """Session mapping covers expected ranges."""
        assert _get_session(4) == "Pre-Market"
        assert _get_session(10) == "Morning"
        assert _get_session(12) == "Lunch"
        assert _get_session(14) == "Afternoon"
        assert _get_session(16) == "After-Hours"
        assert _get_session(2) == "Off-Hours"
        assert _get_session(22) == "Off-Hours"


# ---------------------------------------------------------------------------
# ADV-07/08: MAE/MFE
# ---------------------------------------------------------------------------

class TestMAEMFE:
    def test_long_trade_mae_mfe(self):
        """Long trade: MAE when price dips, MFE when price rises."""
        start = datetime(2024, 1, 1, 10, 0)
        fills = [
            _make_fill("AAPL", start, OrderSide.BUY, 10, 100, commission=0),
            _make_fill("AAPL", start + timedelta(hours=4), OrderSide.SELL, 10, 105, commission=0),
        ]
        equity_log = [
            {"timestamp": start, "equity": Decimal("10000"), "cash": Decimal("9000"), "price": Decimal("100")},
            {"timestamp": start + timedelta(hours=1), "equity": Decimal("9800"), "cash": Decimal("9000"), "price": Decimal("98")},
            {"timestamp": start + timedelta(hours=2), "equity": Decimal("10300"), "cash": Decimal("9000"), "price": Decimal("107")},
            {"timestamp": start + timedelta(hours=3), "equity": Decimal("10100"), "cash": Decimal("9000"), "price": Decimal("103")},
            {"timestamp": start + timedelta(hours=4), "equity": Decimal("10500"), "cash": Decimal("10500"), "price": Decimal("105")},
        ]

        result = compute_mae_mfe(equity_log, fills)
        assert len(result) == 1
        trade = result[0]
        assert trade["side"] == "LONG"
        # MAE = entry(100) - min(98) = 2
        assert trade["mae"] == Decimal("2")
        # MFE = max(107) - entry(100) = 7
        assert trade["mfe"] == Decimal("7")
        assert trade["is_win"] is True

    def test_short_trade_mae_mfe(self):
        """Short trade: MAE when price rises, MFE when price drops."""
        start = datetime(2024, 1, 1, 10, 0)
        fills = [
            _make_fill("AAPL", start, OrderSide.SELL, 10, 100, commission=0),
            _make_fill("AAPL", start + timedelta(hours=3), OrderSide.BUY, 10, 95, commission=0),
        ]
        equity_log = [
            {"timestamp": start, "equity": Decimal("10000"), "cash": Decimal("11000"), "price": Decimal("100")},
            {"timestamp": start + timedelta(hours=1), "equity": Decimal("9700"), "cash": Decimal("11000"), "price": Decimal("103")},
            {"timestamp": start + timedelta(hours=2), "equity": Decimal("10200"), "cash": Decimal("11000"), "price": Decimal("92")},
            {"timestamp": start + timedelta(hours=3), "equity": Decimal("10500"), "cash": Decimal("10500"), "price": Decimal("95")},
        ]

        result = compute_mae_mfe(equity_log, fills)
        assert len(result) == 1
        trade = result[0]
        assert trade["side"] == "SHORT"
        # MAE = max(103) - entry(100) = 3
        assert trade["mae"] == Decimal("3")
        # MFE = entry(100) - min(92) = 8
        assert trade["mfe"] == Decimal("8")

    def test_empty_fills_returns_empty(self):
        result = compute_mae_mfe([], [])
        assert result == []

    def test_no_matching_prices_skips_trade(self):
        """Trades with no matching equity_log bars are skipped."""
        start = datetime(2024, 1, 1)
        fills = [
            _make_fill("AAPL", start, OrderSide.BUY, 10, 100),
            _make_fill("AAPL", start + timedelta(hours=1), OrderSide.SELL, 10, 105),
        ]
        # Equity log with completely different timestamps
        equity_log = [
            {"timestamp": datetime(2025, 1, 1), "equity": Decimal("10000"), "cash": Decimal("10000"), "price": Decimal("100")},
        ]
        result = compute_mae_mfe(equity_log, fills)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Pair fills to trades helper
# ---------------------------------------------------------------------------

class TestPairFillsToTrades:
    def test_basic_pairing(self):
        start = datetime(2024, 1, 1)
        fills = [
            _make_fill("AAPL", start, OrderSide.BUY, 10, 100),
            _make_fill("AAPL", start + timedelta(hours=1), OrderSide.SELL, 10, 105),
        ]
        trades = _pair_fills_to_trades(fills)
        assert len(trades) == 1
        assert trades[0]["pnl"] > Decimal("0")  # Win minus commissions

    def test_empty_fills(self):
        assert _pair_fills_to_trades([]) == []

    def test_unpaired_fill_not_in_trades(self):
        """Open fills without a closing fill are not counted as trades."""
        start = datetime(2024, 1, 1)
        fills = [
            _make_fill("AAPL", start, OrderSide.BUY, 10, 100),
        ]
        trades = _pair_fills_to_trades(fills)
        assert len(trades) == 0


# ---------------------------------------------------------------------------
# ADV-09: Commission Sensitivity Sweep (mocked)
# ---------------------------------------------------------------------------

class TestCommissionSweep:
    def test_sweep_with_mocked_engine(self):
        """Commission sweep runs with mocked DataHandler + engine."""
        from unittest.mock import patch, MagicMock
        from src.analytics import run_commission_sweep
        from src.engine import BacktestResult

        mock_result = BacktestResult(
            equity_log=[
                {"timestamp": datetime(2024, 1, 1), "equity": Decimal("10000"), "cash": Decimal("10000")},
                {"timestamp": datetime(2024, 1, 2), "equity": Decimal("10100"), "cash": Decimal("10000")},
                {"timestamp": datetime(2024, 1, 3), "equity": Decimal("10200"), "cash": Decimal("10200")},
            ],
            fill_log=[
                _make_fill("TEST", datetime(2024, 1, 1), OrderSide.BUY, 10, 100),
                _make_fill("TEST", datetime(2024, 1, 2), OrderSide.SELL, 10, 102),
            ],
            event_log=[],
            final_equity=Decimal("10200"),
            total_bars=3,
        )

        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.data_handler.DataHandler") as MockDH, \
             patch("src.engine.create_engine", return_value=mock_engine):
            results = run_commission_sweep("TEST", "reversal", "1d", [0.0, 1.0, 2.0])

        assert len(results) == 3
        assert results[0]["multiplier"] == 0.0
        assert results[1]["multiplier"] == 1.0
        assert results[2]["multiplier"] == 2.0
        # All should have numeric values
        for r in results:
            assert isinstance(r["sharpe"], float)
            assert isinstance(r["net_pnl"], float)

    def test_sweep_unknown_strategy_returns_empty(self):
        from src.analytics import run_commission_sweep
        result = run_commission_sweep("TEST", "unknown_strategy", "1d")
        assert result == []

    def test_sweep_handles_empty_equity_log(self):
        """Sweep returns zeros when engine produces no equity data."""
        from unittest.mock import patch, MagicMock
        from src.analytics import run_commission_sweep
        from src.engine import BacktestResult

        mock_result = BacktestResult(
            equity_log=[],
            fill_log=[],
            event_log=[],
            final_equity=Decimal("0"),
            total_bars=0,
        )
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.data_handler.DataHandler"), \
             patch("src.engine.create_engine", return_value=mock_engine):
            results = run_commission_sweep("TEST", "reversal", "1d", [1.0])

        assert len(results) == 1
        assert results[0]["sharpe"] == 0.0

    def test_sweep_handles_exception(self):
        """Sweep returns zeros on exception."""
        from unittest.mock import patch
        from src.analytics import run_commission_sweep

        with patch("src.data_handler.DataHandler", side_effect=Exception("Network error")):
            results = run_commission_sweep("TEST", "reversal", "1d", [1.0])

        assert len(results) == 1
        assert results[0]["sharpe"] == 0.0

    def test_sweep_default_multipliers(self):
        """Default multipliers are [0, 0.5, 1, 2, 3]."""
        from unittest.mock import patch, MagicMock
        from src.analytics import run_commission_sweep
        from src.engine import BacktestResult

        mock_result = BacktestResult(
            equity_log=[
                {"timestamp": datetime(2024, 1, 1), "equity": Decimal("10000"), "cash": Decimal("10000")},
                {"timestamp": datetime(2024, 1, 2), "equity": Decimal("10100"), "cash": Decimal("10100")},
            ],
            fill_log=[],
            event_log=[],
            final_equity=Decimal("10100"),
            total_bars=2,
        )
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_result

        with patch("src.data_handler.DataHandler"), \
             patch("src.engine.create_engine", return_value=mock_engine):
            results = run_commission_sweep("TEST", "reversal", "1d")

        assert len(results) == 5
        multipliers = [r["multiplier"] for r in results]
        assert multipliers == [0.0, 0.5, 1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# Chart builder functions (smoke tests)
# ---------------------------------------------------------------------------

class TestChartBuilders:
    def test_monthly_heatmap_empty(self):
        from src.dashboard.callbacks import build_monthly_heatmap
        fig = build_monthly_heatmap({})
        assert fig is not None

    def test_monthly_heatmap_with_data(self):
        from src.dashboard.callbacks import build_monthly_heatmap
        data = {2024: {1: Decimal("5.0"), 2: Decimal("-3.0")}}
        fig = build_monthly_heatmap(data)
        assert len(fig.data) == 1  # One heatmap trace

    def test_rolling_sharpe_figure_empty(self):
        from src.dashboard.callbacks import build_rolling_sharpe_figure
        fig = build_rolling_sharpe_figure([])
        assert fig is not None

    def test_rolling_sharpe_figure_with_data(self):
        from src.dashboard.callbacks import build_rolling_sharpe_figure
        data = [
            {"timestamp": datetime(2024, 1, 1), "rolling_sharpe": 1.5},
            {"timestamp": datetime(2024, 1, 2), "rolling_sharpe": 1.8},
        ]
        fig = build_rolling_sharpe_figure(data)
        assert len(fig.data) == 1

    def test_rolling_drawdown_figure_empty(self):
        from src.dashboard.callbacks import build_rolling_drawdown_figure
        fig = build_rolling_drawdown_figure([])
        assert fig is not None

    def test_mae_figure_with_data(self):
        from src.dashboard.callbacks import build_mae_figure
        data = [
            {"mae": Decimal("5"), "pnl": Decimal("10"), "is_win": True},
            {"mae": Decimal("8"), "pnl": Decimal("-5"), "is_win": False},
        ]
        fig = build_mae_figure(data)
        assert len(fig.data) == 2  # Wins + Losses

    def test_mfe_figure_with_data(self):
        from src.dashboard.callbacks import build_mfe_figure
        data = [
            {"mfe": Decimal("10"), "pnl": Decimal("8"), "is_win": True},
        ]
        fig = build_mfe_figure(data)
        assert len(fig.data) == 1  # Only wins

    def test_commission_sweep_figure_empty(self):
        from src.dashboard.callbacks import build_commission_sweep_figure
        fig = build_commission_sweep_figure([])
        assert fig is not None

    def test_commission_sweep_figure_with_data(self):
        from src.dashboard.callbacks import build_commission_sweep_figure
        data = [
            {"multiplier": 0.0, "sharpe": 1.5, "net_pnl": 500, "win_rate": 60, "max_dd_pct": 5},
            {"multiplier": 1.0, "sharpe": 1.2, "net_pnl": 400, "win_rate": 55, "max_dd_pct": 7},
            {"multiplier": 2.0, "sharpe": 0.8, "net_pnl": 200, "win_rate": 50, "max_dd_pct": 10},
        ]
        fig = build_commission_sweep_figure(data)
        assert len(fig.data) == 4  # 4 subplot traces

    def test_breakdown_count_figure_empty(self):
        from src.dashboard.callbacks import _build_breakdown_count_figure
        fig = _build_breakdown_count_figure([], "hour", "Test")
        assert fig is not None

    def test_breakdown_pnl_figure_with_data(self):
        from src.dashboard.callbacks import _build_breakdown_pnl_figure
        data = [
            {"hour": 10, "total_pnl": Decimal("50"), "count": 3, "win_count": 2, "loss_count": 1},
            {"hour": 14, "total_pnl": Decimal("-20"), "count": 2, "win_count": 0, "loss_count": 2},
        ]
        fig = _build_breakdown_pnl_figure(data, "hour", "PnL by Hour")
        assert len(fig.data) == 1  # One bar trace


# ---------------------------------------------------------------------------
# Serialization / Deserialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_roundtrip_serialization(self):
        """Serialize and deserialize produces equivalent data."""
        from src.dashboard.callbacks import _serialize_result, _deserialize_result
        from src.engine import BacktestResult

        start = datetime(2024, 1, 1)
        equity_log = [
            {"timestamp": start, "equity": Decimal("10000"), "cash": Decimal("10000"), "price": Decimal("100")},
            {"timestamp": start + timedelta(days=1), "equity": Decimal("10100"), "cash": Decimal("10100"), "price": Decimal("101")},
        ]
        fill_log = [
            _make_fill("AAPL", start, OrderSide.BUY, 10, 100),
        ]

        result = BacktestResult(
            equity_log=equity_log,
            fill_log=fill_log,
            event_log=[],
            final_equity=Decimal("10100"),
            total_bars=2,
        )

        serialized = _serialize_result(result, "reversal", "1d", "AAPL")
        eq_out, fill_out, tf_out, _ = _deserialize_result(serialized)

        assert len(eq_out) == 2
        assert eq_out[0]["equity"] == Decimal("10000")
        assert eq_out[1]["equity"] == Decimal("10100")
        assert len(fill_out) == 1
        assert fill_out[0].fill_price == Decimal("100")
        assert tf_out == "1d"


# ---------------------------------------------------------------------------
# Dashboard layout (smoke test)
# ---------------------------------------------------------------------------

class TestDashboardLayout:
    def test_layout_builds_without_error(self):
        """The tabbed layout builds without exceptions."""
        from src.dashboard.layouts import build_layout
        layout = build_layout()
        assert layout is not None

    def test_create_app_with_new_layout(self):
        """create_app() works with the new tabbed layout."""
        from src.dashboard.app import create_app
        app = create_app()
        assert app is not None
        assert app.layout is not None


# ---------------------------------------------------------------------------
# Additional callback edge cases
# ---------------------------------------------------------------------------

class TestCallbackEdgeCases:
    def test_build_candlestick_empty(self):
        from src.dashboard.callbacks import build_candlestick_figure
        fig = build_candlestick_figure([], [])
        assert fig is not None

    def test_build_equity_empty(self):
        from src.dashboard.callbacks import build_equity_figure
        fig = build_equity_figure([])
        assert fig is not None

    def test_build_drawdown_empty(self):
        from src.dashboard.callbacks import build_drawdown_figure
        fig = build_drawdown_figure([])
        assert fig is not None

    def test_build_heatmap_empty(self):
        from src.dashboard.callbacks import build_heatmap_figure
        fig = build_heatmap_figure([], "p1", "p2")
        assert fig is not None

    def test_format_decimal(self):
        from src.dashboard.callbacks import _format_decimal
        assert _format_decimal(Decimal("1234.567"), 2) == "1,234.57"
        assert _format_decimal(Decimal("0.5"), 3) == "0.500"

    def test_import_strategy_valid(self):
        from src.dashboard.callbacks import _import_strategy
        cls = _import_strategy("reversal")
        assert cls.__name__ == "ReversalStrategy"

    def test_import_strategy_all_types(self):
        from src.dashboard.callbacks import _import_strategy
        for name in ["reversal", "breakout", "fvg"]:
            cls = _import_strategy(name)
            assert cls is not None

    def test_run_backtest_bad_strategy(self):
        """_run_backtest with invalid strategy returns error."""
        from src.dashboard.callbacks import _run_backtest
        result, metrics, error, _ = _run_backtest("AAPL", "nonexistent", "1d")
        assert error is not None
        assert result is None

    def test_deserialize_no_price_field(self):
        """Deserialization handles missing price field."""
        from src.dashboard.callbacks import _deserialize_result
        store = {
            "equity_log": [
                {"timestamp": "2024-01-01T00:00:00", "equity": "10000", "cash": "10000"},
            ],
            "fill_log": [],
            "timeframe": "1d",
        }
        eq, fills, tf, _ = _deserialize_result(store)
        assert len(eq) == 1
        assert "price" not in eq[0]
        assert tf == "1d"

    def test_mae_mfe_figures_only_wins(self):
        """MAE/MFE figures with only winning trades (no loss trace)."""
        from src.dashboard.callbacks import build_mae_figure, build_mfe_figure
        data = [
            {"mae": Decimal("2"), "mfe": Decimal("10"), "pnl": Decimal("50"), "is_win": True},
        ]
        mae_fig = build_mae_figure(data)
        mfe_fig = build_mfe_figure(data)
        assert len(mae_fig.data) == 1  # Only wins
        assert len(mfe_fig.data) == 1

    def test_mae_mfe_figures_only_losses(self):
        """MAE/MFE figures with only losing trades (no win trace)."""
        from src.dashboard.callbacks import build_mae_figure, build_mfe_figure
        data = [
            {"mae": Decimal("8"), "mfe": Decimal("3"), "pnl": Decimal("-20"), "is_win": False},
        ]
        mae_fig = build_mae_figure(data)
        mfe_fig = build_mfe_figure(data)
        assert len(mae_fig.data) == 1  # Only losses
        assert len(mfe_fig.data) == 1
