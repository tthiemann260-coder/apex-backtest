"""
layouts.py — Dashboard layout components for apex-backtest.

Builds the Dash layout with tabs:
- Tab 1: Overview (Candlestick, Equity, Drawdown, KPIs) — DASH-01..06
- Tab 2: Advanced Analytics (Monthly Heatmap, Rolling Sharpe/DD) — ADV-01..03
- Tab 3: Trade Analysis (Breakdown, MAE/MFE) — ADV-04..08
- Tab 4: Sensitivity (Parameter Sweep + Commission Sweep) — DASH-06, ADV-09
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
                    {"label": "SMC (Smart Money Concepts)", "value": "smc"},
                    {"label": "ICT (Enhanced Liquidity)", "value": "ict"},
                    {"label": "Regime-Gated ICT", "value": "regime_ict"},
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


# ---------------------------------------------------------------------------
# Phase 9: Advanced Analytics chart placeholders
# ---------------------------------------------------------------------------

def build_monthly_heatmap_chart() -> dcc.Graph:
    """Monthly returns heatmap placeholder (ADV-01)."""
    return dcc.Graph(
        id="monthly-heatmap-chart",
        config={"displayModeBar": True},
        style={"height": "350px"},
    )


def build_rolling_sharpe_chart() -> dcc.Graph:
    """Rolling Sharpe ratio chart placeholder (ADV-02)."""
    return dcc.Graph(
        id="rolling-sharpe-chart",
        config={"displayModeBar": True},
        style={"height": "300px"},
    )


def build_rolling_drawdown_chart() -> dcc.Graph:
    """Rolling drawdown chart placeholder (ADV-03)."""
    return dcc.Graph(
        id="rolling-drawdown-chart",
        config={"displayModeBar": True},
        style={"height": "300px"},
    )


def build_breakdown_hour_count_chart() -> dcc.Graph:
    """Trade count by hour chart (ADV-04)."""
    return dcc.Graph(
        id="breakdown-hour-count-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_breakdown_hour_pnl_chart() -> dcc.Graph:
    """Trade PnL by hour chart (ADV-04)."""
    return dcc.Graph(
        id="breakdown-hour-pnl-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_breakdown_weekday_count_chart() -> dcc.Graph:
    """Trade count by weekday chart (ADV-05)."""
    return dcc.Graph(
        id="breakdown-weekday-count-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_breakdown_weekday_pnl_chart() -> dcc.Graph:
    """Trade PnL by weekday chart (ADV-05)."""
    return dcc.Graph(
        id="breakdown-weekday-pnl-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_breakdown_session_count_chart() -> dcc.Graph:
    """Trade count by session chart (ADV-06)."""
    return dcc.Graph(
        id="breakdown-session-count-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_breakdown_session_pnl_chart() -> dcc.Graph:
    """Trade PnL by session chart (ADV-06)."""
    return dcc.Graph(
        id="breakdown-session-pnl-chart",
        config={"displayModeBar": True},
        style={"height": "280px"},
    )


def build_mae_chart() -> dcc.Graph:
    """MAE scatter plot (ADV-07)."""
    return dcc.Graph(
        id="mae-chart",
        config={"displayModeBar": True},
        style={"height": "350px"},
    )


def build_mfe_chart() -> dcc.Graph:
    """MFE scatter plot (ADV-08)."""
    return dcc.Graph(
        id="mfe-chart",
        config={"displayModeBar": True},
        style={"height": "350px"},
    )


def build_commission_sweep_chart() -> dcc.Graph:
    """Commission sensitivity sweep chart (ADV-09)."""
    return dcc.Graph(
        id="commission-sweep-chart",
        config={"displayModeBar": True},
        style={"height": "400px"},
    )


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------

def _build_overview_tab() -> dbc.Tab:
    """Tab 1: Overview — existing charts and KPIs."""
    return dbc.Tab(
        label="Overview",
        tab_id="tab-overview",
        children=html.Div([
            build_kpi_panel(),

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
        ], className="mt-3"),
    )


def _build_analytics_tab() -> dbc.Tab:
    """Tab 2: Advanced Analytics — Monthly Heatmap, Rolling Sharpe/DD."""
    return dbc.Tab(
        label="Advanced Analytics",
        tab_id="tab-analytics",
        children=html.Div([
            # Rolling window selector
            dbc.Row([
                dbc.Col([
                    html.Label("Rolling Window", className="fw-bold mb-1"),
                    dcc.Dropdown(
                        id="rolling-window-selector",
                        options=[
                            {"label": "20 Bars", "value": 20},
                            {"label": "60 Bars", "value": 60},
                            {"label": "90 Bars", "value": 90},
                            {"label": "252 Bars", "value": 252},
                        ],
                        value=20,
                        clearable=False,
                    ),
                ], md=3),
            ], className="mb-3"),

            # Monthly Returns Heatmap
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Monthly Returns Heatmap"),
                        dbc.CardBody(build_monthly_heatmap_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=12),
            ]),

            # Rolling Sharpe + Rolling Drawdown
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Rolling Sharpe Ratio"),
                        dbc.CardBody(build_rolling_sharpe_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Rolling Max Drawdown"),
                        dbc.CardBody(build_rolling_drawdown_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),
        ], className="mt-3"),
    )


def _build_trade_analysis_tab() -> dbc.Tab:
    """Tab 3: Trade Analysis — Breakdown + MAE/MFE."""
    return dbc.Tab(
        label="Trade Analysis",
        tab_id="tab-trades",
        children=html.Div([
            # Breakdown by Hour (ADV-04)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade Count by Hour"),
                        dbc.CardBody(build_breakdown_hour_count_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade PnL by Hour"),
                        dbc.CardBody(build_breakdown_hour_pnl_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),

            # Breakdown by Weekday (ADV-05)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade Count by Weekday"),
                        dbc.CardBody(build_breakdown_weekday_count_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade PnL by Weekday"),
                        dbc.CardBody(build_breakdown_weekday_pnl_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),

            # Breakdown by Session (ADV-06)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade Count by Session"),
                        dbc.CardBody(build_breakdown_session_count_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("Trade PnL by Session"),
                        dbc.CardBody(build_breakdown_session_pnl_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),

            # MAE/MFE (ADV-07/08)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("MAE — Max Adverse Excursion"),
                        dbc.CardBody(build_mae_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader("MFE — Max Favorable Excursion"),
                        dbc.CardBody(build_mfe_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=6),
            ]),
        ], className="mt-3"),
    )


def _build_sensitivity_tab() -> dbc.Tab:
    """Tab 4: Sensitivity — Parameter Sweep + Commission Sweep."""
    return dbc.Tab(
        label="Sensitivity",
        tab_id="tab-sensitivity",
        children=html.Div([
            # Parameter Sweep (existing)
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

            # Commission Sensitivity Sweep (ADV-09)
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardHeader([
                            html.Span("Commission Sensitivity Sweep"),
                            dbc.Button(
                                "Run Commission Sweep",
                                id="run-commission-sweep-btn",
                                color="secondary",
                                size="sm",
                                className="float-end",
                            ),
                        ]),
                        dbc.CardBody(build_commission_sweep_chart()),
                    ], className="shadow-sm mb-3"),
                ], md=12),
            ]),
        ], className="mt-3"),
    )


# ---------------------------------------------------------------------------
# Main layout builder
# ---------------------------------------------------------------------------

def build_layout() -> html.Div:
    """Build the complete dashboard layout with tabs."""
    return html.Div([
        # Hidden store for backtest results (shared between tabs)
        dcc.Store(id="backtest-result-store"),

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

            # Tabbed content
            dbc.Tabs(
                id="dashboard-tabs",
                active_tab="tab-overview",
                children=[
                    _build_overview_tab(),
                    _build_analytics_tab(),
                    _build_trade_analysis_tab(),
                    _build_sensitivity_tab(),
                ],
            ),

        ], fluid=True),
    ])
