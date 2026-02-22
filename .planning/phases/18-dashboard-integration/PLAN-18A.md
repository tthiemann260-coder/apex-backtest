# PLAN-18A: Regime Overlay + Risk Dashboard Tab

## Context
Phase 18 integrates Phase 15-17 features into the Dash dashboard. This plan adds a regime overlay on the candlestick chart and a new Risk Dashboard tab.

**Requirements:** DASH-01, DASH-02 | **~250 LOC** | **No dependencies beyond Phase 17**

## Architecture Decisions
- **Regime history capture:** Add `_regime_log` list to RegimeGatedStrategy — records per-bar regime data
- **_run_backtest 4-tuple return:** `(result, metrics, error, regime_log)` — regime_log captured before strategy goes out of scope
- **Regime overlay:** Separate callback `Input("regime-overlay-toggle") + Input("backtest-result-store")` → `Output("candlestick-chart")` — avoids modifying the existing 15-output main callback
- **Serialization:** `regime_log` stored as `[{"timestamp": iso_str, "regime_type": str, "adx": float, "vol_regime": str}]` in store_data
- **Risk Dashboard:** New 5th tab with Heat Gauge + Sizing Distribution + Daily Risk Usage + Drawdown Scaling
- **Daily Risk Usage:** Group fills by calendar day, compute daily capital at risk as bar chart

## Modified Files

### 1. `src/strategy/regime/gated_strategy.py` (+15 LOC)

**Add regime_log capture:**
```python
# In __init__:
self._regime_log: list[dict] = []

# In calculate_signals, after regime classification:
if regime is not None:
    self._regime_log.append({
        "timestamp": event.timestamp,
        "regime_type": regime.regime_type.value,
        "adx": float(regime.adx),
        "vol_regime": regime.vol_regime.value,
    })

@property
def regime_log(self) -> list[dict]:
    return list(self._regime_log)
```

### 2. `src/dashboard/layouts.py` (+80 LOC)

**New chart placeholders:**
```python
def build_heat_gauge() -> dcc.Graph:
    return dcc.Graph(id="heat-gauge-chart", style={"height": "250px"})

def build_sizing_distribution_chart() -> dcc.Graph:
    return dcc.Graph(id="sizing-distribution-chart", style={"height": "300px"})

def build_daily_risk_usage_chart() -> dcc.Graph:
    return dcc.Graph(id="daily-risk-usage-chart", style={"height": "300px"})

def build_drawdown_scaling_chart() -> dcc.Graph:
    return dcc.Graph(id="drawdown-scaling-chart", style={"height": "300px"})
```

**Risk summary cards:**
```python
def build_risk_summary_cards() -> dbc.Row:
    kpis = [
        ("Current Heat %", "risk-kpi-heat"),
        ("Max Positions", "risk-kpi-max-pos"),
        ("DD Scale Factor", "risk-kpi-dd-scale"),
        ("Risk Budget Used %", "risk-kpi-budget"),
    ]
    return dbc.Row([dbc.Col(build_kpi_card(t, v), width="auto") for t, v in kpis])
```

**New tab:**
```python
def _build_risk_tab() -> dbc.Tab:
    """Tab 5: Risk Dashboard — Heat, Sizing, Daily Risk, Drawdown."""
    return dbc.Tab(
        label="Risk Dashboard",
        tab_id="tab-risk",
        children=html.Div([
            build_risk_summary_cards(),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Portfolio Heat"),
                    dbc.CardBody(build_heat_gauge()),
                ]), md=4),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Position Sizing Distribution"),
                    dbc.CardBody(build_sizing_distribution_chart()),
                ]), md=8),
            ]),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Daily Risk Usage"),
                    dbc.CardBody(build_daily_risk_usage_chart()),
                ]), md=6),
                dbc.Col(dbc.Card([
                    dbc.CardHeader("Drawdown Scale Factor"),
                    dbc.CardBody(build_drawdown_scaling_chart()),
                ]), md=6),
            ]),
        ], className="mt-3"),
    )
```

**Regime overlay toggle (add to build_controls):**
```python
dbc.Col([
    dbc.Checkbox(id="regime-overlay-toggle", label="Regime Overlay", value=False),
], md="auto", className="d-flex align-items-end"),
```

**Add `_build_risk_tab()` to tabs list in `build_layout()`.**

### 3. `src/dashboard/callbacks.py` (+150 LOC)

**_run_backtest signature change — 4-tuple return:**
```python
def _run_backtest(...) -> tuple[Optional[BacktestResult], Optional[MetricsResult], Optional[str], list[dict]]:
    """...returns (result, metrics, error, regime_log)."""
    try:
        ...
        result = engine.run()
        # Capture regime_log before strategy goes out of scope
        regime_log = getattr(strategy, "regime_log", [])
        ...
        return result, metrics, None, regime_log
    except Exception as e:
        return None, None, f"Error: ...", []
```

**All 3 call sites updated:**
- `run_backtest_callback`: `result, metrics, error, regime_log = _run_backtest(...)`
- `run_sweep_callback`: `_, metrics, error, _ = _run_backtest(...)`
- `run_commission_sweep_callback` (calls via `run_commission_sweep` which is in analytics.py — must be checked; if it calls `_run_backtest`, update too)

**Serialization extension — _serialize_result:**
```python
# Add to _serialize_result:
def _serialize_result(result, strategy, timeframe, symbol, regime_log=None):
    ...
    store = {
        "equity_log": equity_data,
        "fill_log": fill_data,
        "strategy": strategy,
        "timeframe": timeframe,
        "symbol": symbol,
        "regime_log": [
            {"timestamp": r["timestamp"].isoformat(), "regime_type": r["regime_type"],
             "adx": r["adx"], "vol_regime": r["vol_regime"]}
            for r in (regime_log or [])
        ],
    }
    return store
```

**Deserialization extension — _deserialize_result:**
```python
# Add after fill_log deserialization:
regime_log = []
for r in store_data.get("regime_log", []):
    regime_log.append({
        "timestamp": datetime.fromisoformat(r["timestamp"]),
        "regime_type": r["regime_type"],
        "adx": r["adx"],
        "vol_regime": r["vol_regime"],
    })
# Return 4-tuple: (equity_log, fill_log, timeframe, regime_log)
```

**Regime overlay chart builder:**
```python
REGIME_COLORS = {
    "STRONG_TREND": "rgba(76, 175, 80, 0.1)",
    "MODERATE_TREND": "rgba(139, 195, 74, 0.1)",
    "WEAK_TREND": "rgba(255, 235, 59, 0.1)",
    "RANGING_NORMAL": "rgba(158, 158, 158, 0.1)",
    "RANGING_LOW": "rgba(33, 150, 243, 0.1)",
    "CHOPPY": "rgba(244, 67, 54, 0.1)",
}

def _add_regime_overlay(fig, regime_log):
    """Add colored vrect backgrounds for consecutive regime bands."""
    if not regime_log:
        return
    # Group consecutive same-regime entries into bands
    bands = []
    current_regime = regime_log[0]["regime_type"]
    band_start = regime_log[0]["timestamp"]
    for entry in regime_log[1:]:
        if entry["regime_type"] != current_regime:
            bands.append((band_start, entry["timestamp"], current_regime))
            current_regime = entry["regime_type"]
            band_start = entry["timestamp"]
    bands.append((band_start, regime_log[-1]["timestamp"], current_regime))
    for start, end, regime in bands:
        fig.add_vrect(x0=start, x1=end,
                      fillcolor=REGIME_COLORS.get(regime, "rgba(0,0,0,0)"),
                      layer="below", line_width=0)
```

**Separate regime overlay callback (avoids modifying main callback):**
```python
@app.callback(
    Output("candlestick-chart", "figure", allow_duplicate=True),
    [Input("regime-overlay-toggle", "value"),
     Input("backtest-result-store", "data")],
    prevent_initial_call=True,
)
def update_regime_overlay(toggle_on, store_data):
    if not store_data:
        return no_update
    equity_log, fill_log, timeframe, regime_log = _deserialize_result(store_data)
    fig = build_candlestick_figure(equity_log, fill_log)
    if toggle_on and regime_log:
        _add_regime_overlay(fig, regime_log)
    return fig
```

**Risk chart builders:**
```python
def build_heat_gauge_figure(equity_log, fill_log):
    """Plotly Indicator gauge showing approximate portfolio heat."""
    # Compute: sum(position_risk) / final_equity
    # Return go.Indicator(mode="gauge+number+delta", value=heat_pct)

def build_sizing_distribution_figure(fill_log):
    """Histogram of position sizes from fill quantities."""
    quantities = [float(f.quantity) for f in fill_log if f.side == OrderSide.BUY]
    # Return go.Histogram(x=quantities)

def build_daily_risk_usage_figure(fill_log):
    """Bar chart: daily capital at risk vs daily limit."""
    # Group fills by calendar day
    # daily_risk[day] = sum(fill.quantity * fill.fill_price) for BUY fills
    # Show as bar chart per day

def build_drawdown_scaling_figure(equity_log):
    """Line chart: DrawdownScaler.compute_scale() over time."""
    from src.risk_manager import DrawdownScaler
    scaler = DrawdownScaler()
    # For each equity entry, compute scale factor from equity_log[:i+1]
```

**Risk Dashboard callback:**
```python
@app.callback(
    [Output("heat-gauge-chart", "figure"),
     Output("sizing-distribution-chart", "figure"),
     Output("daily-risk-usage-chart", "figure"),
     Output("drawdown-scaling-chart", "figure"),
     Output("risk-kpi-heat", "children"),
     Output("risk-kpi-max-pos", "children"),
     Output("risk-kpi-dd-scale", "children"),
     Output("risk-kpi-budget", "children")],
    Input("backtest-result-store", "data"),
)
def update_risk_tab(store_data):
    if not store_data:
        empty = go.Figure()
        empty.update_layout(template="plotly_dark")
        return [empty] * 4 + ["--"] * 4
    equity_log, fill_log, timeframe, _ = _deserialize_result(store_data)
    ...
```

## Verification
1. Regime overlay shows colored vrect bands on candlestick chart when regime_ict selected + toggle on
2. Regime overlay toggle hides/shows bands without re-running backtest
3. regime_log serialization round-trip: _serialize → store → _deserialize → _add_regime_overlay
4. Risk Dashboard tab shows heat gauge, sizing histogram, daily risk usage, drawdown scaling
5. Risk KPI cards display computed values
6. Daily Risk Usage bar chart groups fills by calendar day
7. _run_backtest 4-tuple return works at all 3 call sites
8. All 536 existing tests still pass
