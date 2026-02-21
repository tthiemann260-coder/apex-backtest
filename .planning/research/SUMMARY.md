# Research Summary: apex-backtest

**Synthesized:** 2026-02-21
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Stack Decision

- **Python 3.12.x** — stable fast release (~25% speedup over 3.11); avoid 3.13 (experimental free-threaded mode, lagging wheels)
- **decimal.Decimal (stdlib)** — only correct choice for financial arithmetic; `Decimal('0.0001')` string constructor, prec=28
- **collections.deque (stdlib)** — O(1) event queue; simpler and faster than asyncio.Queue or queue.Queue for single-threaded sim
- **pandas 2.2.3 (PINNED)** — DO NOT upgrade to 3.0 (Copy-on-Write breaking change + new string dtype); use with NumPy 2.2.4
- **yfinance 1.0.x** — free US stock OHLCV, major 2026 release; always cache locally after first fetch (unofficial scraper — can break)
- **alpha_vantage 3.0.x** — secondary source for Forex (EUR/USD, GBP/USD); 500 calls/day free; rate-limit wrapper required
- **pandas-ta 0.3.14b** — pure Python TA library (ATR, EMA, RSI, Bollinger, pivots); avoids ta-lib C compilation pain on Windows
- **Dash 3.x + Plotly 6.x** — mandated; interactive dashboard, candlestick charts, multi-panel layouts; avoid Dash 4.0 (released Feb 2026, too fresh)
- **pytest 8.4.x + pytest-cov + pytest-mock + freezegun** — full TDD stack; freezegun for deterministic timestamp tests
- **SQLite (stdlib) + pyarrow** — SQLite for trade log/config; Parquet for bulk OHLCV caching (faster re-reads for 1-min data)

---

## Table Stakes Features

**Data Management**
- OHLCV bar ingestion (yfinance + Alpha Vantage)
- Local Parquet/SQLite caching — mandatory to avoid re-downloading and API rate limits
- Multi-symbol support and date range filtering
- Multi-timeframe bar alignment (1min to Daily in lockstep)
- Forward-fill gap handling (weekends, holidays)
- Decimal-precise prices throughout — retrofit is painful, must be foundational

**Strategy Framework**
- Abstract `BaseStrategy` with `calculate_signals(event)` hook
- Signal generation (LONG / SHORT / EXIT per bar)
- Indicator access via pandas-ta (SMA, EMA, ATR, RSI, Bollinger)
- Lookahead bias prevention — structurally solved by yield-generator DataHandler
- Parameter injection at instantiation

**Execution Simulation**
- Market order fill at next bar open (NOT same-bar close)
- Limit order fill (intra-bar H/L check)
- Stop-loss and take-profit (intra-bar)
- Commission model (per-trade flat + per-share/pip)
- Spread simulation (bid/ask applied at entry and exit)
- Slippage model (percentage-based)
- Percentage-based position sizing (risk % of current equity)
- Long and short support

**Performance Metrics**
- Net PnL, Total Return %, CAGR
- Sharpe Ratio (annualized, correct factor per timeframe)
- Sortino Ratio, Calmar Ratio
- Max Drawdown + Max Drawdown Duration
- Win Rate, Profit Factor, Expectancy
- Trade count, average holding time, average R:R

**Visualization**
- Equity curve chart
- Drawdown chart
- Trade entry/exit markers on candlestick chart
- Summary KPI panel (Sharpe, MDD, PnL, Win%)
- Dash localhost app

---

## Differentiating Features

- **Monthly returns heatmap** — reveals seasonality and regime sensitivity; absent in most free tools
- **Rolling Sharpe / Rolling Drawdown** — exposes strategy degradation over time; static Sharpe hides this
- **Trade-level breakdown by session/hour/day** — identifies when a strategy works vs. bleeds
- **MAE/MFE analysis** — max adverse/favorable excursion per trade; optimizes stop and target placement
- **FVG detection engine** — three-candle imbalance pattern detection (bullish + bearish), mitigation tracking
- **Order Block + Break of Structure (BOS) detection** — ICT-style smart money companion to FVG
- **Session filters** — restrict signals to London, NY, or overlap; forex-specific, changes result profiles dramatically
- **Higher-timeframe bias filter** — H4 trend gates 1H entries; prevents fighting the trend
- **Multi-timeframe signal cascade** — signal on H4 triggers entry search on M15
- **Grid search parameter sweep + walk-forward validation** — OOS validation; broad plateau selection over sharp peaks
- **Commission sensitivity sweep** — test edge at 0x, 0.5x, 1x, 2x friction
- **Forex pip-level precision** — P&L in pips before currency conversion; dynamic pip value per pair

---

## Architecture Overview

**8 Components:**

| Component | File | Role |
|---|---|---|
| Events | `src/events.py` | Immutable `@dataclass(frozen=True)`: MarketEvent, SignalEvent, OrderEvent, FillEvent |
| Event Queue | `src/event_queue.py` | `collections.deque` wrapper — FIFO, single-threaded |
| DataHandler | `src/data_handler.py` | Yield-generator, one bar at a time; sole float→Decimal conversion point |
| Strategy | `src/strategy/` | BaseStrategy ABC + Reversal, Breakout, FVG implementations |
| Portfolio | `src/portfolio.py` | Positions, cash, mark-to-market, equity log — single source of truth |
| ExecutionHandler | `src/execution.py` | Slippage + commission simulation → FillEvent |
| Metrics | `src/metrics.py` | Post-loop KPI computation from equity log + fill log |
| Dashboard | `src/dashboard/` | Dash app, layouts, callbacks — read-only consumer of metrics |

**Event Flow:**
```
DataHandler.yield(bar) → MarketEvent → queue
  → Strategy.calculate_signals() → SignalEvent → queue
  → Portfolio.generate_order() → OrderEvent → queue
  → ExecutionHandler.execute_order() [+slippage+spread] → FillEvent → queue
  → Portfolio.update_fill() → equity_log update
[next bar]
POST LOOP: Metrics.compute(equity_log, fill_log) → Dashboard.render()
```

**Key invariants:** FIFO processing, one bar per outer-loop tick, Decimal everywhere downstream of DataHandler, no component references another's state directly (only via events).

---

## Build Order

1. **Phase 1 — Foundation:** `events.py` → `event_queue.py` (pure data; no dependencies)
2. **Phase 2 — Data Layer:** `data_handler.py` — yield-generator, Decimal conversion, session filters, gap handling; write `test_causality.py` FIRST
3. **Phase 3 — Strategy Layer:** `strategy/base.py` → `reversal.py`, `breakout.py`, `fvg.py`; indicator integration via pandas-ta
4. **Phase 4 — Execution Layer:** `execution.py` — slippage, spread, commission, gap-fill model
5. **Phase 5 — Portfolio Layer:** `portfolio.py` — position tracking, mark-to-market, equity log, margin enforcement
6. **Phase 6 — Engine Layer:** `backtest.py` — orchestrator, event dispatch loop, integration tests
7. **Phase 7 — Analytics Layer:** `metrics.py` — Sharpe, Sortino, MDD, Calmar (post-loop only)
8. **Phase 8 — Dashboard Layer:** `src/dashboard/` — Dash app, candlestick + markers, KPI cards, heatmap

**Rule:** Do not start the next phase until all tests for the current phase pass. Single-timeframe engine must work before adding multi-timeframe layers.

---

## Critical Pitfalls to Prevent

1. **Lookahead bias** — Use yield-generator DataHandler; never pre-compute indicators on full DataFrame; write `test_causality.py` before any strategy code; grep for `.shift(`, `resample(` inside strategy/execution modules.

2. **Same-bar fill (open vs. close execution)** — Signals from bar T fill at bar T+1's open, never T's close; write a dedicated test asserting fill timestamp equals next-bar open.

3. **Float arithmetic** — `Decimal` from day 0; string constructor only (`Decimal('0.0001')`, not `Decimal(0.0001)`); exact `Decimal` equality in PnL tests, never `pytest.approx()`; add pre-commit grep for `float(` in financial modules.

4. **Wrong Sharpe annualization factor** — `sqrt(252)` for daily, `sqrt(252*390)` for 1-min stocks, `sqrt(252*1440)` for 1-min Forex; define `ANNUALIZATION_FACTORS` dict in `metrics.py`; pass timeframe explicitly.

5. **Slippage/commission underestimation** — Forex EUR/USD realistic spread: 0.8–1.5 pips liquid, 2–5 pips off-hours; stock commission: $0–1/trade; always run friction sensitivity test (0x, 1x, 2x); strategy must survive realistic friction.

6. **State reuse across parameter sweep runs** — Each sweep iteration gets freshly instantiated DataHandler + Portfolio + Strategy + ExecutionHandler; never share instances; factory function `create_engine(params)` pattern.

7. **Gap-through stop fill** — If next bar opens past the stop price, fill at next bar's open, not at the stop price; implement configurable `gap_fill_model`; write explicit test: stop at 1.2000, next open at 1.1950, assert fill = 1.1950.

---

## Key Numbers

- **Forex spread (EUR/USD):** 0.8–1.5 pips liquid hours; 2–5 pips off-hours; use 1.0 pip as conservative default
- **Forex spread (GBP/USD):** 1.2–2.0 pips liquid hours; double off-hours
- **Forex slippage:** 0.3–1.0 pips additional on market orders (news events: up to 5 pips gap slippage)
- **Stock commission:** $0–1 per trade (retail); $0.005/share minimum for algos; use $1/trade as conservative default
- **Stock bid/ask spread:** $0.01–0.05 large-cap; $0.10–0.50 small-cap
- **Stock slippage:** 0.05%–0.15% of trade value (market orders)
- **Sharpe annualization:**
  - Daily: `sqrt(252)`
  - 1h: `sqrt(252 * 24)`; stocks: `sqrt(252 * 6.5)`
  - 5min: `sqrt(252 * 288)`
  - 1min Forex: `sqrt(252 * 1440)`; stocks: `sqrt(252 * 390)`
- **yfinance intraday limits:** 1min = 7 days max; 5min = 60 days; 1h = 730 days — must cache locally
- **Alpha Vantage free tier:** 5 calls/minute, 500 calls/day; 12s sleep between consecutive calls

---

## Anti-Patterns (Do NOT Do)

1. **Never use `.shift(-1)` or vectorized pandas operations to simulate trades** — that is lookahead bias in disguise; all trade logic goes through the event queue.

2. **Never pre-compute indicators on the full DataFrame before the backtest loop** — computing RSI on all data, then replaying bar-by-bar, means the indicator already knows future volatility; compute incrementally from a rolling buffer.

3. **Never use `float` for any financial calculation** — not for prices, not for PnL, not for position sizes; `Decimal('0.0001')` everywhere; `float` drift compounds into wrong results at 10,000+ trades.

4. **Never fill an order at the same bar's close that generated the signal** — impossible in reality; always fill at next bar's open; this single mistake produces fantasy equity curves.

5. **Never share DataHandler or Portfolio state between parameter sweep runs** — state leakage produces non-deterministic, order-dependent sweep results; always fresh-instantiate every component.

6. **Never test the final portfolio value without testing the event sequence** — a lookahead-biased engine and a correct engine can produce the same final value on some test data; assert event ORDER in causality tests.

7. **Never call Alpha Vantage API inside the sweep inner loop** — fetch once, cache as Parquet, read from cache for every sweep iteration; 500 calls/day is exhausted instantly by a 10×10 grid search.

8. **Never use Dash 4.0, pandas 3.0, or NumPy 2.4 immediately** — all released early 2026 with breaking changes; pin pandas==2.2.3, NumPy==2.2.4, Dash~=3.x until compatibility is confirmed.
