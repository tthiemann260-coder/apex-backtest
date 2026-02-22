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
    "ict": ("src.strategy.smc.ict_strategy", "ICTStrategy"),
    "regime_ict": ("src.strategy.regime.gated_strategy", "create_regime_gated_ict"),
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
    "ict": {
        "swing_strength": [2, 3, 4],
        "atr_period": [10, 14, 20],
        "require_sweep": [True, False],
        "require_kill_zone": [True, False],
        "require_ote": [True, False],
    },
    "regime_ict": {
        "atr_period": [10, 14, 20],
        "adx_period": [10, 14, 20],
        "regime_lookback": [30, 50, 100],
        "require_sweep": [True, False],
    },
}


def _import_strategy(strategy_name: str):
    """Dynamically import a strategy class or factory function."""
    import importlib
    module_path, class_or_func_name = STRATEGY_MAP[strategy_name]
    module = importlib.import_module(module_path)
    return getattr(module, class_or_func_name)


def _run_backtest(
    symbol: str,
    strategy_name: str,
    timeframe: str,
    params: Optional[dict] = None,
) -> tuple[Optional[BacktestResult], Optional[MetricsResult], Optional[str], list[dict]]:
    """Run a single backtest and return results + metrics + regime_log."""
    try:
        dh = DataHandler(symbol=symbol, source="yfinance", timeframe=timeframe)
        strategy_cls = _import_strategy(strategy_name)

        kwargs = {"symbol": symbol, "timeframe": timeframe}
        if params:
            kwargs["params"] = params
        strategy = strategy_cls(**kwargs)

        engine = create_engine(dh, strategy)
        result = engine.run()

        # Capture regime_log before strategy goes out of scope
        regime_log = getattr(strategy, "regime_log", [])

        if not result.equity_log:
            return result, None, "No equity data produced", regime_log

        metrics = compute(
            result.equity_log,
            result.fill_log,
            timeframe=timeframe,
        )
        return result, metrics, None, regime_log
    except Exception as e:
        return None, None, f"Error: {e}\n{traceback.format_exc()}", []


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


# ---------------------------------------------------------------------------
# Chart builders — Phase 18: Regime Overlay
# ---------------------------------------------------------------------------

REGIME_COLORS = {
    "STRONG_TREND": "rgba(76, 175, 80, 0.12)",
    "MODERATE_TREND": "rgba(139, 195, 74, 0.12)",
    "WEAK_TREND": "rgba(255, 235, 59, 0.10)",
    "RANGING_NORMAL": "rgba(158, 158, 158, 0.10)",
    "RANGING_LOW": "rgba(33, 150, 243, 0.10)",
    "CHOPPY": "rgba(244, 67, 54, 0.12)",
}


def _add_regime_overlay(fig: go.Figure, regime_log: list[dict]) -> None:
    """Add colored vrect backgrounds for consecutive regime bands."""
    if not regime_log:
        return

    # Group consecutive same-regime entries into bands
    bands: list[tuple] = []
    current_regime = regime_log[0]["regime_type"]
    band_start = regime_log[0]["timestamp"]

    for entry in regime_log[1:]:
        if entry["regime_type"] != current_regime:
            bands.append((band_start, entry["timestamp"], current_regime))
            current_regime = entry["regime_type"]
            band_start = entry["timestamp"]
    bands.append((band_start, regime_log[-1]["timestamp"], current_regime))

    for start, end, regime in bands:
        color = REGIME_COLORS.get(regime, "rgba(0,0,0,0)")
        fig.add_vrect(
            x0=start, x1=end,
            fillcolor=color,
            layer="below",
            line_width=0,
        )


# ---------------------------------------------------------------------------
# Chart builders — Phase 18: Risk Dashboard
# ---------------------------------------------------------------------------

def build_heat_gauge_figure(
    equity_log: list[dict], fill_log: list[FillEvent],
) -> go.Figure:
    """Plotly Indicator gauge showing approximate portfolio heat."""
    fig = go.Figure()

    if not equity_log or not fill_log:
        fig.add_trace(go.Indicator(
            mode="gauge+number",
            value=0,
            title={"text": "Portfolio Heat %"},
            gauge={"axis": {"range": [0, 10]},
                   "bar": {"color": "#4CAF50"},
                   "steps": [
                       {"range": [0, 3], "color": "rgba(76,175,80,0.2)"},
                       {"range": [3, 6], "color": "rgba(255,152,0,0.2)"},
                       {"range": [6, 10], "color": "rgba(244,67,54,0.2)"},
                   ]},
        ))
        fig.update_layout(template="plotly_dark", margin={"l": 20, "r": 20, "t": 40, "b": 20})
        return fig

    # Approximate heat: sum of open position risk / equity
    final_equity = float(equity_log[-1]["equity"])
    if final_equity <= 0:
        heat_pct = 0
    else:
        # Count open exposure from fills
        positions: dict[str, float] = {}
        for fill in fill_log:
            sym = fill.symbol
            qty = float(fill.quantity)
            price = float(fill.fill_price)
            if fill.side == OrderSide.BUY:
                positions[sym] = positions.get(sym, 0) + qty * price
            else:
                positions[sym] = positions.get(sym, 0) - qty * price
        total_exposure = sum(abs(v) for v in positions.values())
        heat_pct = (total_exposure / final_equity) * 100 if final_equity > 0 else 0

    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=round(heat_pct, 1),
        title={"text": "Portfolio Heat %"},
        gauge={"axis": {"range": [0, max(10, heat_pct * 1.5)]},
               "bar": {"color": "#FF5722" if heat_pct > 6 else "#FF9800" if heat_pct > 3 else "#4CAF50"},
               "steps": [
                   {"range": [0, 3], "color": "rgba(76,175,80,0.2)"},
                   {"range": [3, 6], "color": "rgba(255,152,0,0.2)"},
                   {"range": [6, max(10, heat_pct * 1.5)], "color": "rgba(244,67,54,0.2)"},
               ]},
    ))
    fig.update_layout(template="plotly_dark", margin={"l": 20, "r": 20, "t": 40, "b": 20})
    return fig


def build_sizing_distribution_figure(fill_log: list[FillEvent]) -> go.Figure:
    """Histogram of position sizes from fill quantities."""
    fig = go.Figure()

    quantities = [float(f.quantity) for f in fill_log if f.side == OrderSide.BUY]
    if not quantities:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "No trades to analyze", "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    fig.add_trace(go.Histogram(
        x=quantities, nbinsx=20,
        marker_color="#2196F3",
        name="Position Size",
    ))
    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 40},
        xaxis_title="Position Size (shares)",
        yaxis_title="Frequency",
    )
    return fig


def build_daily_risk_usage_figure(fill_log: list[FillEvent]) -> go.Figure:
    """Bar chart: daily capital at risk."""
    fig = go.Figure()

    if not fill_log:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "No trades to analyze", "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    # Group BUY fills by calendar day
    daily_risk: dict[str, float] = {}
    for fill in fill_log:
        if fill.side == OrderSide.BUY:
            day = fill.timestamp.strftime("%Y-%m-%d")
            daily_risk[day] = daily_risk.get(day, 0) + float(fill.quantity * fill.fill_price)

    if not daily_risk:
        fig.update_layout(template="plotly_dark")
        return fig

    days = sorted(daily_risk.keys())
    values = [daily_risk[d] for d in days]

    fig.add_trace(go.Bar(
        x=days, y=values,
        marker_color="#FF9800",
        name="Daily Risk ($)",
    ))
    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 40},
        xaxis_title="Date",
        yaxis_title="Capital at Risk ($)",
    )
    return fig


def build_drawdown_scaling_figure(equity_log: list[dict]) -> go.Figure:
    """Line chart: DrawdownScaler.compute_scale() over time."""
    fig = go.Figure()

    if not equity_log or len(equity_log) < 2:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "Not enough data", "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    from src.risk_manager import DrawdownScaler
    scaler = DrawdownScaler()

    timestamps = []
    scales = []
    for i in range(len(equity_log)):
        timestamps.append(equity_log[i]["timestamp"])
        scale = float(scaler.compute_scale(equity_log[:i + 1]))
        scales.append(scale * 100)

    fig.add_trace(go.Scatter(
        x=timestamps, y=scales,
        mode="lines", name="Scale Factor %",
        line={"color": "#9C27B0", "width": 2},
        fill="tozeroy",
        fillcolor="rgba(156, 39, 176, 0.1)",
    ))
    fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Scale Factor %",
    )
    return fig


# ---------------------------------------------------------------------------
# Chart builders — Phase 18: Multi-Asset View
# ---------------------------------------------------------------------------

def build_multi_equity_figure(equity_log: list[dict]) -> go.Figure:
    """Overlaid per-symbol equity curves normalized to 100%.

    Pipeline: equity_log -> compute_per_symbol_equity() -> normalize -> go.Scatter
    """
    from src.multi_asset import compute_per_symbol_equity

    fig = go.Figure()
    per_symbol = compute_per_symbol_equity(equity_log)

    if not per_symbol:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "No multi-asset data", "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    colors = ["#4CAF50", "#2196F3", "#FF9800", "#F44336", "#9C27B0", "#00BCD4"]

    for i, symbol in enumerate(sorted(per_symbol.keys())):
        entries = per_symbol[symbol]
        if not entries:
            continue
        base_eq = float(entries[0]["equity"])
        if base_eq == 0:
            base_eq = 1
        timestamps = [e["timestamp"] for e in entries]
        normalized = [float(e["equity"]) / base_eq * 100 for e in entries]
        fig.add_trace(go.Scatter(
            x=timestamps, y=normalized,
            mode="lines", name=symbol,
            line={"color": colors[i % len(colors)], "width": 2},
        ))

    fig.add_hline(y=100, line_dash="dash", line_color="gray", opacity=0.5)
    fig.update_layout(
        template="plotly_dark",
        margin={"l": 40, "r": 20, "t": 10, "b": 30},
        yaxis_title="Normalized Equity (%)",
        legend={"orientation": "h", "y": 1.1},
    )
    return fig


def build_correlation_heatmap_figure(equity_log: list[dict]) -> go.Figure:
    """Square NxN correlation heatmap from last rolling window.

    Pipeline: equity_log -> compute_per_symbol_equity() ->
              compute_rolling_correlation() -> last-window pivot -> go.Heatmap
    """
    from src.multi_asset import compute_per_symbol_equity, compute_rolling_correlation

    fig = go.Figure()
    per_symbol = compute_per_symbol_equity(equity_log)
    sorted_symbols = sorted(per_symbol.keys())

    if len(sorted_symbols) < 2:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "Need >= 2 symbols for correlation",
                          "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    # Build aligned equity curves
    min_len = min(len(per_symbol[s]) for s in sorted_symbols)
    equity_curves: dict[str, list] = {}
    timestamps: list = []
    for sym in sorted_symbols:
        entries = per_symbol[sym][:min_len]
        equity_curves[sym] = [entry["equity"] for entry in entries]
        if not timestamps:
            timestamps = [entry["timestamp"] for entry in entries]

    window = min(60, min_len - 1) if min_len > 2 else 2
    corr_data = compute_rolling_correlation(equity_curves, timestamps, window=window)

    if not corr_data:
        fig.update_layout(
            template="plotly_dark",
            annotations=[{"text": "Not enough data for correlation",
                          "xref": "paper", "yref": "paper",
                          "x": 0.5, "y": 0.5, "showarrow": False, "font": {"size": 14}}],
        )
        return fig

    # Take last timestamp's correlations and pivot to NxN matrix
    last_ts = corr_data[-1]["timestamp"]
    last_corrs = {r["pair"]: float(r["correlation"]) for r in corr_data if r["timestamp"] == last_ts}

    n = len(sorted_symbols)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            pair_key = f"{sorted_symbols[i]}/{sorted_symbols[j]}"
            corr_val = last_corrs.get(pair_key, 0.0)
            matrix[i][j] = corr_val
            matrix[j][i] = corr_val

    fig.add_trace(go.Heatmap(
        z=matrix,
        x=sorted_symbols,
        y=sorted_symbols,
        colorscale="RdBu",
        zmid=0,
        zmin=-1, zmax=1,
        text=[[f"{v:.2f}" for v in row] for row in matrix],
        texttemplate="%{text}",
        hovertemplate="Row: %{y}<br>Col: %{x}<br>Corr: %{z:.3f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_dark",
        margin={"l": 60, "r": 20, "t": 10, "b": 40},
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

        result, metrics, error, regime_log = _run_backtest(symbol, strategy, timeframe)

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

        # Serialize result for store (equity_log + fill_log + regime_log)
        store_data = _serialize_result(result, strategy, timeframe, symbol, regime_log)

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

        equity_log, fill_log, timeframe, _ = _deserialize_result(store_data)

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

        equity_log, fill_log, timeframe, _ = _deserialize_result(store_data)

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
                _, metrics, error, _ = _run_backtest(symbol, strategy, timeframe, params)
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

    # ------------------------------------------------------------------
    # Regime Overlay callback — separate from main to avoid output clash
    # ------------------------------------------------------------------

    @app.callback(
        Output("candlestick-chart", "figure", allow_duplicate=True),
        [
            Input("regime-overlay-toggle", "value"),
            Input("backtest-result-store", "data"),
        ],
        prevent_initial_call=True,
    )
    def update_regime_overlay(toggle_on, store_data):
        """Rebuild candlestick chart with optional regime overlay."""
        if not store_data:
            return no_update

        equity_log, fill_log, timeframe, regime_log = _deserialize_result(store_data)
        fig = build_candlestick_figure(equity_log, fill_log)

        if toggle_on and regime_log:
            _add_regime_overlay(fig, regime_log)

        return fig

    # ------------------------------------------------------------------
    # Risk Dashboard tab — updates when store data changes
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output("heat-gauge-chart", "figure"),
            Output("sizing-distribution-chart", "figure"),
            Output("daily-risk-usage-chart", "figure"),
            Output("drawdown-scaling-chart", "figure"),
            Output("risk-kpi-heat", "children"),
            Output("risk-kpi-max-pos", "children"),
            Output("risk-kpi-dd-scale", "children"),
            Output("risk-kpi-budget", "children"),
        ],
        Input("backtest-result-store", "data"),
    )
    def update_risk_tab(store_data):
        """Update risk dashboard charts from stored backtest data."""
        if not store_data:
            empty = go.Figure()
            empty.update_layout(template="plotly_dark")
            return [empty] * 4 + ["--"] * 4

        equity_log, fill_log, timeframe, _ = _deserialize_result(store_data)

        heat_fig = build_heat_gauge_figure(equity_log, fill_log)
        sizing_fig = build_sizing_distribution_figure(fill_log)
        daily_fig = build_daily_risk_usage_figure(fill_log)
        dd_fig = build_drawdown_scaling_figure(equity_log)

        # KPI values
        final_eq = float(equity_log[-1]["equity"]) if equity_log else 0
        # Heat %
        positions: dict[str, float] = {}
        for fill in fill_log:
            qty = float(fill.quantity)
            price = float(fill.fill_price)
            if fill.side == OrderSide.BUY:
                positions[fill.symbol] = positions.get(fill.symbol, 0) + qty * price
            else:
                positions[fill.symbol] = positions.get(fill.symbol, 0) - qty * price
        total_exposure = sum(abs(v) for v in positions.values())
        heat_pct = (total_exposure / final_eq * 100) if final_eq > 0 else 0

        # Max concurrent positions (approximate from fill log)
        open_count = 0
        max_pos = 0
        for fill in fill_log:
            if fill.side == OrderSide.BUY:
                open_count += 1
            else:
                open_count = max(0, open_count - 1)
            max_pos = max(max_pos, open_count)

        # DD scale factor from last equity entry
        from src.risk_manager import DrawdownScaler
        scaler = DrawdownScaler()
        dd_scale = float(scaler.compute_scale(equity_log)) if equity_log else 1.0

        # Risk budget approximation
        budget_pct = min(heat_pct, 100.0)

        return [
            heat_fig, sizing_fig, daily_fig, dd_fig,
            f"{heat_pct:.1f}%",
            str(max_pos),
            f"{dd_scale:.2f}",
            f"{budget_pct:.1f}%",
        ]

    # ------------------------------------------------------------------
    # Multi-Asset callback — runs on button click
    # ------------------------------------------------------------------

    @app.callback(
        [
            Output("multi-equity-chart", "figure"),
            Output("correlation-heatmap-chart", "figure"),
            Output("multi-kpi-symbols", "children"),
            Output("multi-kpi-pnl", "children"),
            Output("multi-kpi-correlation", "children"),
        ],
        Input("run-multi-asset-btn", "n_clicks"),
        [
            State("multi-symbol-input", "value"),
            State("strategy-selector", "value"),
            State("timeframe-selector", "value"),
        ],
        prevent_initial_call=True,
    )
    def run_multi_asset_callback(n_clicks, symbols_str, strategy, timeframe):
        """Run multi-asset backtest and update charts + KPIs."""
        if not n_clicks or not symbols_str:
            return [no_update] * 5

        try:
            symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
            if len(symbols) < 2:
                empty = go.Figure()
                empty.update_layout(
                    template="plotly_dark",
                    annotations=[{"text": "Enter at least 2 symbols",
                                  "xref": "paper", "yref": "paper",
                                  "x": 0.5, "y": 0.5, "showarrow": False}],
                )
                return [empty, empty, str(len(symbols)), "--", "--"]

            # Build handlers + strategies per symbol
            handlers = {}
            strategies = {}
            strategy_cls = _import_strategy(strategy)
            for sym in symbols:
                handlers[sym] = DataHandler(symbol=sym, source="yfinance", timeframe=timeframe)
                strategies[sym] = strategy_cls(symbol=sym, timeframe=timeframe)

            from src.multi_asset import create_multi_asset_engine
            engine = create_multi_asset_engine(handlers=handlers, strategies=strategies)
            result = engine.run()

            # Build charts
            eq_fig = build_multi_equity_figure(result.equity_log)
            corr_fig = build_correlation_heatmap_figure(result.equity_log)

            # KPIs
            n_sym = str(len(symbols))
            pnl = f"${float(result.final_equity - Decimal('10000')):,.2f}"

            # Average correlation from last window
            from src.multi_asset import compute_per_symbol_equity, compute_rolling_correlation
            per_sym = compute_per_symbol_equity(result.equity_log)
            sorted_syms = sorted(per_sym.keys())
            avg_corr_str = "--"
            if len(sorted_syms) >= 2:
                min_len = min(len(per_sym[s]) for s in sorted_syms)
                if min_len > 2:
                    eq_curves = {s: [e["equity"] for e in per_sym[s][:min_len]] for s in sorted_syms}
                    ts = [e["timestamp"] for e in per_sym[sorted_syms[0]][:min_len]]
                    window = min(60, min_len - 1)
                    corr_data = compute_rolling_correlation(eq_curves, ts, window=window)
                    if corr_data:
                        last_ts = corr_data[-1]["timestamp"]
                        last_vals = [float(r["correlation"]) for r in corr_data if r["timestamp"] == last_ts]
                        if last_vals:
                            avg_corr_str = f"{sum(last_vals) / len(last_vals):.3f}"

            return [eq_fig, corr_fig, n_sym, pnl, avg_corr_str]

        except Exception as e:
            empty = go.Figure()
            empty.update_layout(
                template="plotly_dark",
                annotations=[{"text": f"Error: {e}",
                              "xref": "paper", "yref": "paper",
                              "x": 0.5, "y": 0.5, "showarrow": False,
                              "font": {"color": "red"}}],
            )
            return [empty, empty, "--", "--", "--"]


# ---------------------------------------------------------------------------
# Serialization helpers for dcc.Store
# ---------------------------------------------------------------------------

def _serialize_result(
    result: BacktestResult,
    strategy: str,
    timeframe: str,
    symbol: str,
    regime_log: Optional[list[dict]] = None,
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

    regime_data = []
    for r in (regime_log or []):
        regime_data.append({
            "timestamp": r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
            "regime_type": r["regime_type"],
            "adx": r["adx"],
            "vol_regime": r["vol_regime"],
        })

    return {
        "equity_log": equity_data,
        "fill_log": fill_data,
        "strategy": strategy,
        "timeframe": timeframe,
        "symbol": symbol,
        "regime_log": regime_data,
    }


def _deserialize_result(
    store_data: dict,
) -> tuple[list[dict], list[FillEvent], str, list[dict]]:
    """Deserialize stored data back to equity_log, fill_log, timeframe, regime_log."""
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

    regime_log = []
    for r in store_data.get("regime_log", []):
        regime_log.append({
            "timestamp": datetime.fromisoformat(r["timestamp"]),
            "regime_type": r["regime_type"],
            "adx": r["adx"],
            "vol_regime": r["vol_regime"],
        })

    timeframe = store_data.get("timeframe", "1d")
    return equity_log, fill_log, timeframe, regime_log
