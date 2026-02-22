"""
callbacks.py — Dash callbacks for apex-backtest dashboard.

Handles:
- Running backtests on button click
- Updating KPI cards from MetricsResult
- Building candlestick chart with trade markers (DASH-01)
- Building equity curve (DASH-02)
- Building drawdown chart (DASH-03)
- Parameter sweep heatmap (DASH-06)
- Monthly returns heatmap (ADV-01)
- Rolling Sharpe/Drawdown (ADV-02/03)
- Trade breakdown charts (ADV-04/05/06)
- MAE/MFE scatter plots (ADV-07/08)
- Commission sensitivity sweep (ADV-09)
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from decimal import Decimal
from typing import Optional

import plotly.graph_objects as go
from plotly.subplots import make_subplots
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
    "smc": ("src.strategy.smc.smc_strategy", "SMCStrategy"),
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
    "smc": {
        "swing_strength": [2, 3, 4],
        "atr_period": [10, 14, 20],
        "atr_mult_threshold": [1.0, 1.5, 2.0],
        "warmup_bars": [20, 30, 50],
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


# ---------------------------------------------------------------------------
# Chart builders — Overview (v1.0)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Chart builders — Phase 9: Advanced Analytics
# ---------------------------------------------------------------------------

def build_monthly_heatmap(monthly_returns: dict) -> go.Figure:
    """Build monthly returns heatmap (ADV-01).

    monthly_returns: dict[year][month] = return_pct (Decimal).
    """
    fig = go.Figure()

    if not monthly_returns:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "Run a backtest first",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    years = sorted(monthly_returns.keys())
    month_labels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    z_grid = []
    text_grid = []
    for year in years:
        row = []
        text_row = []
        for month in range(1, 13):
            val = monthly_returns.get(year, {}).get(month)
            if val is not None:
                fval = float(val)
                row.append(fval)
                text_row.append(f"{fval:.1f}%")
            else:
                row.append(None)
                text_row.append("")
        z_grid.append(row)
        text_grid.append(text_row)

    fig.add_trace(go.Heatmap(
        z=z_grid,
        x=month_labels,
        y=[str(y) for y in years],
        colorscale="RdYlGn",
        zmid=0,
        colorbar={"title": "Return %"},
        text=text_grid,
        texttemplate="%{text}",
        hovertemplate="Year: %{y}<br>Month: %{x}<br>Return: %{z:.2f}%<extra></extra>",
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 10, "b": 40},
        xaxis_title="Month",
        yaxis_title="Year",
    )
    return fig


def build_rolling_sharpe_figure(rolling_data: list[dict]) -> go.Figure:
    """Build rolling Sharpe ratio time series (ADV-02)."""
    fig = go.Figure()

    if not rolling_data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "Not enough data for rolling window",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    timestamps = [d["timestamp"] for d in rolling_data]
    values = [d["rolling_sharpe"] for d in rolling_data]

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=values,
        mode="lines",
        name="Rolling Sharpe",
        line={"color": "#2196F3", "width": 2},
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Sharpe Ratio",
        xaxis_title="",
    )
    return fig


def build_rolling_drawdown_figure(rolling_data: list[dict]) -> go.Figure:
    """Build rolling max drawdown time series (ADV-03)."""
    fig = go.Figure()

    if not rolling_data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "Not enough data for rolling window",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    timestamps = [d["timestamp"] for d in rolling_data]
    values = [d["rolling_drawdown_pct"] for d in rolling_data]

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=values,
        mode="lines",
        name="Rolling Drawdown %",
        fill="tozeroy",
        line={"color": "#FF5722", "width": 2},
        fillcolor="rgba(255, 87, 34, 0.15)",
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Drawdown %",
        xaxis_title="",
    )
    return fig


def _build_breakdown_count_figure(
    data: list[dict],
    x_key: str,
    title: str,
) -> go.Figure:
    """Build a bar chart for trade count breakdown."""
    fig = go.Figure()

    if not data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "No trades to analyze",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    x_vals = [str(d[x_key]) for d in data]
    wins = [d["win_count"] for d in data]
    losses = [d["loss_count"] for d in data]

    fig.add_trace(go.Bar(
        x=x_vals, y=wins, name="Wins",
        marker_color="#4CAF50",
    ))
    fig.add_trace(go.Bar(
        x=x_vals, y=losses, name="Losses",
        marker_color="#F44336",
    ))

    fig.update_layout(
        barmode="stack",
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Trade Count",
        legend={"orientation": "h", "y": 1.1},
    )
    return fig


def _build_breakdown_pnl_figure(
    data: list[dict],
    x_key: str,
    title: str,
) -> go.Figure:
    """Build a bar chart for PnL breakdown."""
    fig = go.Figure()

    if not data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "No trades to analyze",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    x_vals = [str(d[x_key]) for d in data]
    pnls = [float(d["total_pnl"]) for d in data]
    colors = ["#4CAF50" if p >= 0 else "#F44336" for p in pnls]

    fig.add_trace(go.Bar(
        x=x_vals, y=pnls, name="PnL",
        marker_color=colors,
    ))

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="PnL ($)",
    )
    return fig


def build_mae_figure(mae_mfe_data: list[dict]) -> go.Figure:
    """Build MAE scatter plot (ADV-07)."""
    fig = go.Figure()

    if not mae_mfe_data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "No trades to analyze",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    wins = [d for d in mae_mfe_data if d["is_win"]]
    losses = [d for d in mae_mfe_data if not d["is_win"]]

    if wins:
        fig.add_trace(go.Scatter(
            x=[float(d["mae"]) for d in wins],
            y=[float(d["pnl"]) for d in wins],
            mode="markers",
            name="Wins",
            marker={"color": "#4CAF50", "size": 10, "opacity": 0.7},
        ))

    if losses:
        fig.add_trace(go.Scatter(
            x=[float(d["mae"]) for d in losses],
            y=[float(d["pnl"]) for d in losses],
            mode="markers",
            name="Losses",
            marker={"color": "#F44336", "size": 10, "opacity": 0.7},
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 40},
        xaxis_title="Max Adverse Excursion ($)",
        yaxis_title="Trade PnL ($)",
    )
    return fig


def build_mfe_figure(mae_mfe_data: list[dict]) -> go.Figure:
    """Build MFE scatter plot (ADV-08)."""
    fig = go.Figure()

    if not mae_mfe_data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "No trades to analyze",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    wins = [d for d in mae_mfe_data if d["is_win"]]
    losses = [d for d in mae_mfe_data if not d["is_win"]]

    if wins:
        fig.add_trace(go.Scatter(
            x=[float(d["mfe"]) for d in wins],
            y=[float(d["pnl"]) for d in wins],
            mode="markers",
            name="Wins",
            marker={"color": "#4CAF50", "size": 10, "opacity": 0.7},
        ))

    if losses:
        fig.add_trace(go.Scatter(
            x=[float(d["mfe"]) for d in losses],
            y=[float(d["pnl"]) for d in losses],
            mode="markers",
            name="Losses",
            marker={"color": "#F44336", "size": 10, "opacity": 0.7},
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 40},
        xaxis_title="Max Favorable Excursion ($)",
        yaxis_title="Trade PnL ($)",
    )
    return fig


def build_commission_sweep_figure(sweep_data: list[dict]) -> go.Figure:
    """Build commission sensitivity sweep chart (ADV-09).

    Shows 4 metrics across friction multipliers as subplots.
    """
    if not sweep_data:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            annotations=[{
                "text": "Click 'Run Commission Sweep' to start",
                "xref": "paper", "yref": "paper",
                "x": 0.5, "y": 0.5, "showarrow": False,
                "font": {"size": 14},
            }],
        )
        return fig

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=["Sharpe Ratio", "Net PnL ($)", "Win Rate (%)", "Max Drawdown (%)"],
    )

    x_vals = [f"{d['multiplier']}x" for d in sweep_data]

    # Sharpe
    fig.add_trace(go.Bar(
        x=x_vals,
        y=[d["sharpe"] for d in sweep_data],
        marker_color="#2196F3",
        name="Sharpe",
        showlegend=False,
    ), row=1, col=1)

    # Net PnL
    pnl_colors = ["#4CAF50" if d["net_pnl"] >= 0 else "#F44336" for d in sweep_data]
    fig.add_trace(go.Bar(
        x=x_vals,
        y=[d["net_pnl"] for d in sweep_data],
        marker_color=pnl_colors,
        name="PnL",
        showlegend=False,
    ), row=1, col=2)

    # Win Rate
    fig.add_trace(go.Bar(
        x=x_vals,
        y=[d["win_rate"] for d in sweep_data],
        marker_color="#FF9800",
        name="Win Rate",
        showlegend=False,
    ), row=2, col=1)

    # Max DD
    fig.add_trace(go.Bar(
        x=x_vals,
        y=[d["max_dd_pct"] for d in sweep_data],
        marker_color="#F44336",
        name="Max DD",
        showlegend=False,
    ), row=2, col=2)

    fig.update_layout(
        template="plotly_dark",
        height=400,
        margin={"l": 40, "r": 20, "t": 40, "b": 30},
    )
    return fig


def _format_decimal(val: Decimal, decimals: int = 2) -> str:
    """Format Decimal for display."""
    return f"{float(val):,.{decimals}f}"


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_callbacks(app) -> None:
    """Register all Dash callbacks on the app."""

    # ------------------------------------------------------------------
    # Main backtest callback — runs on button click, updates all tabs
    # ------------------------------------------------------------------

    @app.callback(
        [
            # Overview tab outputs
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
            # Store backtest result for other tabs
            Output("backtest-result-store", "data"),
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
            return [no_update] * 15

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
            return [empty_fig, empty_fig, empty_fig] + ["--"] * 10 + [error or "", None]

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

        # Serialize result for store (equity_log + fill_log summary)
        store_data = _serialize_result(result, strategy, timeframe, symbol)

        return [candle_fig, equity_fig, dd_fig] + kpi_values + ["", store_data]

    # ------------------------------------------------------------------
    # Advanced Analytics tab — updates when store data or window changes
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output("monthly-heatmap-chart", "figure"),
            Output("rolling-sharpe-chart", "figure"),
            Output("rolling-drawdown-chart", "figure"),
        ],
        [
            Input("backtest-result-store", "data"),
            Input("rolling-window-selector", "value"),
        ],
    )
    def update_analytics_tab(store_data, window):
        """Update advanced analytics charts from stored backtest data."""
        if not store_data:
            empty = go.Figure()
            empty.update_layout(template="plotly_dark")
            return [empty, empty, empty]

        equity_log, fill_log, timeframe = _deserialize_result(store_data)

        from src.analytics import (
            compute_monthly_returns,
            compute_rolling_sharpe,
            compute_rolling_drawdown,
        )

        monthly = compute_monthly_returns(equity_log)
        rolling_s = compute_rolling_sharpe(equity_log, window=window or 20, timeframe=timeframe)
        rolling_d = compute_rolling_drawdown(equity_log, window=window or 20)

        return [
            build_monthly_heatmap(monthly),
            build_rolling_sharpe_figure(rolling_s),
            build_rolling_drawdown_figure(rolling_d),
        ]

    # ------------------------------------------------------------------
    # Trade Analysis tab — updates when store data changes
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output("breakdown-hour-count-chart", "figure"),
            Output("breakdown-hour-pnl-chart", "figure"),
            Output("breakdown-weekday-count-chart", "figure"),
            Output("breakdown-weekday-pnl-chart", "figure"),
            Output("breakdown-session-count-chart", "figure"),
            Output("breakdown-session-pnl-chart", "figure"),
            Output("mae-chart", "figure"),
            Output("mfe-chart", "figure"),
        ],
        Input("backtest-result-store", "data"),
    )
    def update_trade_analysis_tab(store_data):
        """Update trade analysis charts from stored backtest data."""
        if not store_data:
            empty = go.Figure()
            empty.update_layout(template="plotly_dark")
            return [empty] * 8

        equity_log, fill_log, timeframe = _deserialize_result(store_data)

        from src.analytics import compute_trade_breakdown, compute_mae_mfe

        breakdown = compute_trade_breakdown(fill_log)
        mae_mfe = compute_mae_mfe(equity_log, fill_log)

        return [
            _build_breakdown_count_figure(breakdown["by_hour"], "hour", "Count by Hour"),
            _build_breakdown_pnl_figure(breakdown["by_hour"], "hour", "PnL by Hour"),
            _build_breakdown_count_figure(breakdown["by_weekday"], "weekday_name", "Count by Weekday"),
            _build_breakdown_pnl_figure(breakdown["by_weekday"], "weekday_name", "PnL by Weekday"),
            _build_breakdown_count_figure(breakdown["by_session"], "session", "Count by Session"),
            _build_breakdown_pnl_figure(breakdown["by_session"], "session", "PnL by Session"),
            build_mae_figure(mae_mfe),
            build_mfe_figure(mae_mfe),
        ]

    # ------------------------------------------------------------------
    # Sweep parameter update callback
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Parameter Sweep callback
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Commission Sensitivity Sweep callback (ADV-09)
    # ------------------------------------------------------------------

    @app.callback(
        Output("commission-sweep-chart", "figure"),
        Input("run-commission-sweep-btn", "n_clicks"),
        [
            State("strategy-selector", "value"),
            State("timeframe-selector", "value"),
            State("symbol-input", "value"),
        ],
        prevent_initial_call=True,
    )
    def run_commission_sweep_callback(n_clicks, strategy, timeframe, symbol):
        """Run commission sensitivity sweep."""
        if not n_clicks or not symbol:
            return no_update

        from src.analytics import run_commission_sweep

        sweep_data = run_commission_sweep(symbol, strategy, timeframe)
        return build_commission_sweep_figure(sweep_data)


# ---------------------------------------------------------------------------
# Serialization helpers for dcc.Store
# ---------------------------------------------------------------------------

def _serialize_result(
    result: BacktestResult,
    strategy: str,
    timeframe: str,
    symbol: str,
) -> dict:
    """Serialize BacktestResult for dcc.Store (JSON-compatible)."""
    equity_data = []
    for entry in result.equity_log:
        e = {
            "timestamp": entry["timestamp"].isoformat(),
            "equity": str(entry["equity"]),
            "cash": str(entry["cash"]),
        }
        if "price" in entry:
            e["price"] = str(entry["price"])
        equity_data.append(e)

    fill_data = []
    for fill in result.fill_log:
        fill_data.append({
            "symbol": fill.symbol,
            "timestamp": fill.timestamp.isoformat(),
            "side": fill.side.value,
            "quantity": str(fill.quantity),
            "fill_price": str(fill.fill_price),
            "commission": str(fill.commission),
            "slippage": str(fill.slippage),
            "spread_cost": str(fill.spread_cost),
        })

    return {
        "equity_log": equity_data,
        "fill_log": fill_data,
        "strategy": strategy,
        "timeframe": timeframe,
        "symbol": symbol,
    }


def _deserialize_result(
    store_data: dict,
) -> tuple[list[dict], list[FillEvent], str]:
    """Deserialize stored data back to equity_log and fill_log."""
    equity_log = []
    for e in store_data.get("equity_log", []):
        entry = {
            "timestamp": datetime.fromisoformat(e["timestamp"]),
            "equity": Decimal(e["equity"]),
            "cash": Decimal(e["cash"]),
        }
        if "price" in e:
            entry["price"] = Decimal(e["price"])
        equity_log.append(entry)

    fill_log = []
    for f in store_data.get("fill_log", []):
        fill_log.append(FillEvent(
            symbol=f["symbol"],
            timestamp=datetime.fromisoformat(f["timestamp"]),
            side=OrderSide(f["side"]),
            quantity=Decimal(f["quantity"]),
            fill_price=Decimal(f["fill_price"]),
            commission=Decimal(f["commission"]),
            slippage=Decimal(f["slippage"]),
            spread_cost=Decimal(f["spread_cost"]),
        ))

    timeframe = store_data.get("timeframe", "1d")
    return equity_log, fill_log, timeframe
