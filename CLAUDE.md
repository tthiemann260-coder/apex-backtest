# apex-backtest — Workspace Rules

## Project Identity
- **Name:** apex-backtest
- **Type:** Event-Driven Backtesting Engine + Dash Dashboard
- **Language:** Python 3.12+
- **Location:** `C:\Users\Tobias\OneDrive\Desktop\Backtest`
- **Owner:** Tobias (personal use only)

## ABSOLUTE RULES (NEVER VIOLATE)

### 1. NO Vectorized Trading Logic
- NEVER use `.shift(-1)`, `.shift()` or vectorized Pandas operations to simulate trades
- NEVER allow the strategy to access future data points
- ALL trade simulation MUST go through the Event Queue
- Look-Ahead Bias = project failure

### 2. Event-Driven Architecture (EDA)
- Central Event Queue: `collections.deque`
- Event Types: `MarketEvent` → `SignalEvent` → `OrderEvent` → `FillEvent`
- DataHandler: Yield-Generator only — one bar at a time, chronologically
- Strategy sees ONLY current and past bars, NEVER future bars
- Event loop processes events one at a time in strict FIFO order

### 3. decimal.Decimal for ALL Financial Math
- Prices, balances, position sizes, commissions, slippage: ALL `decimal.Decimal`
- NEVER use `float` for PnL calculations or price comparisons
- Use `Decimal('0.01')` not `Decimal(0.01)` (string constructor only)
- Quantize to appropriate precision per market (Forex: 5 decimals, Stocks: 2 decimals)

### 4. LYNX Isolation
- This project is 100% independent from the LYNX project
- NEVER modify, reference, or depend on any LYNX files
- Separate git repo, separate dependencies, separate everything

## Architecture Constraints

### DataHandler
- Yield-generator pattern: `yield` one bar at a time
- Support CSV/Parquet import AND API fetch (yfinance, Alpha Vantage)
- Point-in-Time data: distinguish Raw vs Adjusted prices
- Handle corporate actions (splits, dividends)
- Reject zero-volume bars
- Handle timestamp gaps gracefully

### ExecutionHandler
- Slippage model: percentage-based AND bid/ask spread simulation
- Commission model: per-trade AND per-share
- Fill price = market price +/- slippage - commissions
- All in decimal.Decimal

### Portfolio
- Cash + Positions tracking with decimal.Decimal
- Edge cases: zero-volume rejection, margin monitoring, forced liquidation
- Missing date handling
- Position sizing based on account equity

### Strategy Framework
- Base class with `calculate_signals(event)` method
- Built-in examples: Reversal, Breakout, FVG (Fair Value Gap)
- Multi-timeframe support (1min to Daily)
- Strategies ONLY see historical data via DataHandler's current window

### Metrics
- Sharpe Ratio, Sortino Ratio, Maximum Drawdown, Calmar Ratio
- Total Exposure Time, Win Rate, Profit Factor
- All computed from the event log, NOT from vectorized equity curves

### Dashboard (Dash/Plotly)
- Candlestick chart with Buy/Sell markers
- Drawdown waterfall diagram
- Parameter sweep heatmap
- KPI cards for all metrics
- Interactive timeframe/strategy selection

## Tech Stack
- **Runtime:** Python 3.12+
- **Core:** collections.deque, decimal.Decimal, dataclasses, abc
- **Data:** yfinance, alpha_vantage (free tier), pandas (data loading only, NOT trading logic)
- **Dashboard:** dash, plotly, dash-bootstrap-components
- **Testing:** pytest, pytest-cov, unittest.mock
- **Data Storage:** CSV/Parquet files (local)
- **No external paid services**

## Testing Rules (TDD)
- Every module gets unit tests BEFORE or WITH implementation
- Causality tests: prove no future data access
- PnL verification: cent-exact matching after trades
- Use pytest fixtures and mocks for deterministic tests
- Minimum coverage target: 90%

## File Structure Convention
```
apex-backtest/
├── CLAUDE.md                  # This file — workspace rules
├── .planning/                 # GSD planning documents
├── src/
│   ├── __init__.py
│   ├── events.py              # Event classes (Market, Signal, Order, Fill)
│   ├── event_queue.py         # Central event queue + loop
│   ├── data_handler.py        # DataHandler with yield-generator
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── base.py            # Abstract strategy base class
│   │   ├── reversal.py        # Mean reversion strategy
│   │   ├── breakout.py        # Breakout/momentum strategy
│   │   └── fvg.py             # Fair Value Gap strategy
│   ├── portfolio.py           # Portfolio + position management
│   ├── execution.py           # ExecutionHandler (slippage, commissions)
│   ├── metrics.py             # KPI calculations
│   └── dashboard/
│       ├── __init__.py
│       ├── app.py             # Dash app entry point
│       ├── layouts.py         # Dashboard layouts
│       └── callbacks.py       # Interactive callbacks
├── tests/
│   ├── __init__.py
│   ├── test_events.py
│   ├── test_data_handler.py
│   ├── test_strategy.py
│   ├── test_portfolio.py
│   ├── test_execution.py
│   ├── test_metrics.py
│   ├── test_causality.py      # Look-ahead bias prevention tests
│   └── test_pnl_accuracy.py   # Cent-exact PnL verification
├── data/                      # Local market data files
├── config/                    # Strategy & engine configuration
├── requirements.txt
└── pyproject.toml
```

## Git Conventions
- Commit messages: `type: description` (feat, fix, test, docs, refactor)
- Branch: `main` for stable, feature branches for development
- Never force-push to main

## Development Workflow
1. Plan the module (architecture review)
2. Write tests first (TDD)
3. Implement module
4. Run tests — all must pass
5. Commit with descriptive message
6. Update CLAUDE.md if architecture changes

---
*Last updated: 2026-02-21 — Project initialization*
