# Features Research: apex-backtest

**Research Date:** 2026-02-21
**Scope:** Event-driven backtesting engine — Forex + US Stocks, 1min–Daily, Reversal/Breakout/FVG strategies
**Method:** Comparative analysis of Backtrader, Zipline, VectorBT, NautilusTrader, QuantConnect, backtesting.py

---

## Table Stakes (Must Have)

Without these, the engine is not a backtesting engine — it is just a simulation loop.

### Data Management

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| OHLCV bar ingestion | Load Open/High/Low/Close/Volume per bar | Low | Absolute minimum for any backtester |
| Multiple data sources | yfinance (stocks), Alpha Vantage or OANDA (forex) | Low–Medium | Free APIs only; yfinance unreliable for heavy use — cache locally |
| Local data caching | Persist downloaded bars to CSV/Parquet — avoid re-downloading | Low | Essential for iteration speed; avoids rate limits |
| Multi-symbol support | Run engine across >1 ticker/pair simultaneously | Medium | Needed for portfolio strategies |
| Multi-timeframe alignment | 1min, 5min, 15min, 1h, 4h, Daily coexist; bars step forward in lockstep | Medium | Without this, higher-timeframe signals see the future |
| Date range filtering | Start/end date parameters for train/test splits | Low | Needed from day one |
| Forward-fill gaps | Handle missing bars (weekends, holidays, illiquid hours) | Low–Medium | Especially important for forex pairs |
| Decimal-precise prices | `Decimal` type for all price/PnL arithmetic, not `float` | Low | Float drift compounds over thousands of trades; `Decimal("0.0001")` not `Decimal(0.0001)` |

**Dependencies:** Local caching depends on ingestion. Multi-timeframe alignment depends on multi-symbol. Decimal precision is foundational — retrofit is painful.

---

### Strategy Framework

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| Strategy base class | Abstract interface: `on_bar()`, `on_order_filled()` hooks | Low | All engines have this; defines the plugin contract |
| Signal generation | Strategy emits BUY/SELL/FLAT signals per bar | Low | Core loop |
| Indicator library access | SMA, EMA, ATR, RSI, Bollinger Bands, pivot levels | Low–Medium | Use `pandas-ta` or `ta-lib` — do not reinvent |
| Lookahead bias prevention | Strategy sees only bars up to `t`, never `t+1` | Medium | Event-driven architecture solves this structurally; vector backtesters require explicit care |
| Parameter injection | Pass strategy params (period lengths, thresholds) at instantiation | Low | Required for optimization later |
| Multiple concurrent strategies | Run Reversal + Breakout + FVG independently on same data | Medium | Needed for your use case |

**Dependencies:** Indicator library plugs into strategy framework. Multiple strategies depend on portfolio layer handling position conflicts.

---

### Execution Simulation

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| Market order simulation | Fill at next bar open (standard), or at close | Low | Most common; "fill at signal bar close" is a lookahead bias |
| Limit order simulation | Fill when price crosses limit within bar's H/L range | Medium | Required for realistic reversal/FVG entries |
| Stop-loss orders | Exit at stop price; intra-bar simulation using bar's Low | Medium | Without this, drawdowns are unrealistically small |
| Take-profit orders | Exit at target price within bar | Low–Medium | Pairs with stop-loss for R:R tracking |
| Commission modeling | Fixed per trade, percentage of notional, or per-share | Low | Even $0 commission must be modeled explicitly |
| Spread simulation | Bid-ask spread applied at entry/exit (critical for forex) | Low–Medium | Forex lives on spread; ignoring it produces fantasy results |
| Slippage modeling | Fixed-point slippage or volume-proportional slippage | Medium | Even a 1-pip constant slippage changes results materially |
| Position sizing | Fixed lot, fixed risk %, fixed capital fraction | Low–Medium | Needed for any meaningful PnL calculation |
| Long and short support | Both directions simulatable per instrument | Low | Needed for reversal strategies |
| Partial fills | Fill fraction of order when liquidity is insufficient | High | Skip initially — add only if your strategies rely on large size |

**Dependencies:** Stop/TP depend on limit order logic. Slippage depends on commission being in place. Position sizing feeds into portfolio state.

**What free alternatives miss:** Backtrader has all of the above but its multi-timeframe API is non-obvious. backtesting.py is excellent for single-timeframe but multi-symbol support is limited. VectorBT is fast but requires explicit lookahead guards.

---

### Performance Metrics

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| Net PnL | Total profit/loss in currency units | Low | Absolute baseline |
| Total return % | (Final equity - Initial equity) / Initial equity | Low | |
| Annualized return | Compound annual growth rate (CAGR) | Low | Required for cross-strategy comparison |
| Sharpe Ratio | Risk-adjusted return vs total volatility; >1 acceptable, >2 strong | Low | Industry standard; must use annualized, risk-free rate configurable |
| Sortino Ratio | Like Sharpe but uses only downside deviation | Low | Better for asymmetric strategies (breakouts, reversals) |
| Calmar Ratio | Annualized return / Max drawdown; focuses on worst-case risk | Low | Preferred by many CTAs |
| Max Drawdown | Largest peak-to-trough decline in equity curve | Low | Absolute must-have for risk assessment |
| Max Drawdown Duration | How many bars/days the drawdown lasted | Low | Extension of MDD; often ignored, highly informative |
| Win rate | % of trades that are profitable | Low | Alone is misleading; needs R:R to be meaningful |
| Profit factor | Gross profit / Gross loss | Low | >1.5 is the threshold for a viable strategy |
| Average R:R | Average reward-to-risk per trade | Low | Core for reversal/breakout strategies |
| Trade count | Total trades executed | Low | Context for statistical significance |
| Average holding time | Mean bars held per position | Low | Helps characterize strategy behavior |
| Expectancy | (Win% × Avg Win) - (Loss% × Avg Loss) | Low | Positive expectancy is the fundamental requirement |

**Dependencies:** All metrics depend on a completed trade log. Annualized metrics require knowing the timeframe of the data.

---

### Basic Visualization

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| Equity curve chart | Portfolio value over time, plotted as line | Low | First chart any user looks at |
| Drawdown chart | Drawdown % below equity peak over time | Low | Paired with equity curve; standard |
| Trade markers on price chart | Entry/exit points overlaid on OHLCV candlestick chart | Medium | Visually validates that trades make sense |
| Summary metrics panel | Key stats (Sharpe, MDD, PnL, Win%) in a table/card | Low | Reference card; displayed alongside charts |
| Dash integration | Serve charts via Dash app on localhost | Low–Medium | You have already chosen Dash; straightforward with Plotly figures |

**Dependencies:** All charts depend on trade log and equity curve data structures. Dash integration is a wrapper around Plotly figures.

---

## Differentiators (Competitive Advantage)

These features distinguish apex-backtest from using backtesting.py or Backtrader off the shelf.

### Advanced Analytics

| Feature | Description | Complexity | Why It Differentiates |
|---|---|---|---|
| Monthly returns heatmap | Returns broken down by year × month grid | Medium | Immediately reveals seasonality and regime sensitivity; not in most free tools |
| Rolling Sharpe / Rolling Drawdown | Metrics over a sliding window (e.g., 252-bar) | Medium | Shows if strategy degrades over time; static Sharpe hides this |
| Trade-level breakdown | Win/loss/BE by hour-of-day, day-of-week, session (London/NY/Tokyo) | Medium | Identifies when a strategy actually works vs when it bleeds |
| Consecutive loss / win streaks | Longest run of losing trades | Low | Psychological and risk sizing relevance |
| MAE/MFE analysis | Maximum Adverse/Favorable Excursion per trade — how far against/for before close | High | Optimizes stop and target placement; rarely in free tools |
| Commission sensitivity | Re-run metrics at 0x, 0.5x, 1x, 2x commission to test robustness | Low | Shows if edge survives realistic friction |
| Pip-level precision for forex | P&L computed in pips before currency conversion; pip value per pair | Medium | Free tools often approximate this; getting it right is a differentiator |

**Dependencies:** Trade-level breakdown requires timestamps on all trades. MAE/MFE requires intra-bar price tracking (bar's High/Low range).

---

### Multi-Timeframe Analysis

| Feature | Description | Complexity | Why It Differentiates |
|---|---|---|---|
| Higher-timeframe bias filter | Daily or 4H trend determines whether 1H signals are taken | Medium–High | Structural to FVG and reversal strategies; prevents fighting the trend |
| Multi-timeframe signal cascade | Signal formed on H4 triggers entry search on M15 | High | Directly supports your strategy design; very few free tools handle this cleanly |
| Timeframe-aware indicator calculation | ATR on 4H, entry on 1H, stop on 15min | Medium | Prevents indicator recalculation errors across timeframe boundaries |
| Session filters | Restrict trades to London session, NY session, overlap | Medium | Forex-specific; dramatically changes result profiles |

**Dependencies:** All multi-timeframe features require the bar alignment system from Table Stakes. Session filters require datetime-aware bar metadata.

---

### Strategy Optimization

| Feature | Description | Complexity | Why It Differentiates |
|---|---|---|---|
| Grid search parameter sweep | Run strategy across a parameter grid; return metrics matrix | Medium | Baseline optimization; needed to tune ATR multiples, lookback periods |
| Walk-forward validation | Train on rolling window, test on next window, report OOS results | High | Reduces overfitting; most free tools do not do this out of the box |
| Robustness report | Show how metrics degrade as parameters vary ±10% | Medium | Identifies fragile parameter choices; a robust edge is flat-ish around optimum |
| Multiple strategy comparison | Side-by-side metrics for Reversal vs Breakout vs FVG | Low | Dash panel; needs consistent output schema from all strategies |

**Dependencies:** Walk-forward requires grid search infrastructure. Robustness report is a derivative of the parameter sweep output. All optimization depends on fast run times — if a single backtest takes >5 seconds, grid search becomes painful.

---

### FVG / Smart Money Concepts (Strategy-Specific Differentiator)

| Feature | Description | Complexity | Notes |
|---|---|---|---|
| FVG detection engine | Identify three-candle imbalance patterns (bullish + bearish FVG) | Medium | Three consecutive candles where C3 does not overlap C1; filter by momentum candle size |
| FVG mitigation tracking | Track which FVGs have been partially or fully filled | Medium | Unfilled FVGs remain active; filled ones are closed |
| FVG entry logic | Entry when price re-enters gap from above (bearish) or below (bullish) | Medium | Core of the FVG reversal strategy |
| Order block detection | Identify last bearish candle before a bullish impulse (and vice versa) | Medium | Companion to FVG; common in ICT-style strategies |
| Break of Structure (BOS) detection | Identify swing high/low breaks to confirm trend | Medium | Used as higher-timeframe filter for FVG entries |

**Dependencies:** FVG tracking depends on the bar history buffer in the data handler. Multi-timeframe is essential for BOS on H4 + FVG entry on M15.

---

## Anti-Features (Do NOT Build)

These are features found in enterprise/commercial tools that would consume significant time with no return for a personal-use, free-API project.

| Feature | Why Not | What To Do Instead |
|---|---|---|
| Live trading integration | Out of scope; doubles complexity; requires broker API auth, real-time feeds, order management | Keep backtesting and live trading as separate codebases. If live trading is ever needed, use CCXT or OANDA REST API as a separate layer. |
| Tick-level / L2 order book simulation | Free APIs do not provide tick data or depth; complexity is enormous; results not meaningful without real tick data | Stick to OHLCV bar simulation. 1-minute bars are the lowest meaningful resolution for your data sources. |
| Neural network / ML strategy generation | Backtesting ML strategies requires feature engineering, cross-validation, purging — a research project in itself | Keep strategies rule-based (Reversal, Breakout, FVG). Add ML only if you have a specific, tested hypothesis and purged CV infrastructure. |
| Cloud deployment / multi-user SaaS | Personal use. Adding auth, billing, multi-tenancy, rate limiting turns a research tool into a product | Run on localhost. Use Dash's built-in dev server. |
| Real-time data streaming / paper trading | Requires WebSocket connections, reconnect logic, missed-message handling, timestamp sync | Not needed for backtesting. Defer indefinitely. |
| Portfolio-level multi-asset optimization (Markowitz, risk parity) | Requires covariance estimation, regime modeling; far beyond strategy backtesting | Track per-strategy metrics. Multi-strategy comparison via summary table is sufficient. |
| Options / futures / crypto derivatives | Different margining rules, settlement, expiry, contango, roll costs — a separate engine | Focus on Forex spot + US equities. State this scope limit explicitly in code. |
| GUI strategy builder (drag-and-drop) | Engineering effort is 10x. Dash is already the visualization layer. | Keep strategy definition as Python classes with parameters. A good parameter interface is sufficient. |
| Automated report PDF generation | Low ROI. Dash already provides interactive reports. | Export to CSV for trade log; Dash screenshots for charts. |
| Natural language strategy input (LLM parsing) | LLMs hallucinate logic; debugging is impossible; not reproducible | Write strategies in Python. The interface is already code. |

---

## Feature Dependencies

```
Data Ingestion
  └── Local Cache
       └── Multi-Symbol Support
            └── Multi-Timeframe Alignment
                 └── Higher-TF Bias Filter
                      └── Multi-TF Signal Cascade

Bar Event Loop (Event-Driven Core)
  └── Strategy.on_bar()
       ├── Indicator Calculation (pandas-ta)
       ├── Signal Generation
       │    ├── FVG Detection Engine
       │    ├── FVG Mitigation Tracking
       │    └── BOS Detection
       └── Order Submission
            └── Execution Handler
                 ├── Market Fill (next open)
                 ├── Limit Fill (intra-bar H/L check)
                 ├── Stop-Loss Check (intra-bar Low)
                 └── Take-Profit Check (intra-bar High)
                      └── Commission + Spread + Slippage deduction

Trade Log (per completed trade)
  ├── Performance Metrics (Sharpe, MDD, Win%, PF, Expectancy, CAGR)
  ├── Trade-Level Breakdown (by hour, session, day)
  ├── MAE/MFE Analysis
  └── Equity Curve
       ├── Drawdown Chart
       ├── Monthly Returns Heatmap
       └── Rolling Metrics

Equity Curve + Trade Log
  └── Dash Dashboard
       ├── Price Chart + Trade Markers
       ├── Metrics Summary Panel
       └── Multi-Strategy Comparison Panel

Performance Metrics
  └── Grid Search / Parameter Sweep
       └── Walk-Forward Validation
            └── Robustness Report
```

**Critical path:** Bar Event Loop → Trade Log → Performance Metrics. Everything else is layered on top.

---

## Complexity Estimates

### Table Stakes

| Feature | Complexity | Effort Estimate |
|---|---|---|
| OHLCV bar ingestion (yfinance + Alpha Vantage) | Low | 1–2 days |
| Local data caching (Parquet) | Low | 0.5 day |
| Multi-symbol support | Low–Medium | 1 day |
| Multi-timeframe alignment (bar lockstep) | Medium | 2–3 days |
| Forward-fill gap handling | Low | 0.5 day |
| Decimal-precise arithmetic throughout | Low | 0.5 day (foundational decision, not a separate task) |
| Strategy base class + `on_bar()` hook | Low | 1 day |
| Indicator library integration (pandas-ta) | Low | 0.5 day |
| Lookahead bias prevention (event-driven structure) | Medium | Solved by architecture; ongoing discipline |
| Market order simulation | Low | 1 day |
| Limit order simulation | Medium | 1–2 days |
| Stop-loss / Take-profit intra-bar | Medium | 1 day |
| Commission + Spread + Slippage model | Medium | 1 day |
| Position sizing | Low | 0.5 day |
| Core performance metrics (12 metrics) | Low | 1–2 days |
| Equity curve + Drawdown chart (Dash) | Low | 1 day |
| Trade markers on price chart | Medium | 1–2 days |
| Summary metrics panel | Low | 0.5 day |

**Table Stakes Total Estimate: 3–5 weeks (solo developer, part-time)**

---

### Differentiators

| Feature | Complexity | Effort Estimate |
|---|---|---|
| Monthly returns heatmap | Medium | 1 day |
| Rolling Sharpe / Drawdown | Medium | 1 day |
| Trade-level breakdown by session/hour | Medium | 1–2 days |
| MAE/MFE analysis | High | 2–3 days |
| Commission sensitivity sweep | Low | 0.5 day |
| Forex pip-level precision | Medium | 1 day |
| Higher-timeframe bias filter | Medium–High | 2–3 days |
| Multi-TF signal cascade | High | 3–5 days |
| Session filters (London/NY) | Medium | 1 day |
| FVG detection + mitigation tracking | Medium | 2–3 days |
| Order block + BOS detection | Medium | 2–3 days |
| Grid search parameter sweep | Medium | 2 days |
| Walk-forward validation | High | 3–5 days |
| Robustness report | Medium | 1–2 days |
| Multi-strategy comparison panel | Low | 1 day |

**Differentiators Total Estimate: 4–8 weeks additional (after table stakes)**

---

## Prioritization Recommendation

**Phase 1 — Core Engine (Build First)**
1. Decimal-precise event loop with single-timeframe OHLCV
2. Market + limit + stop/TP order simulation with commission/spread/slippage
3. Trade log → 12 core metrics
4. Equity curve + drawdown in Dash

**Phase 2 — Strategy Layer**
5. Strategy base class with pandas-ta indicators
6. FVG detection, BOS, reversal signal logic
7. Single-timeframe backtest of all three strategy types
8. Trade markers on price chart, session filters

**Phase 3 — Multi-Timeframe + Analytics**
9. Multi-timeframe bar alignment
10. Higher-TF bias filter + signal cascade
11. Monthly heatmap, rolling metrics, trade-level breakdown
12. MAE/MFE analysis

**Phase 4 — Optimization**
13. Grid search
14. Walk-forward validation
15. Robustness report
16. Multi-strategy comparison panel

**Rationale:** Each phase delivers usable, testable output. Do not start Phase 3 until you have at least one strategy producing valid Phase 1 results.

---

## Key Risks and Decisions

| Risk | Mitigation |
|---|---|
| yfinance reliability for historical data | Cache all downloaded data locally in Parquet from first use; implement a fallback to Alpha Vantage (free tier: 25 calls/day — sufficient for cached workflow) |
| Float drift in PnL over thousands of trades | Enforce `Decimal` from day 0; no retrofitting |
| Lookahead bias in multi-timeframe | Use event-driven bar-by-bar loop; higher-TF bar is only visible after it closes |
| Over-optimization via grid search | Implement walk-forward from the start; report OOS metrics only |
| Multi-timeframe complexity spike | Build single-timeframe engine first; validate it fully before adding timeframe layers |
| FVG strategies requiring tick precision | 1-minute bars are sufficient for FVG pattern detection; acknowledge that intra-minute entry is not simulated |

---

*Sources consulted: QuantStart event-driven backtesting series, NautilusTrader documentation, Backtrader/VectorBT/Zipline comparison analysis, QuantConnect slippage model docs, LuxAlgo backtesting metrics guide, IBKR slippage analysis, Python Decimal documentation, Plotly/Dash community examples, smart-money-concepts Python package (joshyattridge), ForexTester FVG guide.*
