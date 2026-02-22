"""
report.py — Report generation for apex-backtest (RPT-01, RPT-02, RPT-03).

Generates HTML and PDF reports from backtest results using Jinja2 templates.

Design:
- HTML reports include interactive Plotly charts (via CDN)
- PDF reports embed static chart images (base64 PNG)
- Template is configurable: title, branding, which sections to include
- Trade list extracted from fill_log

Requirement: RPT-01, RPT-02, RPT-03
"""

from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any, Optional

import jinja2
import plotly.graph_objects as go

from src.engine import BacktestResult
from src.events import FillEvent, OrderSide
from src.metrics import MetricsResult


# Default template directory
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


def _pair_fills_to_trades(fills: list[FillEvent]) -> list[dict]:
    """Extract round-trip trades from fill log for the trade table."""
    trades: list[dict] = []
    open_fill: Optional[FillEvent] = None

    for fill in fills:
        if open_fill is None:
            open_fill = fill
        else:
            if fill.side != open_fill.side:
                if open_fill.side == OrderSide.BUY:
                    pnl = float(
                        (fill.fill_price - open_fill.fill_price) * open_fill.quantity
                        - open_fill.commission - open_fill.slippage - open_fill.spread_cost
                        - fill.commission - fill.slippage - fill.spread_cost
                    )
                    side = "LONG"
                else:
                    pnl = float(
                        (open_fill.fill_price - fill.fill_price) * open_fill.quantity
                        - open_fill.commission - open_fill.slippage - open_fill.spread_cost
                        - fill.commission - fill.slippage - fill.spread_cost
                    )
                    side = "SHORT"

                trades.append({
                    "entry_time": open_fill.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "side": side,
                    "quantity": float(open_fill.quantity),
                    "entry_price": float(open_fill.fill_price),
                    "exit_price": float(fill.fill_price),
                    "pnl": pnl,
                })
                open_fill = None
            else:
                open_fill = fill

    return trades


def _build_equity_figure(equity_log: list[dict]) -> go.Figure:
    """Build equity curve figure."""
    if not equity_log:
        return go.Figure()

    timestamps = [e["timestamp"] for e in equity_log]
    equities = [float(e["equity"]) for e in equity_log]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=equities,
        mode="lines", name="Equity",
        line=dict(color="#0f3460", width=2),
        fill="tozeroy", fillcolor="rgba(15,52,96,0.1)",
    ))
    fig.update_layout(
        title="Equity Curve",
        xaxis_title="Date", yaxis_title="Equity",
        template="plotly_white",
        height=400,
        margin=dict(l=60, r=30, t=50, b=40),
    )
    return fig


def _build_drawdown_figure(equity_log: list[dict]) -> go.Figure:
    """Build drawdown chart."""
    if not equity_log:
        return go.Figure()

    timestamps = [e["timestamp"] for e in equity_log]
    equities = [float(e["equity"]) for e in equity_log]

    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100 if peak > 0 else 0
        drawdowns.append(dd)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=drawdowns,
        mode="lines", name="Drawdown %",
        line=dict(color="#dc3545", width=2),
        fill="tozeroy", fillcolor="rgba(220,53,69,0.15)",
    ))
    fig.update_layout(
        title="Drawdown",
        xaxis_title="Date", yaxis_title="Drawdown %",
        template="plotly_white",
        height=300,
        margin=dict(l=60, r=30, t=50, b=40),
    )
    return fig


def _fig_to_html(fig: go.Figure) -> str:
    """Convert Plotly figure to inline HTML div."""
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _fig_to_base64_png(fig: go.Figure, width: int = 900, height: int = 400) -> str:
    """Convert Plotly figure to base64-encoded PNG data URI."""
    try:
        img_bytes = fig.to_image(format="png", width=width, height=height)
        b64 = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/png;base64,{b64}"
    except Exception:
        # kaleido not installed — return empty
        return ""


def generate_report(
    result: BacktestResult,
    metrics: MetricsResult,
    format: str = "html",
    symbol: str = "",
    strategy_name: str = "",
    timeframe: str = "1d",
    template_path: Optional[str] = None,
    title: Optional[str] = None,
    branding: Optional[str] = None,
    show_sections: Optional[dict[str, bool]] = None,
    robustness: Optional[Any] = None,
    output_path: Optional[str] = None,
) -> str:
    """Generate a backtest report.

    Parameters
    ----------
    result : BacktestResult
        Backtest results (equity_log, fill_log).
    metrics : MetricsResult
        Computed performance metrics.
    format : str
        Output format: "html" or "pdf". Default: "html".
    symbol : str
        Instrument symbol.
    strategy_name : str
        Strategy name.
    timeframe : str
        Bar timeframe.
    template_path : Optional[str]
        Path to custom Jinja2 template. Default: built-in template.
    title : Optional[str]
        Report title.
    branding : Optional[str]
        Branding text in header.
    show_sections : Optional[dict[str, bool]]
        Control which sections to show: kpis, equity, drawdown, monthly, trades, robustness.
    robustness : Optional[Any]
        RobustnessReport for robustness section.
    output_path : Optional[str]
        If provided, write the report to this file path.

    Returns
    -------
    str
        The rendered report content (HTML string or PDF file path).
    """
    # Load template
    if template_path:
        template_dir = str(Path(template_path).parent)
        template_name = Path(template_path).name
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=True,
        )
    else:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )
        template_name = "report.html"

    template = env.get_template(template_name)

    # Section visibility
    sections = {
        "show_kpis": True,
        "show_equity": True,
        "show_drawdown": True,
        "show_monthly": False,
        "show_trades": True,
        "show_robustness": robustness is not None,
    }
    if show_sections:
        sections.update(show_sections)

    # Build charts
    equity_fig = _build_equity_figure(result.equity_log)
    drawdown_fig = _build_drawdown_figure(result.equity_log)

    # Trade list
    trades = _pair_fills_to_trades(result.fill_log)

    # Date range
    date_range = ""
    if result.equity_log:
        start = result.equity_log[0]["timestamp"]
        end = result.equity_log[-1]["timestamp"]
        date_range = f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"

    # Build template context
    is_pdf = format.lower() == "pdf"

    context = {
        # Header
        "title": title or f"Backtest Report — {symbol} {strategy_name}",
        "symbol": symbol,
        "strategy_name": strategy_name,
        "timeframe": timeframe,
        "date_range": date_range,
        "branding": branding,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "plotly_js": not is_pdf,

        # KPIs
        "net_pnl": float(metrics.net_pnl),
        "total_return": float(metrics.total_return_pct),
        "sharpe_ratio": float(metrics.sharpe_ratio),
        "sortino_ratio": float(metrics.sortino_ratio),
        "max_drawdown_pct": float(metrics.max_drawdown_pct),
        "calmar_ratio": float(metrics.calmar_ratio),
        "win_rate": float(metrics.win_rate),
        "profit_factor": float(metrics.profit_factor),
        "total_trades": metrics.trade_count,
        "exposure_pct": float(metrics.total_exposure_pct),

        # Charts
        "equity_chart_html": _fig_to_html(equity_fig) if not is_pdf else "",
        "equity_chart_img": _fig_to_base64_png(equity_fig) if is_pdf else "",
        "drawdown_chart_html": _fig_to_html(drawdown_fig) if not is_pdf else "",
        "drawdown_chart_img": _fig_to_base64_png(drawdown_fig) if is_pdf else "",
        "monthly_chart_html": "",

        # Trades
        "trades": trades,

        # Robustness
        "robustness": robustness,

        # Section visibility
        **sections,
    }

    html_content = template.render(**context)

    # Output
    if format.lower() == "pdf":
        pdf_path = output_path or "report.pdf"
        try:
            import weasyprint
            weasyprint.HTML(string=html_content).write_pdf(pdf_path)
        except ImportError:
            # WeasyPrint not available — save HTML with note
            pdf_path = pdf_path.replace(".pdf", ".html")
            Path(pdf_path).write_text(html_content, encoding="utf-8")
        return pdf_path

    if output_path:
        Path(output_path).write_text(html_content, encoding="utf-8")

    return html_content
