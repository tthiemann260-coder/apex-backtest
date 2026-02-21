# Roadmap: apex-backtest

**Created:** 2026-02-21
**Phases:** 8
**Requirements:** 54 mapped
**Depth:** Comprehensive

---

## Phase 1: Event Foundation

**Goal:** Create the immutable event type system and the central FIFO event queue that all other components depend on.
**Dependencies:** None
**Requirements:** EDA-01, EDA-02, TEST-01
**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md — Project scaffolding + immutable event types + event type tests
- [ ] 01-02-PLAN.md — EventQueue (TDD) + queue tests + causality test skeleton

### Success Criteria
1. Four event types exist as `@dataclass(frozen=True)`: `MarketEvent`, `SignalEvent`, `OrderEvent`, `FillEvent` — instantiation raises `FrozenInstanceError` on mutation attempt.
2. `EventQueue` wraps `collections.deque` and processes events in strict FIFO order — a sequence of 100 enqueued events dequeues in identical order.
3. `test_causality.py` skeleton exists with at least one passing placeholder test; causality test infrastructure is importable.
4. All event classes carry the required fields with correct types (symbol, timestamp, direction, quantity, price as `Decimal` where applicable).
5. `pytest tests/test_events.py` passes with zero warnings and zero failures.

---

## Phase 2: Data Layer

**Goal:** Build the `DataHandler` with a yield-generator pattern that releases bars one at a time, converts all prices to `Decimal`, caches to Parquet, fetches from APIs, handles gaps, and rejects null-volume bars.
**Dependencies:** Phase 1 (MarketEvent must exist before DataHandler can emit it)
**Requirements:** DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08, DATA-09, TEST-05

### Success Criteria
1. `DataHandler.stream_bars()` yields bars sequentially — accessing index `i+1` before consuming index `i` is structurally impossible (generator does not advance until `next()` is called).
2. All float OHLCV values from yfinance and Alpha Vantage are converted to `Decimal` via string constructor at the ingestion boundary; no `float` exists downstream.
3. Local Parquet cache is written after first API fetch; a second run with the same symbol/date range reads from disk and makes zero network calls.
4. Bars with `volume == 0` are silently skipped and never emitted as `MarketEvent`; `test_null_volume_rejection` passes with exact assertion.
5. Gap dates (weekends, holidays, missing dates) are forward-filled; multi-symbol bar alignment for 1min through Daily timeframes produces identical timestamp index across symbols.

---

## Phase 3: Strategy Layer

**Goal:** Build the abstract `BaseStrategy` framework and three concrete example strategies (Reversal, Breakout, FVG) that generate signals strictly from historical data via pandas-ta indicators.
**Dependencies:** Phase 1 (SignalEvent), Phase 2 (MarketEvent input)
**Requirements:** STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, STRAT-06, STRAT-07, STRAT-08

### Success Criteria
1. `BaseStrategy` is an abstract base class (`abc.ABC`) with a mandatory `calculate_signals(event: MarketEvent) -> Optional[SignalEvent]` hook — instantiating `BaseStrategy` directly raises `TypeError`.
2. Signals are restricted to three values: `LONG`, `SHORT`, `EXIT` — any other value causes a `ValueError` at `SignalEvent` creation.
3. All three strategies (`ReversalStrategy`, `BreakoutStrategy`, `FVGStrategy`) produce at least one `SignalEvent` on a synthetic 200-bar test dataset without raising exceptions.
4. Indicator computation uses pandas-ta exclusively and operates on a rolling buffer of historical bars — no indicator is pre-computed on the full dataset before the loop begins.
5. Parameter injection works at instantiation (`ReversalStrategy(sma_period=20, rsi_threshold=30)`) and is carried through all signal logic without global state.

---

## Phase 4: Execution Layer

**Goal:** Build the `ExecutionHandler` that simulates realistic order fills — next-bar-open for market orders, intra-bar H/L check for limit/stop orders, plus slippage, spread, and commission — entirely in `Decimal`.
**Dependencies:** Phase 1 (OrderEvent, FillEvent), Phase 2 (bar data for fill price reference)
**Requirements:** EXEC-01, EXEC-02, EXEC-03, EXEC-04, EXEC-05, EXEC-06, EXEC-07, TEST-03, TEST-04

### Success Criteria
1. Market orders are filled at the open of the bar following signal generation — `FillEvent.timestamp` equals `next_bar.open_time`; `test_same_bar_fill_prevention` asserts this with a synthetic two-bar sequence.
2. Limit orders fill only when intra-bar High (for sells) or Low (for buys) reaches the limit price; orders that are not touched remain open and carry to the next bar.
3. Gap-through stop fill test passes: stop set at 1.2000, next bar opens at 1.1950, assert `FillEvent.fill_price == Decimal('1.1950')` (not 1.2000).
4. Commission (flat per trade + per share/pip), spread (bid/ask at entry and exit), and slippage (percentage-based) are all applied and stored as separate `Decimal` fields in `FillEvent`.
5. All arithmetic — fill price, gross cost, commission, net cost — uses `Decimal` arithmetic exclusively; no `float` appears in `execution.py`.

---

## Phase 5: Portfolio Layer

**Goal:** Build the `Portfolio` component that tracks cash and positions in `Decimal`, computes mark-to-market equity after each bar, enforces margin, applies FIFO PnL attribution, and rejects invalid orders.
**Dependencies:** Phase 1 (FillEvent input, OrderEvent output), Phase 4 (FillEvent structure defined)
**Requirements:** PORT-01, PORT-02, PORT-03, PORT-04, PORT-05, PORT-06, PORT-07, TEST-02, TEST-06

### Success Criteria
1. Cash and all position quantities are stored as `Decimal`; `test_pnl_accuracy.py` verifies a round-trip trade (buy 100 shares at 50.00, sell at 52.00) produces exactly `Decimal('200.00')` net PnL with no `pytest.approx()`.
2. Percentage-based position sizing computes correctly: 1% risk on a $10,000 account with a 20-pip stop yields the exact lot size in `Decimal`.
3. Mark-to-market equity log is updated after every bar; `portfolio.equity_log` has one entry per bar consumed, with correct cash + open position value.
4. Margin monitoring triggers a simulated forced liquidation (close all positions at current bid) when equity falls below the required margin threshold.
5. Portfolio balance invariant test passes after every trade: `cash + sum(position_value) == initial_equity + realized_pnl`.

---

## Phase 6: Engine Integration

**Goal:** Wire all five components (DataHandler, Strategy, Portfolio, ExecutionHandler, EventQueue) into the `Backtest` orchestrator that drives the event dispatch loop and guarantees sweep isolation.
**Dependencies:** Phase 1, Phase 2, Phase 3, Phase 4, Phase 5 (all components must exist)
**Requirements:** EDA-03, EDA-04

### Success Criteria
1. A full backtest run on a 500-bar synthetic dataset completes without exceptions; the orchestrator dispatches each event to exactly one component with no trading logic of its own.
2. Events flow in correct causal order: `MarketEvent` → `SignalEvent` → `OrderEvent` → `FillEvent` — `test_causality.py` asserts timestamp ordering is strictly non-decreasing across the event log.
3. Each parameter sweep iteration instantiates fresh `DataHandler`, `Strategy`, `Portfolio`, and `ExecutionHandler` objects via a `create_engine(params)` factory; shared state between iterations is verified absent.
4. Integration test with two consecutive sweep runs on identical parameters produces identical equity logs (deterministic, no state leakage).
5. Engine exits cleanly when the data stream is exhausted, writing complete `equity_log` and `fill_log` to disk.

---

## Phase 7: Analytics Layer

**Goal:** Compute all nine performance metric groups (PnL, Sharpe, Sortino, MDD, Calmar, Win Rate, Trade Stats, Exposure, and annualization-correct Sharpe per timeframe) post-loop from the equity log and fill log.
**Dependencies:** Phase 6 (equity_log and fill_log must be produced by a complete backtest run)
**Requirements:** METR-01, METR-02, METR-03, METR-04, METR-05, METR-06, METR-07, METR-08, METR-09

### Success Criteria
1. All nine metric groups are computed exclusively in `metrics.py` after the event loop ends — no metric logic exists inside the event loop itself.
2. Sharpe Ratio uses the correct annualization factor per timeframe: `sqrt(252)` for Daily, `sqrt(252*390)` for 1-min stocks, `sqrt(252*1440)` for 1-min Forex — verified by unit tests with known synthetic equity series.
3. Maximum Drawdown returns both absolute value and percentage, plus drawdown duration in bars — tested against a hand-computed 10-bar equity sequence.
4. CAGR computation is tested with a 2-year synthetic run: start equity $10,000, end equity $14,400 asserts `CAGR == Decimal('0.20')` (exactly 20% per year).
5. `metrics.compute(equity_log, fill_log, timeframe)` returns a single `MetricsResult` dataclass with all fields populated; missing fields raise `MetricsComputationError` rather than returning `None`.

---

## Phase 8: Dashboard Layer

**Goal:** Build the interactive Dash localhost web application with candlestick chart and trade markers, equity curve, drawdown chart, KPI panel, interactive selectors, and parameter sweep heatmap — reaching 90% test coverage.
**Dependencies:** Phase 7 (MetricsResult must be available), Phase 6 (fill_log for trade markers), Phase 2 (OHLCV data for candlestick)
**Requirements:** DASH-01, DASH-02, DASH-03, DASH-04, DASH-05, DASH-06, DASH-07, TEST-07

### Success Criteria
1. `python src/dashboard/app.py` launches a Dash app accessible at `http://localhost:8050` without errors.
2. Candlestick chart renders with correct OHLC bars and overlays green (buy) and red (sell) triangle markers at the exact fill price and timestamp from `fill_log`.
3. Equity curve and drawdown waterfall chart render correctly from `equity_log`; drawdown is shown as negative values from peak.
4. KPI panel displays Sharpe, Sortino, Max Drawdown, Calmar Ratio, Win Rate, Net PnL, and Total Exposure Time — sourced from `MetricsResult`.
5. Parameter sweep heatmap renders a 2D grid from sweep results with color intensity representing Sharpe Ratio; interactive timeframe and strategy selection dropdowns trigger Dash callbacks and update all charts.
6. `pytest --cov=src tests/` reports coverage >= 90%; `pytest tests/test_dashboard.py` passes all layout and callback unit tests.

---

## Dependency Graph

```
Phase 1 (Events)
    └── Phase 2 (Data)
            └── Phase 3 (Strategy)
            └── Phase 4 (Execution)
                    └── Phase 5 (Portfolio)
                            └── Phase 6 (Engine Integration)
                                    └── Phase 7 (Analytics)
                                            └── Phase 8 (Dashboard)
```

## Requirements Coverage Summary

| Phase | Requirements | Count |
|-------|-------------|-------|
| 1 | EDA-01, EDA-02, TEST-01 | 3 |
| 2 | DATA-01–09, TEST-05 | 10 |
| 3 | STRAT-01–08 | 8 |
| 4 | EXEC-01–07, TEST-03, TEST-04 | 9 |
| 5 | PORT-01–07, TEST-02, TEST-06 | 9 |
| 6 | EDA-03, EDA-04 | 2 |
| 7 | METR-01–09 | 9 |
| 8 | DASH-01–07, TEST-07 | 8 |
| **Total** | | **58 mapped** |

> Note: 54 v1 requirements + 4 testing requirements distributed across phases as specified in REQUIREMENTS.md traceability table.

---

## Critical Pitfalls (Carried Forward from Research)

- **Lookahead Bias:** Write `test_causality.py` before any strategy code. The yield-generator DataHandler is the structural solution — never pre-compute indicators on full DataFrames.
- **Same-Bar Fill:** Signals on bar T fill at bar T+1's open. Enforced by `EXEC-01` and `TEST-03`.
- **Float Arithmetic:** `Decimal` from day 0. `TEST-02` uses exact `Decimal` equality, never `pytest.approx()`.
- **Sharpe Annualization:** `ANNUALIZATION_FACTORS` dict in `metrics.py` keyed by timeframe string. Covered by `METR-02`.
- **Sweep State Reuse:** `create_engine(params)` factory pattern enforced by `EDA-04`. Covered in Phase 6.
- **Gap-Through Stop:** Fill at next open, not at stop price. Covered by `EXEC-06` and `TEST-04`.
- **API Rate Limits:** yfinance intraday limits (1min = 7 days max). Alpha Vantage: 5 calls/min, 500/day. Cache to Parquet always (`DATA-04`).
- **Library Pins:** pandas==2.2.3, NumPy==2.2.4, Dash~=3.x. Do not upgrade until compatibility confirmed.

---
*Roadmap created: 2026-02-21*
*All 54 v1 requirements mapped across 8 phases.*
