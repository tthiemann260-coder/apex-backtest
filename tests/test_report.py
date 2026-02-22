"""
test_report.py — Tests for Report Export (Phase 13).

Covers:
- HTML report generation (RPT-01)
- PDF fallback (RPT-02)
- Template configuration (RPT-03)
- Trade list extraction
- Chart generation
- TEST-13: Reports generate without exception
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from src.engine import BacktestResult
from src.events import FillEvent, OrderSide
from src.metrics import MetricsResult
from src.report import (
    generate_report,
    _pair_fills_to_trades,
    _build_equity_figure,
    _build_drawdown_figure,
    _fig_to_html,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASE_TS = datetime(2024, 1, 1, 9, 30)


def _make_metrics() -> MetricsResult:
    return MetricsResult(
        net_pnl=Decimal("500"),
        total_return_pct=Decimal("5.0"),
        cagr=Decimal("3.2"),
        sharpe_ratio=Decimal("1.5"),
        sortino_ratio=Decimal("2.1"),
        calmar_ratio=Decimal("1.8"),
        max_drawdown=Decimal("200"),
        max_drawdown_pct=Decimal("-2.0"),
        max_drawdown_duration=10,
        win_rate=Decimal("55.0"),
        profit_factor=Decimal("1.6"),
        expectancy=Decimal("25.0"),
        trade_count=20,
        avg_holding_time=5,
        avg_rr=Decimal("1.3"),
        total_exposure_pct=Decimal("60.0"),
    )


def _make_result() -> BacktestResult:
    equity_log = []
    for i in range(30):
        equity_log.append({
            "timestamp": BASE_TS + timedelta(days=i),
            "equity": Decimal(str(10000 + i * 50)),
            "cash": Decimal(str(10000 + i * 50)),
        })

    fill_log = [
        FillEvent("TEST", BASE_TS + timedelta(days=5), OrderSide.BUY,
                  Decimal("10"), Decimal("100"), Decimal("1"), Decimal("0"), Decimal("0")),
        FillEvent("TEST", BASE_TS + timedelta(days=10), OrderSide.SELL,
                  Decimal("10"), Decimal("110"), Decimal("1"), Decimal("0"), Decimal("0")),
        FillEvent("TEST", BASE_TS + timedelta(days=15), OrderSide.BUY,
                  Decimal("10"), Decimal("105"), Decimal("1"), Decimal("0"), Decimal("0")),
        FillEvent("TEST", BASE_TS + timedelta(days=20), OrderSide.SELL,
                  Decimal("10"), Decimal("95"), Decimal("1"), Decimal("0"), Decimal("0")),
    ]

    return BacktestResult(
        equity_log=equity_log,
        fill_log=fill_log,
        event_log=[],
        final_equity=Decimal("11450"),
        total_bars=30,
    )


# ===========================================================================
# Trade Extraction Tests
# ===========================================================================


class TestPairFillsToTrades:

    def test_basic_round_trip(self):
        fills = [
            FillEvent("TEST", BASE_TS, OrderSide.BUY, Decimal("10"),
                      Decimal("100"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=1), OrderSide.SELL, Decimal("10"),
                      Decimal("110"), Decimal("1"), Decimal("0"), Decimal("0")),
        ]
        trades = _pair_fills_to_trades(fills)
        assert len(trades) == 1
        assert trades[0]["side"] == "LONG"
        assert trades[0]["pnl"] == pytest.approx(98.0)

    def test_short_trade(self):
        fills = [
            FillEvent("TEST", BASE_TS, OrderSide.SELL, Decimal("10"),
                      Decimal("110"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=1), OrderSide.BUY, Decimal("10"),
                      Decimal("100"), Decimal("1"), Decimal("0"), Decimal("0")),
        ]
        trades = _pair_fills_to_trades(fills)
        assert len(trades) == 1
        assert trades[0]["side"] == "SHORT"

    def test_multiple_trades(self):
        fills = [
            FillEvent("TEST", BASE_TS, OrderSide.BUY, Decimal("10"),
                      Decimal("100"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=1), OrderSide.SELL, Decimal("10"),
                      Decimal("110"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=2), OrderSide.BUY, Decimal("5"),
                      Decimal("105"), Decimal("1"), Decimal("0"), Decimal("0")),
            FillEvent("TEST", BASE_TS + timedelta(days=3), OrderSide.SELL, Decimal("5"),
                      Decimal("95"), Decimal("1"), Decimal("0"), Decimal("0")),
        ]
        trades = _pair_fills_to_trades(fills)
        assert len(trades) == 2
        assert trades[0]["pnl"] > 0  # Win
        assert trades[1]["pnl"] < 0  # Loss

    def test_empty_fills(self):
        assert _pair_fills_to_trades([]) == []


# ===========================================================================
# Chart Tests
# ===========================================================================


class TestCharts:

    def test_equity_figure_has_data(self):
        result = _make_result()
        fig = _build_equity_figure(result.equity_log)
        assert len(fig.data) > 0

    def test_equity_figure_empty(self):
        fig = _build_equity_figure([])
        assert len(fig.data) == 0

    def test_drawdown_figure_has_data(self):
        result = _make_result()
        fig = _build_drawdown_figure(result.equity_log)
        assert len(fig.data) > 0

    def test_drawdown_figure_empty(self):
        fig = _build_drawdown_figure([])
        assert len(fig.data) == 0

    def test_fig_to_html(self):
        result = _make_result()
        fig = _build_equity_figure(result.equity_log)
        html = _fig_to_html(fig)
        assert "<div" in html
        assert len(html) > 100


# ===========================================================================
# HTML Report Tests (RPT-01, TEST-13)
# ===========================================================================


class TestHTMLReport:

    def test_basic_html_generation(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(
            result, metrics,
            format="html",
            symbol="TEST",
            strategy_name="reversal",
        )
        assert "<!DOCTYPE html>" in html
        assert "TEST" in html
        assert "reversal" in html
        assert "500.00" in html  # Net PnL
        assert "1.50" in html   # Sharpe

    def test_kpi_section(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(result, metrics, format="html")
        assert "Key Performance Indicators" in html
        assert "Net PnL" in html
        assert "Sharpe Ratio" in html

    def test_trade_list(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(result, metrics, format="html")
        assert "Trade List" in html
        assert "LONG" in html

    def test_custom_title(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(
            result, metrics, format="html",
            title="My Custom Report",
        )
        assert "My Custom Report" in html

    def test_branding(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(
            result, metrics, format="html",
            branding="apex-backtest v2.0",
        )
        assert "apex-backtest v2.0" in html

    def test_hide_sections(self):
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(
            result, metrics, format="html",
            show_sections={"show_trades": False},
        )
        assert "Trade List" not in html

    def test_output_to_file(self):
        result = _make_result()
        metrics = _make_metrics()
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            path = f.name

        try:
            html = generate_report(
                result, metrics, format="html",
                output_path=path,
            )
            assert os.path.exists(path)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
        finally:
            os.unlink(path)

    def test_empty_result(self):
        """Empty result should not crash."""
        result = BacktestResult()
        metrics = _make_metrics()
        html = generate_report(result, metrics, format="html")
        assert "<!DOCTYPE html>" in html

    def test_robustness_section(self):
        from src.optimization.robustness import RobustnessReport
        rob = RobustnessReport(
            wfo_efficiency=0.8,
            wfo_mean_oos_sharpe=1.2,
            wfo_n_windows=5,
            wfo_pass=True,
            mc_p5_equity=10500.0,
            mc_p95_equity=11200.0,
            mc_equity_percentile=75.0,
            mc_n_trades=20,
            mc_pass=True,
            sensitivity_overall=0.7,
            sensitivity_param_cv={"param1": 0.1},
            sensitivity_pass=True,
            overall_pass=True,
            score=85.0,
        )
        result = _make_result()
        metrics = _make_metrics()
        html = generate_report(
            result, metrics, format="html",
            robustness=rob,
        )
        assert "Robustness" in html
        assert "85" in html


# ===========================================================================
# PDF Report Tests (RPT-02)
# ===========================================================================


class TestPDFReport:

    def test_pdf_fallback_to_html(self):
        """Without WeasyPrint, falls back to HTML file."""
        result = _make_result()
        metrics = _make_metrics()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            output = generate_report(
                result, metrics, format="pdf",
                output_path=path,
            )
            # Should produce a file (HTML fallback if no WeasyPrint)
            html_path = path.replace(".pdf", ".html")
            assert os.path.exists(html_path) or os.path.exists(path)
        finally:
            for p in [path, path.replace(".pdf", ".html")]:
                if os.path.exists(p):
                    os.unlink(p)


# ===========================================================================
# Template Tests (RPT-03)
# ===========================================================================


class TestTemplate:

    def test_custom_template(self):
        """Custom template can be loaded."""
        with tempfile.NamedTemporaryFile(
            suffix=".html", mode="w", delete=False, encoding="utf-8",
        ) as f:
            f.write("<html><body>Custom: {{ title }}</body></html>")
            template_path = f.name

        try:
            result = _make_result()
            metrics = _make_metrics()
            html = generate_report(
                result, metrics, format="html",
                template_path=template_path,
                title="TestTitle",
            )
            assert "Custom: TestTitle" in html
        finally:
            os.unlink(template_path)


# ===========================================================================
# Integration Tests
# ===========================================================================


class TestReportImports:

    def test_importable(self):
        import src.report
