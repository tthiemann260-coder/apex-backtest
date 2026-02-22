"""
layouts.py — Dashboard layout components for apex-backtest.

Builds the Dash layout with:
- KPI cards panel (DASH-04)
- Candlestick chart with trade markers (DASH-01)
- Equity curve (DASH-02)
- Drawdown chart (DASH-03)
- Strategy/timeframe selectors (DASH-05)
- Parameter sweep heatmap placeholder (DASH-06)
"""

from __future__ import annotations

from dash import html, dcc
import dash_bootstrap_components as dbc


def build_kpi_card(title: str, value_id: str) -> dbc.Card:
    """Build a single KPI card."""
    return dbc.Card(
        dbc.CardBody([
            html.H6(title, className="card-title text-muted mb-1",
                     style={"fontSize": "0.8rem"}),
            html.H4(id=value_id, className="card-text mb-0",
                     style={"fontWeight": "bold"}),
        ]),
        className="shadow-sm",
        style={"minWidth": "140px"},
    )


def build_kpi_panel() -> dbc.Row:
    """Build the KPI cards row (DASH-04)."""
    kpis = [
        ("Net PnL", "kpi-net-pnl"),
        ("Total Return %", "kpi-total-return"),
        ("Sharpe Ratio", "kpi-sharpe"),
        ("Sortino Ratio", "kpi-sortino"),
        ("Max Drawdown %", "kpi-max-dd"),
        ("Calmar Ratio", "kpi-calmar"),
        ("Win Rate %", "kpi-win-rate"),
        ("Profit Factor", "kpi-profit-factor"),
        ("Trade Count", "kpi-trade-count"),
        ("Exposure %", "kpi-exposure"),
    ]
    return dbc.Row(
        [dbc.Col(build_kpi_card(title, vid), width="auto") for title, vid in kpis],
        className="g-2 mb-3 flex-nowrap overflow-auto",
    )


def build_controls() -> dbc.Row:
    """Build strategy and timeframe selectors (DASH-05)."""
    return dbc.Row([
        dbc.Col([
            html.Label("Strategy", className="fw-bold mb-1"),
            dcc.Dropdown(
                id="strategy-selector",
                options=[
                    {"label": "Reversal (RSI)", "value": "reversal"},
                    {"label": "Breakout (Donchian)", "value": "breakout"},
                    {"label": "FVG (Fair Value Gap)", "value": "fvg"},
                ],
                value="reversal",
                clearable=False,
            ),
        ], md=3),
        dbc.Col([
            html.Label("Timeframe", className="fw-bold mb-1"),
            dcc.Dropdown(
                id="timeframe-selector",
                options=[
                    {"label": "1 Minute", "value": "1m"},
                    {"label": "5 Minutes", "value": "5m"},
                    {"label": "15 Minutes", "value": "15m"},
                    {"label": "1 Hour", "value": "1h"},
                    {"label": "4 Hours", "value": "4h"},
                    {"label": "Daily", "value": "1d"},
                ],
                value="1d",
                clearable=False,
            ),
        ], md=3),
        dbc.Col([
            html.Label("Symbol", className="fw-bold mb-1"),
            dcc.Input(
                id="symbol-input",
                type="text",
                value="AAPL",
                placeholder="z.B. AAPL, EURUSD=X",
                className="form-control",
            ),
        ], md=3),
        dbc.Col([
            html.Label("\u00a0", className="d-block mb-1"),
            dbc.Button(
                "Run Backtest",
                id="run-backtest-btn",
                color="primary",
                className="w-100",
            ),
        ], md=3),
    ], className="mb-3")


def build_candlestick_chart() -> dcc.Graph:
    """Candlestick chart placeholder (DASH-01)."""
    return dcc.Graph(
        id="candlestick-chart",
        config={"displayModeBar": True, "scrollZoom": True},
        style={"height": "450px"},
    )


def build_equity_chart() -> dcc.Graph:
    """Equity curve chart placeholder (DASH-02)."""
    return dcc.Graph(
        id="equity-chart",
        config={"displayModeBar": True},
        style={"height": "300px"},
    )


def build_drawdown_chart() -> dcc.Graph:
    """Drawdown waterfall chart placeholder (DASH-03)."""
    return dcc.Graph(
        id="drawdown-chart",
        config={"displayModeBar": True},
        style={"height": "300px"},
    )


def build_heatmap_chart() -> dcc.Graph:
    """Parameter sweep heatmap placeholder (DASH-06)."""
    return dcc.Graph(
        id="heatmap-chart",
        config={"displayModeBar": True},
        style={"height": "400px"},
    )


def build_layout() -> html.Div:
    """Build the complete dashboard layout."""
    return html.Div([
        # Header
        dbc.Navbar(
            dbc.Container([
                dbc.NavbarBrand(
                    "apex-backtest Dashboard",
                    className="fw-bold",
                    style={"fontSize": "1.3rem"},
                ),
                html.Span(
                    "Event-Driven Backtesting Engine",
                    className="text-muted",
                    style={"fontSize": "0.85rem"},
                ),
            ]),
            color="dark",
            dark=True,
            className="mb-3",
        ),

        dbc.Container([
            # Controls row
            build_controls(),

            # Status/loading
            dcc.Loading(
                id="loading-indicator",
                type="circle",
                children=[html.Div(id="loading-output")],
            ),

            # KPI panel
            build_kpi_panel(),

            # Charts
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Candlestick + Trade Markers"),
                        dbc.CardBody(build_candlestick_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=12),
            ]),

            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Equity Curve"),
                        dbc.CardBody(build_equity_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Drawdown"),
                        dbc.CardBody(build_drawdown_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),

            # Sweep Heatmap (collapsible)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Span("Parameter Sweep Heatmap"),
                            dbc.Button(
                                "Run Sweep",
                                id="run-sweep-btn",
                                color="secondary",
                                size="sm",
                                className="float-end",
                            ),
                        ]),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Param 1", className="fw-bold mb-1"),
                                    dcc.Dropdown(
                                        id="sweep-param1",
                                        options=[],
                                        placeholder="Select parameter...",
                                    ),
                                ], md=4),
                                dbc.Col([
                                    html.Label("Param 2", className="fw-bold mb-1"),
                                    dcc.Dropdown(
                                        id="sweep-param2",
                                        options=[],
                                        placeholder="Select parameter...",
                                    ),
                                ], md=4),
                            ], className="mb-2"),
                            build_heatmap_chart(),
                        ]),
                    ], className="shadow-sm mb-3"),
                ], md=12),
            ]),

        ], fluid=True),
    ])
