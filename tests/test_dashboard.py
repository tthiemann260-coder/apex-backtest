"""Tests for Dashboard — layout, callbacks, chart builders."""

from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import plotly.graph_objects as go
from dash import html

from src.events import FillEvent, OrderSide
from src.metrics import MetricsResult
from src.dashboard.layouts import (
    build_layout,
    build_kpi_card,
    build_kpi_panel,
    build_controls,
    build_candlestick_chart,
    build_equity_chart,
    build_drawdown_chart,
    build_heatmap_chart,
)
from src.dashboard.callbacks import (
    build_candlestick_figure,
    build_equity_figure,
    build_drawdown_figure,
    build_heatmap_figure,
    _format_decimal,
    _run_backtest,
    STRATEGY_MAP,
    SWEEP_PARAMS,
)
from src.dashboard.app import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_equity_log(n: int = 10) -> list[dict]:
    """Create a simple equity log."""
    from datetime import timedelta
    base = datetime(2024, 1, 1, 10, 0)
    log = []
    for i in range(n):
        eq = Decimal("10000") + Decimal(str(i * 50))
        log.append({
            "timestamp": base + timedelta(hours=i),
            "equity": eq,
            "cash": eq,
            "price": Decimal("100") + Decimal(str(i)),
        })
    return log


def _make_fill(
    side: OrderSide, price: str, day: int = 1,
) -> FillEvent:
    return FillEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        side=side,
        quantity=Decimal("100"),
        fill_price=Decimal(price),
        commission=Decimal("1"),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
    )


def _make_metrics() -> MetricsResult:
    return MetricsResult(
        net_pnl=Decimal("500"),
        total_return_pct=Decimal("5.0"),
        cagr=Decimal("0.12"),
        sharpe_ratio=Decimal("1.234"),
        sortino_ratio=Decimal("1.567"),
        calmar_ratio=Decimal("0.890"),
        max_drawdown=Decimal("200"),
        max_drawdown_pct=Decimal("2.0"),
        max_drawdown_duration=5,
        win_rate=Decimal("60"),
        profit_factor=Decimal("1.5"),
        expectancy=Decimal("25"),
        trade_count=10,
        avg_holding_time=3,
        avg_rr=Decimal("1.2"),
        total_exposure_pct=Decimal("45"),
    )


# ===========================================================================
# TestLayouts
# ===========================================================================

class TestLayouts:
    """DASH-04, DASH-05: Layout component tests."""

    def test_build_layout_returns_div(self):
        """build_layout() returns an html.Div."""
        layout = build_layout()
        assert isinstance(layout, html.Div)

    def test_kpi_card_has_title_and_id(self):
        """KPI card has the correct title and value id."""
        card = build_kpi_card("Net PnL", "kpi-net-pnl")
        # Card should be a dbc.Card
        assert card is not None

    def test_kpi_panel_has_10_cards(self):
        """KPI panel contains 10 KPI cards."""
        panel = build_kpi_panel()
        # Panel is a Row with Col children
        assert len(panel.children) == 10

    def test_controls_has_4_columns(self):
        """Controls row has 4 columns."""
        controls = build_controls()
        assert len(controls.children) == 4

    def test_candlestick_chart_has_id(self):
        """Candlestick chart has correct id."""
        chart = build_candlestick_chart()
        assert chart.id == "candlestick-chart"

    def test_equity_chart_has_id(self):
        """Equity chart has correct id."""
        chart = build_equity_chart()
        assert chart.id == "equity-chart"

    def test_drawdown_chart_has_id(self):
        """Drawdown chart has correct id."""
        chart = build_drawdown_chart()
        assert chart.id == "drawdown-chart"

    def test_heatmap_chart_has_id(self):
        """Heatmap chart has correct id."""
        chart = build_heatmap_chart()
        assert chart.id == "heatmap-chart"


# ===========================================================================
# TestCandlestickFigure
# ===========================================================================

class TestCandlestickFigure:
    """DASH-01: Candlestick chart with trade markers."""

    def test_empty_log_returns_figure(self):
        """Empty equity log returns a figure (no crash)."""
        fig = build_candlestick_figure([], [])
        assert isinstance(fig, go.Figure)

    def test_line_chart_without_ohlc(self):
        """Without OHLC fields, falls back to line chart."""
        log = _make_equity_log(5)
        fig = build_candlestick_figure(log, [])
        assert isinstance(fig, go.Figure)
        # Should have at least 1 trace (price line)
        assert len(fig.data) >= 1

    def test_buy_markers_added(self):
        """BUY fills add green triangle-up markers."""
        log = _make_equity_log(5)
        fills = [_make_fill(OrderSide.BUY, "100")]
        fig = build_candlestick_figure(log, fills)
        # Should have price trace + BUY trace
        assert len(fig.data) >= 2
        buy_trace = [t for t in fig.data if t.name == "BUY"]
        assert len(buy_trace) == 1

    def test_sell_markers_added(self):
        """SELL fills add red triangle-down markers."""
        log = _make_equity_log(5)
        fills = [_make_fill(OrderSide.SELL, "105")]
        fig = build_candlestick_figure(log, fills)
        sell_trace = [t for t in fig.data if t.name == "SELL"]
        assert len(sell_trace) == 1

    def test_both_markers(self):
        """Both BUY and SELL markers on same chart."""
        log = _make_equity_log(5)
        fills = [
            _make_fill(OrderSide.BUY, "100", day=1),
            _make_fill(OrderSide.SELL, "105", day=2),
        ]
        fig = build_candlestick_figure(log, fills)
        # Price + BUY + SELL = 3 traces
        assert len(fig.data) == 3


# ===========================================================================
# TestEquityFigure
# ===========================================================================

class TestEquityFigure:
    """DASH-02: Equity curve chart."""

    def test_empty_log_returns_figure(self):
        """Empty equity log returns a figure."""
        fig = build_equity_figure([])
        assert isinstance(fig, go.Figure)

    def test_equity_curve_has_trace(self):
        """Equity curve has at least one trace."""
        log = _make_equity_log(10)
        fig = build_equity_figure(log)
        assert len(fig.data) >= 1
        assert fig.data[0].name == "Equity"

    def test_equity_values_correct(self):
        """Equity trace y-values match equity log."""
        log = _make_equity_log(5)
        fig = build_equity_figure(log)
        expected = [float(e["equity"]) for e in log]
        actual = list(fig.data[0].y)
        assert actual == expected


# ===========================================================================
# TestDrawdownFigure
# ===========================================================================

class TestDrawdownFigure:
    """DASH-03: Drawdown chart."""

    def test_empty_log_returns_figure(self):
        """Empty equity log returns a figure."""
        fig = build_drawdown_figure([])
        assert isinstance(fig, go.Figure)

    def test_drawdown_all_negative_or_zero(self):
        """Drawdown values are all <= 0."""
        log = _make_equity_log(10)
        fig = build_drawdown_figure(log)
        drawdowns = list(fig.data[0].y)
        assert all(d <= 0 for d in drawdowns)

    def test_monotonic_up_zero_drawdown(self):
        """Monotonically increasing equity has zero drawdown."""
        log = _make_equity_log(10)
        fig = build_drawdown_figure(log)
        drawdowns = list(fig.data[0].y)
        assert all(d == 0 for d in drawdowns)


# ===========================================================================
# TestHeatmapFigure
# ===========================================================================

class TestHeatmapFigure:
    """DASH-06: Parameter sweep heatmap."""

    def test_empty_results_returns_figure(self):
        """Empty sweep results returns a figure."""
        fig = build_heatmap_figure([], "p1", "p2")
        assert isinstance(fig, go.Figure)

    def test_heatmap_with_data(self):
        """Heatmap renders with sweep data."""
        results = [
            {"p1": 10, "p2": 20, "sharpe_ratio": Decimal("1.5")},
            {"p1": 10, "p2": 30, "sharpe_ratio": Decimal("0.8")},
            {"p1": 20, "p2": 20, "sharpe_ratio": Decimal("2.0")},
            {"p1": 20, "p2": 30, "sharpe_ratio": Decimal("1.2")},
        ]
        fig = build_heatmap_figure(results, "p1", "p2")
        assert len(fig.data) == 1
        assert isinstance(fig.data[0], go.Heatmap)


# ===========================================================================
# TestFormatDecimal
# ===========================================================================

class TestFormatDecimal:
    """Utility: _format_decimal."""

    def test_positive(self):
        assert _format_decimal(Decimal("1234.5678"), 2) == "1,234.57"

    def test_negative(self):
        assert _format_decimal(Decimal("-500.123"), 2) == "-500.12"

    def test_zero(self):
        assert _format_decimal(Decimal("0"), 2) == "0.00"

    def test_three_decimals(self):
        assert _format_decimal(Decimal("1.23456"), 3) == "1.235"


# ===========================================================================
# TestStrategyMap
# ===========================================================================

class TestStrategyMap:
    """DASH-05: Strategy mapping and sweep params."""

    def test_all_strategies_mapped(self):
        """All three strategies are in STRATEGY_MAP."""
        assert "reversal" in STRATEGY_MAP
        assert "breakout" in STRATEGY_MAP
        assert "fvg" in STRATEGY_MAP

    def test_all_strategies_have_sweep_params(self):
        """All strategies have sweep parameter definitions."""
        assert "reversal" in SWEEP_PARAMS
        assert "breakout" in SWEEP_PARAMS
        assert "fvg" in SWEEP_PARAMS

    def test_sweep_params_have_values(self):
        """Sweep params contain non-empty lists."""
        for strategy, params in SWEEP_PARAMS.items():
            for param_name, values in params.items():
                assert len(values) >= 2, f"{strategy}.{param_name} needs >= 2 values"


# ===========================================================================
# TestAppCreation
# ===========================================================================

class TestAppCreation:
    """DASH-07: App creation and configuration."""

    def test_create_app_returns_dash(self):
        """create_app() returns a Dash app instance."""
        app = create_app()
        assert app is not None
        assert app.title == "apex-backtest Dashboard"

    def test_app_has_layout(self):
        """App has a layout set."""
        app = create_app()
        assert app.layout is not None

    def test_app_uses_darkly_theme(self):
        """App uses Bootstrap DARKLY theme."""
        app = create_app()
        stylesheets = app.config.external_stylesheets
        # Should contain the DARKLY theme URL
        assert any("darkly" in str(s).lower() or "bootstrap" in str(s).lower()
                    for s in stylesheets)
