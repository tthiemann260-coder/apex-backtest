"""
callbacks.py — Dash callbacks for apex-backtest dashboard.

Handles:
- Running backtests on button click
- Updating KPI cards from MetricsResult
- Building candlestick chart with trade markers (DASH-01)
- Building equity curve (DASH-02)
- Building drawdown chart (DASH-03)
- Parameter sweep heatmap (DASH-06)
"""

from __future__ import annotations

import traceback
from datetime import datetime
from decimal import Decimal
from typing import Optional

import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, no_update

from src.data_handler import DataHandler
from src.engine import create_engine, BacktestResult
from src.events import FillEvent, OrderSide
from src.metrics import compute, MetricsResult, MetricsComputationError


# Strategy import mapping
STRATEGY_MAP = {
    "reversal": ("src.strategy.reversal", "ReversalStrategy"),
    "breakout": ("src.strategy.breakout", "BreakoutStrategy"),
    "fvg": ("src.strategy.fvg", "FVGStrategy"),
}

# Default strategy params for sweep
SWEEP_PARAMS = {
    "reversal": {
        "rsi_period": [10, 14, 20, 25, 30],
        "rsi_oversold": [20, 25, 30, 35],
        "rsi_overbought": [65, 70, 75, 80],
        "sma_period": [10, 15, 20, 30, 50],
    },
    "breakout": {
        "lookback": [10, 15, 20, 25, 30, 40],
        "atr_period": [10, 14, 20],
        "volume_factor": [1.0, 1.2, 1.5, 2.0],
    },
    "fvg": {
        "min_gap_size_pct": [0.05, 0.1, 0.15, 0.2, 0.3],
        "max_open_gaps": [3, 5, 7, 10],
    },
}


def _import_strategy(strategy_name: str):
    """Dynamically import a strategy class."""
    import importlib
    module_path, class_name = STRATEGY_MAP[strategy_name]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _run_backtest(
    symbol: str,
    strategy_name: str,
    timeframe: str,
    params: Optional[dict] = None,
) -> tuple[Optional[BacktestResult], Optional[MetricsResult], Optional[str]]:
    """Run a single backtest and return results + metrics."""
    try:
        dh = DataHandler(symbol=symbol, source="yfinance", timeframe=timeframe)
        strategy_cls = _import_strategy(strategy_name)

        kwargs = {"symbol": symbol, "timeframe": timeframe}
        if params:
            kwargs["params"] = params
        strategy = strategy_cls(**kwargs)

        engine = create_engine(dh, strategy)
        result = engine.run()

        if not result.equity_log:
            return result, None, "No equity data produced"

        metrics = compute(
            result.equity_log,
            result.fill_log,
            timeframe=timeframe,
        )
        return result, metrics, None
    except Exception as e:
        return None, None, f"Error: {e}\n{traceback.format_exc()}"


def build_candlestick_figure(
    equity_log: list[dict],
    fill_log: list[FillEvent],
) -> go.Figure:
    """Build candlestick chart with buy/sell markers (DASH-01)."""
    fig = go.Figure()

    if not equity_log:
        fig.update_layout(title="No data available")
        return fig

    timestamps = [e["timestamp"] for e in equity_log]
    prices = [float(e.get("price", e["equity"])) for e in equity_log]

    # If we have OHLC data in equity_log, use candlestick
    has_ohlc = all(
        k in equity_log[0]
        for k in ("open", "high", "low", "close")
    )

    if has_ohlc:
        fig.add_trace(go.Candlestick(
            x=timestamps,
            open=[float(e["open"]) for e in equity_log],
            high=[float(e["high"]) for e in equity_log],
            low=[float(e["low"]) for e in equity_log],
            close=[float(e["close"]) for e in equity_log],
            name="Price",
        ))
    else:
        # Fallback: line chart of price
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=prices,
            mode="lines",
            name="Price",
            line={"color": "#2196F3", "width": 1.5},
        ))

    # Buy markers (green triangle up)
    buy_fills = [f for f in fill_log if f.side == OrderSide.BUY]
    if buy_fills:
        fig.add_trace(go.Scatter(
            x=[f.timestamp for f in buy_fills],
            y=[float(f.fill_price) for f in buy_fills],
            mode="markers",
            name="BUY",
            marker={
                "symbol": "triangle-up",
                "size": 12,
                "color": "#4CAF50",
                "line": {"width": 1, "color": "#1B5E20"},
            },
        ))

    # Sell markers (red triangle down)
    sell_fills = [f for f in fill_log if f.side == OrderSide.SELL]
    if sell_fills:
        fig.add_trace(go.Scatter(
            x=[f.timestamp for f in sell_fills],
            y=[float(f.fill_price) for f in sell_fills],
            mode="markers",
            name="SELL",
            marker={
                "symbol": "triangle-down",
                "size": 12,
                "color": "#F44336",
                "line": {"width": 1, "color": "#B71C1C"},
            },
        ))

    fig.update_layout(
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 30, "b": 30},
        legend={"orientation": "h", "y": 1.1},
        xaxis_title="",
        yaxis_title="Price",
    )
    return fig


def build_equity_figure(equity_log: list[dict]) -> go.Figure:
    """Build equity curve chart (DASH-02)."""
    fig = go.Figure()

    if not equity_log:
        fig.update_layout(title="No data")
        return fig

    timestamps = [e["timestamp"] for e in equity_log]
    equities = [float(e["equity"]) for e in equity_log]

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=equities,
        mode="lines",
        name="Equity",
        fill="tozeroy",
        line={"color": "#4CAF50", "width": 2},
        fillcolor="rgba(76, 175, 80, 0.15)",
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Equity ($)",
        xaxis_title="",
    )
    return fig


def build_drawdown_figure(equity_log: list[dict]) -> go.Figure:
    """Build drawdown chart (DASH-03)."""
    fig = go.Figure()

    if not equity_log:
        fig.update_layout(title="No data")
        return fig

    equities = [float(e["equity"]) for e in equity_log]
    timestamps = [e["timestamp"] for e in equity_log]

    # Compute running drawdown
    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd_pct = ((eq - peak) / peak * 100) if peak > 0 else 0
        drawdowns.append(dd_pct)

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=drawdowns,
        mode="lines",
        name="Drawdown %",
        fill="tozeroy",
        line={"color": "#F44336", "width": 2},
        fillcolor="rgba(244, 67, 54, 0.2)",
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Drawdown %",
        xaxis_title="",
    )
    return fig


def build_heatmap_figure(
    sweep_results: list[dict],
    param1_name: str,
    param2_name: str,
    metric: str = "sharpe_ratio",
) -> go.Figure:
    """Build parameter sweep heatmap (DASH-06)."""
    fig = go.Figure()

    if not sweep_results:
        fig.update_layout(title="No sweep data — click 'Run Sweep'")
        return fig

    # Extract unique param values
    p1_vals = sorted(set(r[param1_name] for r in sweep_results))
    p2_vals = sorted(set(r[param2_name] for r in sweep_results))

    # Build 2D grid
    z_grid = []
    for p2 in p2_vals:
        row = []
        for p1 in p1_vals:
            match = [r for r in sweep_results
                     if r[param1_name] == p1 and r[param2_name] == p2]
            if match:
                row.append(float(match[0].get(metric, 0)))
            else:
                row.append(0.0)
        z_grid.append(row)

    fig.add_trace(go.Heatmap(
        z=z_grid,
        x=[str(v) for v in p1_vals],
        y=[str(v) for v in p2_vals],
        colorscale="RdYlGn",
        colorbar={"title": metric.replace("_", " ").title()},
        text=[[f"{v:.2f}" for v in row] for row in z_grid],
        texttemplate="%{text}",
        hovertemplate=(
            f"{param1_name}: %{{x}}<br>"
            f"{param2_name}: %{{y}}<br>"
            f"{metric}: %{{z:.3f}}<extra></extra>"
        ),
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 30, "b": 50},
        xaxis_title=param1_name,
        yaxis_title=param2_name,
    )
    return fig


def _format_decimal(val: Decimal, decimals: int = 2) -> str:
    """Format Decimal for display."""
    return f"{float(val):,.{decimals}f}"


def register_callbacks(app) -> None:
    """Register all Dash callbacks on the app."""

    @app.callback(
        [
            Output("candlestick-chart", "figure"),
            Output("equity-chart", "figure"),
            Output("drawdown-chart", "figure"),
            Output("kpi-net-pnl", "children"),
            Output("kpi-total-return", "children"),
            Output("kpi-sharpe", "children"),
            Output("kpi-sortino", "children"),
            Output("kpi-max-dd", "children"),
            Output("kpi-calmar", "children"),
            Output("kpi-win-rate", "children"),
            Output("kpi-profit-factor", "children"),
            Output("kpi-trade-count", "children"),
            Output("kpi-exposure", "children"),
            Output("loading-output", "children"),
        ],
        Input("run-backtest-btn", "n_clicks"),
        [
            State("strategy-selector", "value"),
            State("timeframe-selector", "value"),
            State("symbol-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def run_backtest_callback(n_clicks, strategy, timeframe, symbol):
        """Run backtest and update all charts + KPIs."""
        if not n_clicks or not symbol:
            return [no_update] * 14

        result, metrics, error = _run_backtest(symbol, strategy, timeframe)

        if error or result is None:
            empty_fig = go.Figure()
            empty_fig.update_layout(
                template="plotly_dark",
                annotations=[{
                    "text": error or "Unknown error",
                    "xref": "paper", "yref": "paper",
                    "x": 0.5, "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 14, "color": "red"},
                }],
            )
            return [empty_fig, empty_fig, empty_fig] + ["--"] * 10 + [error or ""]

        # Build charts
        candle_fig = build_candlestick_figure(result.equity_log, result.fill_log)
        equity_fig = build_equity_figure(result.equity_log)
        dd_fig = build_drawdown_figure(result.equity_log)

        # KPI values
        if metrics:
            kpi_values = [
                f"${_format_decimal(metrics.net_pnl)}",
                f"{_format_decimal(metrics.total_return_pct)}%",
                _format_decimal(metrics.sharpe_ratio, 3),
                _format_decimal(metrics.sortino_ratio, 3),
                f"{_format_decimal(metrics.max_drawdown_pct)}%",
                _format_decimal(metrics.calmar_ratio, 3),
                f"{_format_decimal(metrics.win_rate)}%",
                _format_decimal(metrics.profit_factor, 2),
                str(metrics.trade_count),
                f"{_format_decimal(metrics.total_exposure_pct)}%",
            ]
        else:
            kpi_values = ["--"] * 10

        return [candle_fig, equity_fig, dd_fig] + kpi_values + [""]

    @app.callback(
        [
            Output("sweep-param1", "options"),
            Output("sweep-param2", "options"),
        ],
        Input("strategy-selector", "value"),
    )
    def update_sweep_params(strategy):
        """Update sweep parameter dropdowns based on selected strategy."""
        if not strategy or strategy not in SWEEP_PARAMS:
            return [], []

        params = list(SWEEP_PARAMS[strategy].keys())
        options = [{"label": p, "value": p} for p in params]
        return options, options

    @app.callback(
        Output("heatmap-chart", "figure"),
        Input("run-sweep-btn", "n_clicks"),
        [
            State("strategy-selector", "value"),
            State("timeframe-selector", "value"),
            State("symbol-input", "value"),
            State("sweep-param1", "value"),
            State("sweep-param2", "value"),
        ],
        prevent_initial_call=True,
    )
    def run_sweep_callback(n_clicks, strategy, timeframe, symbol, param1, param2):
        """Run parameter sweep and build heatmap."""
        if not n_clicks or not param1 or not param2 or param1 == param2:
            empty = go.Figure()
            empty.update_layout(
                template="plotly_dark",
                annotations=[{
                    "text": "Select two different parameters and click 'Run Sweep'",
                    "xref": "paper", "yref": "paper",
                    "x": 0.5, "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 14},
                }],
            )
            return empty

        sweep_results = []
        p1_values = SWEEP_PARAMS.get(strategy, {}).get(param1, [])
        p2_values = SWEEP_PARAMS.get(strategy, {}).get(param2, [])

        for v1 in p1_values:
            for v2 in p2_values:
                params = {param1: v1, param2: v2}
                _, metrics, error = _run_backtest(symbol, strategy, timeframe, params)
                entry = {param1: v1, param2: v2}
                if metrics:
                    entry["sharpe_ratio"] = metrics.sharpe_ratio
                    entry["sortino_ratio"] = metrics.sortino_ratio
                    entry["total_return_pct"] = metrics.total_return_pct
                    entry["max_drawdown_pct"] = metrics.max_drawdown_pct
                else:
                    entry["sharpe_ratio"] = Decimal("0")
                    entry["sortino_ratio"] = Decimal("0")
                    entry["total_return_pct"] = Decimal("0")
                    entry["max_drawdown_pct"] = Decimal("0")
                sweep_results.append(entry)

        return build_heatmap_figure(sweep_results, param1, param2)
