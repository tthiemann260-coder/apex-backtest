# Architecture Research: apex-backtest

> Research Date: 2026-02-21
> Scope: Greenfield event-driven backtesting engine (Python 3.12+)
> Source: QuantStart series, professional backtesting literature, apex-backtest CLAUDE.md constraints

---

## Component Overview

An event-driven backtesting engine is structured around a central message bus (the Event Queue). Every component is isolated — it only knows about the events it receives and the events it emits. No component reaches directly into another component's state.

### 1. Event Classes (`src/events.py`)

**Responsibility:** Define the four data-carrier types that flow through the system.

| Event Type    | Produced by      | Consumed by       | Key Fields                                           |
|---------------|------------------|-------------------|------------------------------------------------------|
| MarketEvent   | DataHandler      | Strategy          | symbol, timestamp, bar (OHLCV as Decimal)            |
| SignalEvent   | Strategy         | Portfolio         | symbol, direction (LONG/SHORT/EXIT), strength        |
| OrderEvent    | Portfolio        | ExecutionHandler  | symbol, order_type, quantity, direction              |
| FillEvent     | ExecutionHandler | Portfolio         | symbol, fill_price, quantity, commission, slippage   |

Events are immutable dataclasses. They carry data only — no logic, no references to other components.

**NOT allowed to do:** Contain business logic, hold references to other components, mutate after creation.

---

### 2. Event Queue (`src/event_queue.py`)

**Responsibility:** The central message bus. A thin wrapper around `collections.deque` that enforces FIFO processing.

- Single deque instance shared across the entire engine
- The Backtest Engine (main loop) reads from it
- All components append to it via `queue.append(event)`
- The loop runs until the deque is empty AND the DataHandler is exhausted

**NOT allowed to do:** Process events itself, contain market logic, hold state beyond the deque.

---

### 3. DataHandler (`src/data_handler.py`)

**Responsibility:** The sole source of truth for market data. Releases one bar per heartbeat — never more.

- Abstract base class (`abc.ABC`) with concrete subclasses:
  - `CSVDataHandler` — reads CSV/Parquet files row by row
  - `APIDataHandler` — fetches from yfinance / Alpha Vantage (cached locally)
- Uses a `yield`-generator pattern internally. The engine calls `next()` or `get_next_bar()` each iteration.
- Converts all price data to `decimal.Decimal` at the ingestion boundary (this is the ONLY place floats from external APIs are ever converted)
- Rejects zero-volume bars silently (logs them, skips them)
- Handles gaps in timestamps gracefully (no synthetic bar injection)
- Tracks what it has released: `self.latest_bars` dict, keyed by symbol, is a rolling window of the N most recent bars
- Distinction between Raw prices and Adjusted prices; handles splits/dividends
- Emits a `MarketEvent` after releasing each bar

**NOT allowed to do:** Access the event queue directly (the engine calls it and then enqueues the MarketEvent), peek ahead in the generator, hold Strategy or Portfolio references.

---

### 4. Strategy Base + Implementations (`src/strategy/`)

**Responsibility:** Transform market data observations into trading intentions (signals). Pure signal generation — no portfolio knowledge whatsoever.

- `BaseStrategy` (abstract): defines `calculate_signals(event: MarketEvent) -> None`
- Concrete strategies: `ReversalStrategy`, `BreakoutStrategy`, `FVGStrategy`
- Each strategy holds a reference to the DataHandler (read-only, historical window only)
- Each strategy holds a reference to the Event Queue (write-only, to emit SignalEvents)
- Signals include direction (LONG / SHORT / EXIT) and an optional strength/confidence float
- Multi-timeframe: strategy selects which timeframe bars to act on

**Design pattern:** Strategy Pattern — all concrete strategies are interchangeable behind the `BaseStrategy` interface. The Backtest Engine holds a list of strategies; it calls each one when a MarketEvent arrives.

**NOT allowed to do:** Access Portfolio state, issue OrderEvents directly, see bars beyond what DataHandler has released, use `.shift()` or any vectorized lookahead.

---

### 5. Portfolio (`src/portfolio.py`)

**Responsibility:** State machine for positions, cash, and equity. Translates signals into orders; reconciles fills.

- Holds `current_positions`: `dict[str, Decimal]` — quantity per symbol (negative = short)
- Holds `current_holdings`: cash, market value per position, total equity — all `Decimal`
- On `SignalEvent`: performs position sizing (risk % of equity), generates `OrderEvent`
- On `FillEvent`: updates positions and cash, logs the trade
- After each `MarketEvent`: marks all positions to market (updates unrealized PnL)
- Maintains a time-series log: list of dicts `{timestamp, cash, positions_value, total}` — this becomes the equity curve
- Enforces margin checks; triggers forced liquidation if margin breached
- Handles edge cases: zero-volume rejection, missing price data for mark-to-market

**Design pattern:** Observer Pattern — the Portfolio "observes" both SignalEvents and FillEvents through the main event loop dispatch.

**NOT allowed to do:** Reach into the DataHandler directly (it only sees what arrives via events), execute orders itself, bypass the event queue.

---

### 6. ExecutionHandler (`src/execution.py`)

**Responsibility:** Simulate the brokerage. Takes an OrderEvent and produces a FillEvent with realistic friction applied.

- Abstract base class: `BaseExecutionHandler`
- Concrete: `SimulatedExecutionHandler`
- Slippage model: percentage-based (e.g., `Decimal('0.0001')` of fill price) AND bid/ask spread simulation
- Commission model: per-trade flat fee AND per-share/per-pip cost — all `Decimal`
- Fill price calculation:
  - BUY: `close + (close * slippage_pct) + (spread / 2)`
  - SELL: `close - (close * slippage_pct) - (spread / 2)`
- Market-specific precision: Forex quantizes to 5 decimal places, Stocks to 2
- Always fills at current bar's close (no partial fills in v1)
- Designed for swap-out: `LiveExecutionHandler` can replace `SimulatedExecutionHandler` with same interface

**NOT allowed to do:** Modify the order, access portfolio state, influence Strategy logic.

---

### 7. Performance Analytics (`src/metrics.py`)

**Responsibility:** Post-backtest analysis. Computes all KPIs from the event log and equity curve. Runs AFTER the backtest loop completes.

- Inputs: Portfolio equity curve log (list of dicts), fill log (list of FillEvents)
- Outputs: dict of metrics
- Metrics computed:
  - Sharpe Ratio (annualized, N=252 for daily / N=252*390 for 1min)
  - Sortino Ratio (downside deviation only)
  - Maximum Drawdown (largest peak-to-trough drop, as Decimal)
  - Maximum Drawdown Duration (number of bars)
  - Calmar Ratio (CAGR / Max Drawdown)
  - Total Exposure Time (% of bars with open position)
  - Win Rate (winning fills / total fills)
  - Profit Factor (gross profit / gross loss)
  - CAGR
- Uses pandas + numpy for the post-loop computations ONLY (this is the explicit exception to the no-vectorized rule — post-loop analysis is not trading logic)

**NOT allowed to do:** Influence any trading decisions, be called during the backtest loop, use `.shift()` on trade decisions.

---

### 8. Backtest Engine / Main Loop (`src/backtest.py` or `src/engine.py`)

**Responsibility:** Orchestrator. Wires all components together and drives the event loop.

- Holds references to: DataHandler, list of Strategies, Portfolio, ExecutionHandler, Event Queue
- Main loop:
  1. Call `data_handler.get_next_bar()` → enqueue `MarketEvent` (or stop if exhausted)
  2. While queue is non-empty, pop event and dispatch:
     - `MarketEvent` → call each Strategy's `calculate_signals()`; call Portfolio's `update_timeindex()`
     - `SignalEvent` → call Portfolio's `generate_order()`
     - `OrderEvent` → call ExecutionHandler's `execute_order()`
     - `FillEvent` → call Portfolio's `update_fill()`
  3. Repeat from step 1
- After loop: call `metrics.compute(portfolio.equity_log, portfolio.fill_log)`

**NOT allowed to do:** Contain trading logic, access market data directly (must go through DataHandler), skip events.

---

### 9. Dashboard (`src/dashboard/`)

**Responsibility:** Visualization of backtest results. Read-only — purely presentational.

- `app.py`: Dash application entry point
- `layouts.py`: page structure, component tree
- `callbacks.py`: interactivity (timeframe selector, strategy picker, parameter sweep)
- Charts:
  - Candlestick with Buy/Sell markers overlaid
  - Equity curve line chart
  - Drawdown waterfall diagram
  - Parameter sweep heatmap (run multiple backtests, grid of Sharpe values)
  - KPI cards (Sharpe, Sortino, MDD, Win Rate, etc.)
- Takes results dict from Metrics as its data source

**NOT allowed to do:** Trigger backtest runs from within callbacks (v1), modify backtest state.

---

## Event Flow

The event loop is the heartbeat of the entire system. Each iteration of the outer loop advances time by exactly one bar. The inner loop drains all events that were enqueued as a consequence of that bar.

```
OUTER LOOP (advances time):
  DataHandler yields next bar
    → DataHandler emits MarketEvent → enqueued

INNER LOOP (drains the queue):
  Pop MarketEvent
    → Strategy.calculate_signals(MarketEvent)
        → if signal: emit SignalEvent → enqueued
    → Portfolio.update_timeindex(MarketEvent)   [mark to market]

  Pop SignalEvent
    → Portfolio.generate_order(SignalEvent)
        → if order: emit OrderEvent → enqueued

  Pop OrderEvent
    → ExecutionHandler.execute_order(OrderEvent)
        → apply slippage + commission
        → emit FillEvent → enqueued

  Pop FillEvent
    → Portfolio.update_fill(FillEvent)
        → update positions, cash, trade log

  [queue empty — advance to next bar]

POST LOOP:
  Metrics.compute(portfolio.equity_log, portfolio.fill_log)
  Dashboard.render(metrics_result)
```

**Why this eliminates lookahead bias:** The generator releases exactly one bar before the queue processes any event derived from it. A signal from bar N cannot influence bar N's fill price — it can only result in an order that is filled at bar N+1's data (or bar N's close, which has already been released). The sequential FIFO constraint makes future-data access a structural impossibility.

---

## Component Interactions

```
DataHandler ──────MarketEvent──────────────────────────────────────────────────┐
                                                                               │
                                                              ┌────────────────▼──────────────────┐
                                                              │          Event Queue               │
                                                              │       (collections.deque)          │
                                                              └────────────────┬──────────────────┘
                                                                               │
                        ┌──────────────────────────────────────────────────────┤
                        │                  Backtest Engine (dispatcher)         │
                        │                                                       │
                        │  MarketEvent ──► Strategy ──► SignalEvent             │
                        │  SignalEvent ──► Portfolio ──► OrderEvent             │
                        │  OrderEvent ──► ExecutionHandler ──► FillEvent        │
                        │  FillEvent  ──► Portfolio (update)                   │
                        └──────────────────────────────────────────────────────┘
```

**Who talks to whom (and how):**

| From              | To                  | Mechanism                          |
|-------------------|---------------------|------------------------------------|
| DataHandler       | Event Queue         | `queue.append(MarketEvent(...))`   |
| Backtest Engine   | DataHandler         | Direct method call `get_next_bar()`|
| Backtest Engine   | Strategy            | Direct method call (dispatch)      |
| Strategy          | Event Queue         | `queue.append(SignalEvent(...))`   |
| Strategy          | DataHandler         | Read-only: `data_handler.get_latest_bars()` |
| Backtest Engine   | Portfolio           | Direct method call (dispatch)      |
| Portfolio         | Event Queue         | `queue.append(OrderEvent(...))`    |
| Portfolio         | DataHandler         | Read-only: current bar price for mark-to-market |
| Backtest Engine   | ExecutionHandler    | Direct method call (dispatch)      |
| ExecutionHandler  | Event Queue         | `queue.append(FillEvent(...))`     |
| ExecutionHandler  | DataHandler         | Read-only: current bar close price |
| Backtest Engine   | Metrics             | Call after loop: `metrics.compute()`|
| Dashboard         | Metrics result      | Read-only dict passed in           |

**Dependency direction rule:** All dependencies point inward toward the Event Queue and the DataHandler. No downstream component (Strategy, Portfolio, Execution) holds a reference to an upstream event producer.

---

## Data Flow Diagram (ASCII)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          APEX-BACKTEST DATA FLOW                            │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐     bar (OHLCV,       ┌─────────────────────────┐
  │  CSV/Parquet │ ──► Decimal, ts)  ──► │      DataHandler        │
  │   / API      │                       │   (yield-generator)     │
  └──────────────┘                       └──────────┬──────────────┘
                                                    │
                                          MarketEvent (1 bar)
                                                    │
                                                    ▼
                                   ┌────────────────────────────┐
                                   │       Event Queue          │
                                   │   collections.deque        │
                                   └──────────┬─────────────────┘
                                              │
                                   ┌──────────▼─────────────────┐
                                   │     Backtest Engine         │
                                   │      (dispatcher)           │
                                   └──┬────────┬────────┬───────┘
                                      │        │        │
                              MarketEvent  SignalEvent  OrderEvent  FillEvent
                                      │        │        │              │
                              ┌───────▼──┐  ┌──▼──────┐  ┌───────────▼──────┐
                              │ Strategy │  │Portfolio│  │ ExecutionHandler  │
                              │(signals) │  │(orders, │  │(slippage, commis.)│
                              └──────────┘  │ fills,  │  └───────────────────┘
                                            │ equity) │
                                            └────┬────┘
                                                 │
                                          equity_log +
                                           fill_log
                                                 │
                                                 ▼
                                    ┌────────────────────────┐
                                    │   Metrics (post-loop)  │
                                    │ Sharpe, MDD, Sortino.. │
                                    └────────────┬───────────┘
                                                 │
                                          metrics dict
                                                 │
                                                 ▼
                                    ┌────────────────────────┐
                                    │   Dash Dashboard       │
                                    │ Charts, KPIs, Heatmap  │
                                    └────────────────────────┘

  DECIMAL BOUNDARY: All float→Decimal conversion happens at DataHandler ingestion.
  Everything downstream is decimal.Decimal.
```

---

## Build Order

Build in strict bottom-up order. Each layer depends only on what is below it.

### Phase 1 — Foundation (no dependencies)
**Build first. Everything else depends on these.**

1. **`src/events.py`** — Event dataclasses (MarketEvent, SignalEvent, OrderEvent, FillEvent)
   - Pure data containers. No logic. No imports from the project.
   - Test: instantiation, immutability, field types.

2. **`src/event_queue.py`** — Central queue wrapper around `collections.deque`
   - Depends on: events.py (type hints only)
   - Test: enqueue, dequeue, FIFO order, empty check.

### Phase 2 — Data Layer
**Build second. Strategy and Portfolio cannot be tested without data.**

3. **`src/data_handler.py`** — DataHandler ABC + CSVDataHandler
   - Depends on: events.py, event_queue.py
   - Test: yield order (strictly chronological), zero-volume rejection, Decimal conversion, boundary bar.
   - Causality test: prove generator never yields future bars.

### Phase 3 — Strategy Layer
**Build third. Requires DataHandler to provide historical bars.**

4. **`src/strategy/base.py`** — BaseStrategy ABC
   - Depends on: events.py, event_queue.py, data_handler.py
   - Test: interface enforcement (cannot instantiate without `calculate_signals`).

5. **`src/strategy/reversal.py`**, **`breakout.py`**, **`fvg.py`** — Concrete strategies
   - Depends on: base.py
   - Test: signal output correctness, no future-bar access, Decimal signal fields.

### Phase 4 — Execution Layer
**Build fourth. Portfolio needs execution to close the event cycle.**

6. **`src/execution.py`** — SimulatedExecutionHandler
   - Depends on: events.py, event_queue.py
   - Test: slippage calculation (cent-exact), commission deduction, Decimal precision, BUY vs SELL fill price.

### Phase 5 — Portfolio Layer
**Build fifth. Requires events, execution, and data to be stable.**

7. **`src/portfolio.py`** — Portfolio
   - Depends on: events.py, event_queue.py, data_handler.py
   - Test: position update after fill, cash deduction, mark-to-market, equity log shape, margin enforcement.
   - PnL test: round-trip trade must match cent-exact expected PnL.

### Phase 6 — Engine Layer
**Build sixth. Wires all prior components. Integration test surface.**

8. **`src/backtest.py`** — Backtest Engine (main loop)
   - Depends on: all of the above
   - Test: full integration run with synthetic data, event dispatch order, empty-queue termination.
   - Causality test: inject probe into DataHandler, verify no future events referenced.

### Phase 7 — Analytics Layer
**Build seventh. Runs post-loop. No runtime dependencies on trading components.**

9. **`src/metrics.py`** — Performance Analytics
   - Depends on: equity log format (agreed interface with Portfolio)
   - Test: Sharpe formula verification, MDD calculation against known series, edge cases (flat equity curve, all-loss curve).

### Phase 8 — Visualization Layer
**Build last. Read-only consumer of results.**

10. **`src/dashboard/`** — Dash app, layouts, callbacks
    - Depends on: metrics output dict (shape agreed in Phase 7)
    - Test: layout renders without error, callback returns valid figure.

---

## Design Patterns Used

### 1. Observer Pattern (implicit, via Event Queue)
The Event Queue acts as the notification mechanism. Portfolio "observes" SignalEvents and FillEvents. Strategy "observes" MarketEvents. Neither component is aware of the other — they only know the event type.

**Applied to:** DataHandler → Strategy, Portfolio → ExecutionHandler, ExecutionHandler → Portfolio

### 2. Strategy Pattern
All concrete trading strategies (`ReversalStrategy`, `BreakoutStrategy`, `FVGStrategy`) are interchangeable implementations behind the `BaseStrategy` interface. The Backtest Engine holds a list and iterates — adding or swapping strategies requires zero changes to the engine.

**Applied to:** `src/strategy/` module

### 3. Template Method Pattern
`BaseStrategy.calculate_signals()` defines the skeleton of the algorithm. Each concrete subclass fills in the specific signal logic. The base class handles guard conditions (checking event type, etc.).

**Applied to:** `BaseStrategy` → concrete strategies

### 4. Factory Pattern (light)
The Backtest Engine can be configured via a config dict or YAML, with a factory function that instantiates the correct DataHandler subclass (`CSVDataHandler` vs `APIDataHandler`) and ExecutionHandler subclass based on config flags. This enables the same engine code to run historical vs. live mode.

**Applied to:** DataHandler subclasses, ExecutionHandler subclasses

### 5. Generator / Iterator Pattern
DataHandler's bar release mechanism is a Python generator (`yield`). This is the architectural guarantee against lookahead bias — the generator's internal state advances exactly one bar per `next()` call, making it physically impossible to access bar N+2 when bar N is being processed.

**Applied to:** `DataHandler.get_next_bars()` generator

### 6. Command Pattern
Each `OrderEvent` is a Command — it encapsulates the intent (buy X of Y at market) and is passed to the ExecutionHandler for execution. The Portfolio does not execute; it commands.

**Applied to:** OrderEvent → ExecutionHandler

### 7. Null Object Pattern (recommended for v2)
`NullExecutionHandler` — fills at close with no slippage/commission. Useful for pure signal-quality testing without transaction cost noise.

---

## Boundary Rules

### DataHandler
- ALLOWED: Read files/API, yield bars one at a time, maintain rolling window of past bars, emit MarketEvent.
- NOT ALLOWED: Access Strategy or Portfolio, peek ahead in the generator, hold any position or cash state, yield more than one bar per engine iteration.

### Strategy
- ALLOWED: Read `data_handler.get_latest_bars()` for historical window, emit SignalEvent to queue.
- NOT ALLOWED: Read Portfolio state (positions, cash), emit OrderEvents directly, access bars beyond what DataHandler has released, use any vectorized operation on the full data series.

### Portfolio
- ALLOWED: Read current bar price from DataHandler for mark-to-market, maintain position/cash state, emit OrderEvents, update on FillEvents, append to equity log.
- NOT ALLOWED: Execute orders itself, access ExecutionHandler directly, read Strategy internals, use future prices.

### ExecutionHandler
- ALLOWED: Read current bar price from DataHandler (the already-released close price), apply slippage and commission models, emit FillEvents.
- NOT ALLOWED: Modify the OrderEvent, access Portfolio state, influence Strategy signals, reject orders for risk reasons (that is Portfolio's job).

### Metrics
- ALLOWED: Use pandas/numpy for vectorized computation on the completed equity log and fill log.
- NOT ALLOWED: Be called during the event loop, influence any trading decisions, access DataHandler or the event queue.

### Dashboard
- ALLOWED: Read the metrics result dict and portfolio fill log for visualization.
- NOT ALLOWED: Trigger backtest runs from within callbacks (v1), write to any backtest state, import from strategy or portfolio modules directly.

### Event Queue
- ALLOWED: Accept any event append from any component, deliver events in FIFO order to the Backtest Engine.
- NOT ALLOWED: Process events itself, filter or reorder events, hold business logic.

### Backtest Engine
- ALLOWED: Wire components together, drive the outer loop, dispatch events to correct handlers.
- NOT ALLOWED: Contain trading logic, access market data directly (must go through DataHandler), skip or reorder events.

---

## Key Architectural Invariants

These must hold at all times. Violations = bugs.

1. **Strict Chronological Order:** DataHandler yields bars in ascending timestamp order. No bar is ever yielded twice.
2. **FIFO Event Processing:** Events are processed in the exact order they were enqueued. No priority queue.
3. **Decimal Everywhere:** No `float` crosses a component boundary in any financial calculation. The DataHandler is the sole float→Decimal conversion point.
4. **Strategy Isolation:** A strategy can only read bars that have already been yielded by the DataHandler. This is enforced by `get_latest_bars(N)` returning only from the released buffer.
5. **One Bar, One Market Event:** Each generator `next()` call produces exactly one MarketEvent for each tracked symbol.
6. **Portfolio as Single Source of Truth:** Position and cash state lives only in Portfolio. ExecutionHandler and Strategy do not cache position state.
7. **Post-Loop Analytics Only:** Metrics computation is never called inside the event loop.

---

*Sources consulted:*
- [QuantStart: Event-Driven Backtesting with Python, Parts I–VIII](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [Medium: Building a Robust Backtesting Framework — Event-Driven Architecture](https://medium.com/@jpolec_72972/building-a-robust-backtesting-framework-event-driven-architecture-22aa77eedf34)
- [Medium: How I Built an Event-Driven Backtesting Engine in Python](https://timkimutai.medium.com/how-i-built-an-event-driven-backtesting-engine-in-python-25179a80cde0)
- [OpenEngine: Building Your First Event-Driven Backtesting Engine](https://www.marketcalls.in/openengine/openengine-building-your-first-event-driven-backtesting-engine-a-step-by-step-research-note.html)
- [VertoxQuant: Event-Driven Backtester in Python](https://www.vertoxquant.com/p/event-driven-backtester-in-python)
- [IBKR: A Practical Breakdown of Vector-Based vs. Event-Based Backtesting](https://www.interactivebrokers.com/campus/ibkr-quant-news/a-practical-breakdown-of-vector-based-vs-event-based-backtesting/)
- [LuxAlgo: Backtesting Limitations: Slippage and Liquidity](https://www.luxalgo.com/blog/backtesting-limitations-slippage-and-liquidity-explained/)
- apex-backtest `CLAUDE.md` (project constraints, 2026-02-21)
