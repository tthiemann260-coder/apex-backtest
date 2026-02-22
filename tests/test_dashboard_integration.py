"""
test_dashboard_integration.py — Phase 18 dashboard integration tests.

Tests chart builder functions directly (no Dash app needed).
Requirements: TEST-24
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import plotly.graph_objects as go
import pytest

from src.events import FillEvent, OrderSide
from src.dashboard.callbacks import (
    REGIME_COLORS,
    _add_regime_overlay,
    build_heat_gauge_figure,
    build_sizing_distribution_figure,
    build_daily_risk_usage_figure,
    build_drawdown_scaling_figure,
    build_multi_equity_figure,
    build_correlation_heatmap_figure,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fill(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: str = "10",
    price: str = "150.00",
    timestamp: datetime | None = None,
) -> FillEvent:
    return FillEvent(
        symbol=symbol,
        timestamp=timestamp or datetime(2024, 1, 15, 10, 0),
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(price),
        commission=Decimal("1.00"),
        slippage=Decimal("0.05"),
        spread_cost=Decimal("0.02"),
    )


def _make_equity_log(n: int = 10, start_equity: str = "10000") -> list[dict]:
    """Create a simple equity log with rising equity."""
    base = Decimal(start_equity)
    log = []
    for i in range(n):
        log.append({
            "timestamp": datetime(2024, 1, 1 + i, 16, 0),
            "equity": base + Decimal(str(i * 10)),
            "cash": base + Decimal(str(i * 10)),
        })
    return log


# ---------------------------------------------------------------------------
# Test: REGIME_COLORS covers all 6 RegimeType values
# ---------------------------------------------------------------------------

class TestRegimeOverlay:
    def test_regime_colors_all_types(self):
        """REGIME_COLORS has all 6 RegimeType values."""
        expected = {
            "STRONG_TREND", "MODERATE_TREND", "WEAK_TREND",
            "RANGING_NORMAL", "RANGING_LOW", "CHOPPY",
        }
        assert set(REGIME_COLORS.keys()) == expected

    def test_add_regime_overlay_empty(self):
        """_add_regime_overlay with empty list does nothing."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4]))
        n_shapes_before = len(fig.layout.shapes) if fig.layout.shapes else 0

        _add_regime_overlay(fig, [])

        n_shapes_after = len(fig.layout.shapes) if fig.layout.shapes else 0
        assert n_shapes_after == n_shapes_before

    def test_add_regime_overlay_bands(self):
        """_add_regime_overlay adds vrects for regime bands."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1, 2, 3], y=[10, 20, 30]))

        regime_log = [
            {"timestamp": datetime(2024, 1, 1), "regime_type": "STRONG_TREND",
             "adx": 45.0, "vol_regime": "NORMAL"},
            {"timestamp": datetime(2024, 1, 2), "regime_type": "STRONG_TREND",
             "adx": 46.0, "vol_regime": "NORMAL"},
            {"timestamp": datetime(2024, 1, 3), "regime_type": "CHOPPY",
             "adx": 15.0, "vol_regime": "HIGH"},
        ]

        _add_regime_overlay(fig, regime_log)

        # Should have 2 vrect shapes (STRONG_TREND band + CHOPPY band)
        assert len(fig.layout.shapes) == 2


# ---------------------------------------------------------------------------
# Test: Risk Dashboard chart builders
# ---------------------------------------------------------------------------

class TestRiskCharts:
    def test_build_heat_gauge_empty(self):
        """Heat gauge with empty data returns valid figure."""
        fig = build_heat_gauge_figure([], [])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].mode == "gauge+number"

    def test_build_heat_gauge_with_data(self):
        """Heat gauge with fills computes heat value."""
        equity_log = _make_equity_log(5)
        fills = [
            _make_fill(side=OrderSide.BUY, quantity="10", price="150.00"),
            _make_fill(side=OrderSide.SELL, quantity="5", price="155.00"),
        ]
        fig = build_heat_gauge_figure(equity_log, fills)
        assert isinstance(fig, go.Figure)
        assert fig.data[0].value is not None

    def test_build_sizing_distribution_empty(self):
        """Sizing distribution with empty fills returns valid figure."""
        fig = build_sizing_distribution_figure([])
        assert isinstance(fig, go.Figure)

    def test_build_sizing_distribution_with_data(self):
        """Histogram from fill quantities returns figure with data."""
        fills = [
            _make_fill(quantity="10"),
            _make_fill(quantity="15"),
            _make_fill(quantity="20"),
        ]
        fig = build_sizing_distribution_figure(fills)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1  # One histogram trace

    def test_build_daily_risk_usage_empty(self):
        """Daily risk usage with empty fills returns valid figure."""
        fig = build_daily_risk_usage_figure([])
        assert isinstance(fig, go.Figure)

    def test_build_drawdown_scaling_figure(self):
        """Drawdown scaling returns figure with scale factor line."""
        equity_log = _make_equity_log(20)
        fig = build_drawdown_scaling_figure(equity_log)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) >= 1


# ---------------------------------------------------------------------------
# Test: Multi-Asset chart builders
# ---------------------------------------------------------------------------

class TestMultiAssetCharts:
    def test_build_multi_equity_empty(self):
        """Empty equity_log returns valid figure with annotation."""
        fig = build_multi_equity_figure([])
        assert isinstance(fig, go.Figure)

    def test_build_correlation_heatmap_empty(self):
        """Empty data returns valid figure with annotation."""
        fig = build_correlation_heatmap_figure([])
        assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# Test: Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_regime_log_round_trip(self):
        """regime_log survives serialize → deserialize round-trip."""
        from src.dashboard.callbacks import _serialize_result, _deserialize_result
        from src.engine import BacktestResult

        equity_log = _make_equity_log(3)
        fills = [_make_fill()]

        result = BacktestResult(
            equity_log=equity_log,
            fill_log=fills,
            final_equity=Decimal("10030"),
        )

        regime_log = [
            {"timestamp": datetime(2024, 1, 1, 16, 0),
             "regime_type": "STRONG_TREND", "adx": 42.5, "vol_regime": "NORMAL"},
            {"timestamp": datetime(2024, 1, 2, 16, 0),
             "regime_type": "CHOPPY", "adx": 15.0, "vol_regime": "HIGH"},
        ]

        store = _serialize_result(result, "regime_ict", "1d", "AAPL", regime_log)

        # Verify serialized regime_log exists
        assert "regime_log" in store
        assert len(store["regime_log"]) == 2

        # Deserialize and verify round-trip
        eq, fl, tf, rl = _deserialize_result(store)
        assert len(rl) == 2
        assert rl[0]["regime_type"] == "STRONG_TREND"
        assert rl[1]["regime_type"] == "CHOPPY"
        assert isinstance(rl[0]["timestamp"], datetime)
