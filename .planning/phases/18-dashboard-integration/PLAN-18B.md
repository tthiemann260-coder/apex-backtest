# PLAN-18B: Multi-Asset View Tab + Tests

## Context
PLAN-18A adds Regime Overlay and Risk Dashboard. This plan adds the Multi-Asset View tab with per-symbol equity curves and correlation heatmap, plus dashboard tests.

**Requirements:** DASH-03, TEST-24 | **~200 LOC** | **Dependency: PLAN-18A**

## Architecture Decisions
- **Separate run flow:** New "Run Multi-Asset" button with comma-separated symbol input
- **Per-symbol equity:** Use `compute_per_symbol_equity(equity_log)` from `src/multi_asset.py` — returns `{symbol: [{timestamp, equity}]}`
- **Normalized equity:** Each symbol's equity series normalized to 100% base: `eq[i] / eq[0] * 100`
- **Correlation matrix:** Full pipeline: `equity_log → compute_per_symbol_equity() → extract per-symbol Decimal lists → compute_rolling_correlation() → take LAST window's rows → pivot into NxN matrix → go.Heatmap`
- **Separate store:** `multi-asset-result-store` (dcc.Store) — isolates multi-asset data from single-asset
- **Strategy reuse:** Each symbol gets fresh strategy instance of same type from dropdown

## Modified Files

### 1. `src/dashboard/layouts.py` (+70 LOC)

**New chart placeholders:**
```python
def build_multi_equity_chart() -> dcc.Graph:
    return dcc.Graph(id="multi-equity-chart", style={"height": "400px"})

def build_correlation_heatmap_chart() -> dcc.Graph:
    return dcc.Graph(id="correlation-heatmap-chart", style={"height": "350px"})

def build_multi_asset_kpis() -> dbc.Row:
    kpis = [
        ("Symbols", "multi-kpi-symbols"),
        ("Combined PnL", "multi-kpi-pnl"),
        ("Avg Correlation", "multi-kpi-correlation"),
    ]
    return dbc.Row([dbc.Col(build_kpi_card(t, v), width="auto") for t, v in kpis])
```

**New tab:**
```python
def _build_multi_asset_tab() -> dbc.Tab:
    """Tab 6: Multi-Asset View."""
    return dbc.Tab(
        label="Multi-Asset",
        tab_id="tab-multi-asset",
        children=html.Div([
            dbc.Row([
                dbc.Col([
                    html.Label("Symbols (comma-separated)", className="fw-bold mb-1"),
                    dcc.Input(id="multi-symbol-input", type="text",
                              value="AAPL,MSFT", className="form-control"),
                ], md=4),
                dbc.Col([
                    html.Label("\u00a0", className="d-block mb-1"),
                    dbc.Button("Run Multi-Asset", id="run-multi-asset-btn",
                               color="info", className="w-100"),
                ], md=2),
            ], className="mb-3"),
            build_multi_asset_kpis(),
            dbc.Row([dbc.Col(dbc.Card([
                dbc.CardHeader("Per-Symbol Equity (Normalized to 100%)"),
                dbc.CardBody(build_multi_equity_chart()),
            ]))]),
            dbc.Row([dbc.Col(dbc.Card([
                dbc.CardHeader("Cross-Asset Correlation Matrix"),
                dbc.CardBody(build_correlation_heatmap_chart()),
            ]), className="mt-3")]),
        ], className="mt-3"),
    )
```

**Add hidden store + tab to `build_layout()`:**
```python
dcc.Store(id="multi-asset-result-store"),
# Add _build_multi_asset_tab() to tabs list
```

### 2. `src/dashboard/callbacks.py` (+100 LOC)

**Multi-asset backtest runner:**
```python
def _run_multi_asset_backtest(symbols_str, strategy_name, timeframe):
    """Run multi-asset backtest via MultiAssetEngine."""
    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
    handlers = {}
    strategies = {}
    for symbol in symbols:
        handlers[symbol] = DataHandler(symbol=symbol, source="yfinance", timeframe=timeframe)
        strategy_cls = _import_strategy(strategy_name)
        strategies[symbol] = strategy_cls(symbol=symbol, timeframe=timeframe)

    from src.multi_asset import create_multi_asset_engine
    engine = create_multi_asset_engine(handlers=handlers, strategies=strategies)
    result = engine.run()
    return result, symbols
```

**Multi-asset chart builders — EXPLICIT DATA PIPELINES:**

```python
def build_multi_equity_figure(equity_log, symbols):
    """Overlaid per-symbol equity curves normalized to 100%.

    Pipeline:
    1. compute_per_symbol_equity(equity_log) → {symbol: [{timestamp, equity}]}
    2. For each symbol: extract equity values
    3. Normalize: eq[i] / eq[0] * 100
    4. Add go.Scatter per symbol
    """
    from src.multi_asset import compute_per_symbol_equity
    fig = go.Figure()
    per_symbol = compute_per_symbol_equity(equity_log)
    colors = ["#4CAF50", "#2196F3", "#FF9800", "#F44336", "#9C27B0", "#00BCD4"]

    for i, symbol in enumerate(sorted(per_symbol.keys())):
        entries = per_symbol[symbol]
        if not entries:
            continue
        base_equity = float(entries[0]["equity"]) if entries[0]["equity"] != 0 else 1
        timestamps = [e["timestamp"] for e in entries]
        normalized = [float(e["equity"]) / base_equity * 100 for e in entries]
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
    )
    return fig


def build_correlation_heatmap_figure(equity_log, symbols):
    """Square NxN correlation heatmap from last rolling window.

    Pipeline:
    1. compute_per_symbol_equity(equity_log) → {symbol: [{timestamp, equity}]}
    2. Extract per-symbol Decimal lists: {symbol: [Decimal(eq1), Decimal(eq2), ...]}
    3. Extract aligned timestamps
    4. compute_rolling_correlation(equity_curves, timestamps, window=min(60, len))
    5. Take LAST timestamp's correlation values per pair
    6. Pivot into NxN matrix where diag=1.0 and (i,j)=correlation(sym_i, sym_j)
    7. go.Heatmap with symbols on both axes
    """
    from src.multi_asset import compute_per_symbol_equity, compute_rolling_correlation

    fig = go.Figure()
    per_symbol = compute_per_symbol_equity(equity_log)
    sorted_symbols = sorted(per_symbol.keys())

    if len(sorted_symbols) < 2:
        fig.update_layout(template="plotly_dark",
                          annotations=[{"text": "Need >= 2 symbols", "x": 0.5, "y": 0.5,
                                        "xref": "paper", "yref": "paper", "showarrow": False}])
        return fig

    # Build aligned equity curves (use common timestamps)
    min_len = min(len(per_symbol[s]) for s in sorted_symbols)
    equity_curves = {}
    timestamps = []
    for sym in sorted_symbols:
        entries = per_symbol[sym][:min_len]
        equity_curves[sym] = [entry["equity"] for entry in entries]
        if not timestamps:
            timestamps = [entry["timestamp"] for entry in entries]

    window = min(60, min_len - 1) if min_len > 2 else 2
    corr_data = compute_rolling_correlation(equity_curves, timestamps, window=window)

    if not corr_data:
        fig.update_layout(template="plotly_dark",
                          annotations=[{"text": "Not enough data for correlation", "x": 0.5, "y": 0.5,
                                        "xref": "paper", "yref": "paper", "showarrow": False}])
        return fig

    # Take last timestamp's correlations
    last_ts = corr_data[-1]["timestamp"]
    last_corrs = {r["pair"]: float(r["correlation"]) for r in corr_data if r["timestamp"] == last_ts}

    # Pivot into NxN matrix
    n = len(sorted_symbols)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0  # Diagonal
        for j in range(i + 1, n):
            pair_key = f"{sorted_symbols[i]}/{sorted_symbols[j]}"
            corr_val = last_corrs.get(pair_key, 0.0)
            matrix[i][j] = corr_val
            matrix[j][i] = corr_val

    fig.add_trace(go.Heatmap(
        z=matrix,
        x=sorted_symbols, y=sorted_symbols,
        colorscale="RdBu", zmid=0,
        text=[[f"{v:.2f}" for v in row] for row in matrix],
        texttemplate="%{text}",
    ))
    fig.update_layout(template="plotly_dark", margin={"l": 60, "r": 20, "t": 10, "b": 40})
    return fig
```

**New callback:**
```python
@app.callback(
    [Output("multi-equity-chart", "figure"),
     Output("correlation-heatmap-chart", "figure"),
     Output("multi-kpi-symbols", "children"),
     Output("multi-kpi-pnl", "children"),
     Output("multi-kpi-correlation", "children")],
    Input("run-multi-asset-btn", "n_clicks"),
    [State("multi-symbol-input", "value"),
     State("strategy-selector", "value"),
     State("timeframe-selector", "value")],
    prevent_initial_call=True,
)
def run_multi_asset_callback(n_clicks, symbols_str, strategy, timeframe):
    if not n_clicks or not symbols_str:
        return [no_update] * 5
    try:
        result, symbols = _run_multi_asset_backtest(symbols_str, strategy, timeframe)
        eq_fig = build_multi_equity_figure(result.equity_log, symbols)
        corr_fig = build_correlation_heatmap_figure(result.equity_log, symbols)
        # KPIs
        n_sym = str(len(symbols))
        pnl = f"${float(result.final_equity - Decimal('10000')):,.2f}"
        # Avg correlation from last window
        ...
        return [eq_fig, corr_fig, n_sym, pnl, avg_corr_str]
    except Exception as e:
        ...
```

### 3. `tests/test_dashboard_integration.py` (~60 LOC, 7 Tests)

| Test | Prueft |
|---|---|
| test_regime_colors_all_types | REGIME_COLORS has all 6 RegimeType values |
| test_add_regime_overlay_empty | _add_regime_overlay with empty list does nothing |
| test_add_regime_overlay_bands | _add_regime_overlay adds vrects for regime bands |
| test_build_multi_equity_empty | Empty equity_log returns valid figure |
| test_build_correlation_heatmap_empty | Empty data returns valid figure |
| test_build_heat_gauge | Heat gauge returns Plotly indicator figure |
| test_build_sizing_distribution | Histogram from fill quantities returns figure |

**Pattern:** Test chart builder functions directly (no Dash app needed). Import from callbacks.py.

## Ausfuehrungsreihenfolge

1. **Wave 1:** PLAN-18A (Regime Overlay + Risk Dashboard)
2. **Wave 2:** PLAN-18B (Multi-Asset View + Tests — depends on 18A for store changes)

## Neue Dateien (1)
- `tests/test_dashboard_integration.py`

## Modifizierte Dateien (3)
- `src/strategy/regime/gated_strategy.py` (+15 LOC — regime_log)
- `src/dashboard/layouts.py` (+150 LOC — risk tab + multi-asset tab + controls)
- `src/dashboard/callbacks.py` (+250 LOC — chart builders + callbacks + serialization)

## Nicht modifiziert
- `src/engine.py`, `src/portfolio.py`, `src/execution.py`, `src/events.py`, `src/multi_asset.py`

## Verification
1. `pytest tests/test_dashboard_integration.py -v` — alle 7 Tests gruen
2. `pytest tests/ -v` — alle 543+ Tests gruen (536 + 7)
3. `pytest --cov=src tests/` — Coverage >= 90%
4. `python -m src.dashboard` — Dashboard startet ohne Fehler
5. Regime Overlay: vrect bands sichtbar auf Candlestick bei regime_ict + toggle on
6. Risk Dashboard: Heat gauge, sizing, daily risk, drawdown scaling
7. Multi-Asset: Per-Symbol equity normalized to 100%, correlation NxN heatmap
8. compute_per_symbol_equity() korrekt eingebunden (nicht manuell extrahiert)
