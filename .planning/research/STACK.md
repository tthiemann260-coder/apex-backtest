# Stack Research: apex-backtest

**Date:** 2026-02-21
**Researcher:** Claude (claude-sonnet-4-6)
**Project:** apex-backtest — Event-Driven Backtesting Engine
**Scope:** Forex (EUR/USD, GBP/USD) + US Stocks (NYSE, NASDAQ), personal use, zero cost

---

## Recommended Stack

### Core Runtime

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **Python** | 3.12.x | Sweet spot: 3.12 is the most stable "fast Python" release with ~25% speed improvements over 3.11. Avoid 3.13 — its free-threaded mode is still experimental and most financial libs (NumPy 2.4, pandas 3.x) fully support 3.12 but have lagging 3.13 wheels. | HIGH |
| **decimal (stdlib)** | built-in | The only correct choice for financial arithmetic. Configurable precision (default 28 sig. digits), deterministic rounding via `ROUND_HALF_UP`, and no float representaton errors. Use `Decimal('0.0001')` string literals — never `Decimal(0.0001)`. Set `getcontext().prec = 28` globally at engine startup. | HIGH |
| **collections.deque (stdlib)** | built-in | O(1) append and popleft for the central event queue. Thread-safe for single-producer/single-consumer. Zero dependencies. For a single-threaded simulation loop this is faster and simpler than `asyncio.Queue` (which adds coroutine overhead) or `queue.Queue` (which adds mutex overhead for multi-threading you don't need). | HIGH |
| **dataclasses (stdlib)** | built-in | Use `@dataclass(frozen=True)` for immutable Event objects (MarketEvent, SignalEvent, OrderEvent, FillEvent). Immutable events are critical: once placed on the queue they must not be mutated by any handler. | HIGH |
| **enum (stdlib)** | built-in | `EventType`, `OrderSide`, `OrderType`, `AssetClass` enums. Prevents stringly-typed bugs in the event bus. | HIGH |

---

### Data Acquisition

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **yfinance** | 1.0.x | Major 1.0 release dropped Jan 24, 2026. Provides free OHLCV data for US stocks and some Forex pairs going back decades. Handles split/dividend adjustments. No API key required. Primary source for US equities (NYSE, NASDAQ). NOTE: it is an unofficial Yahoo Finance scraper — data can break briefly when Yahoo changes their API. Always cache to local SQLite/Parquet after first fetch. | HIGH |
| **alpha_vantage** | 3.0.x | Free tier: 500 API calls/day. Use as secondary source for Forex (EUR/USD, GBP/USD) where yfinance Forex data is thinner. Provides proper FX OHLCV at 1min resolution. Requires free API key from alphavantage.co. Rate-limit wrapper is essential on the free tier. | MEDIUM |
| **requests** | 2.32.x | HTTP client for direct Alpha Vantage REST calls when the `alpha_vantage` wrapper adds too much abstraction. Also useful for building a future exchange adapter. Stable, ubiquitous, zero surprises. | HIGH |
| **pytz / zoneinfo (stdlib 3.9+)** | stdlib | All timestamps must be timezone-aware. US stocks trade in `America/New_York`. Forex is 24/5 in UTC. Use `zoneinfo` (stdlib since 3.9) as the primary tz library. `pytz` only if a dependency forces it. Never use naive datetimes in the engine. | HIGH |

---

### Data Storage & Processing

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **pandas** | 2.2.x (pin to 2.2.3) | **DO NOT upgrade to pandas 3.0 yet.** Pandas 3.0 (released Jan 21, 2026) introduces Copy-on-Write semantics and removes `object` dtype inference for strings — both are breaking changes that affect virtually every financial data pipeline. The 2.2.x series is stable, fully compatible with NumPy 2.x, and supported. Pin `pandas==2.2.3` and plan a 3.0 migration in a separate branch after the engine is working. | HIGH |
| **NumPy** | 2.2.x (pin to 2.2.4) | NumPy 2.4.0 is the absolute latest (Dec 20, 2025) but introduces annotation-API changes. Use 2.2.x as the stable LTS-equivalent — full pandas 2.2 compatibility confirmed, no breaking changes for financial calculations. NumPy is used for vectorized indicator math (rolling windows, EMA, ATR) over bar arrays before events are emitted. | HIGH |
| **SQLite (stdlib `sqlite3`)** | stdlib | Zero-configuration local persistence. Store all downloaded OHLCV bars in a SQLite database (`data/market_data.db`). Schema: one table per symbol+timeframe (e.g., `eurusd_1min`). Avoids re-downloading on every run. Faster than reading thousands of individual CSV files. For personal use and single-machine deployment, SQLite is sufficient — no PostgreSQL needed. | HIGH |
| **pyarrow** | 18.x | Parquet read/write for bulk data export/import. Use pyarrow to serialize large bar datasets to Parquet for faster I/O than SQLite for read-heavy workloads (backtests reading millions of 1-min bars). Also enables DataFrame `pd.read_parquet()` with column pruning. Optional but highly recommended for 1-min timeframes at scale. | MEDIUM |
| **SQLAlchemy** | 2.0.46 | ORM layer over SQLite for the trade log, portfolio state, and configuration tables. Use the modern 2.0 `Session` API with `mapped_column`. Do NOT use SQLAlchemy 2.1 (still in beta as of 2026-01-21). SQLAlchemy adds type safety and query composability compared to raw `sqlite3` calls. | HIGH |

---

### Financial Calculations & Indicators

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **pandas-ta** | 0.3.14b | Technical analysis library built on pandas. Provides ATR, EMA, SMA, RSI, MACD, Bollinger Bands, and Swing High/Low detection needed for Reversal and Breakout strategies. Stays within the pandas 2.x API. Alternative `ta-lib` requires C compilation which is painful on Windows — avoid. | MEDIUM |
| **scipy** | 1.14.x | Statistical functions for performance metrics: rolling Sharpe ratio, drawdown analysis, return distribution tests. Not needed for the core event loop but essential for the analytics/reporting layer. | MEDIUM |

Note on FVG (Fair Value Gap) detection: This is pure price-action logic (gap between candle[i-2].high and candle[i].low). Implement it natively in the engine using `decimal.Decimal` comparisons — do not depend on an external library for this.

---

### Dashboard & Visualization

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **dash** | 3.x (latest ~3.0.x as of Feb 2026) | The project brief mandates Dash. It is the correct choice: native Plotly integration, reactive callbacks without writing JavaScript, and strong financial chart support. Dash 4.0.0 was released on PyPI in Feb 2026 — verify stability before adopting. The 3.x branch is production-ready. | HIGH |
| **plotly** | 6.x | Bundled with Dash but pin explicitly. `plotly.graph_objects.Candlestick` is the primary chart type. Supports rangeslider, multi-panel layouts (price + volume + indicators), and theme customization. Use `go.Figure` with `make_subplots` for the multi-panel backtest dashboard. | HIGH |
| **dash-bootstrap-components** | 1.6.x | Bootstrap 5 grid and component library for Dash. Provides responsive layouts (sidebar + main chart), cards for metrics (Total Return, Sharpe, Max Drawdown), and modals for strategy parameters. Much faster than building raw Dash HTML layout. | HIGH |
| **dash-ag-grid** | 31.x | Interactive trade log table. Sortable, filterable, paginated grid component for Dash. Display all trades with entry/exit price, PnL, and signal type columns. Far superior to `dash_table.DataTable` for large trade sets. | MEDIUM |

Dashboard Architecture:
- Page 1 — Backtest Runner: strategy selector, date range picker, run button, progress indicator
- Page 2 — Equity Curve: Plotly line chart of portfolio value over time vs benchmark
- Page 3 — Trade Chart: Candlestick + signal markers (entry/exit arrows) + indicator overlays
- Page 4 — Trade Log: dash-ag-grid table of all fills
- Page 5 — Statistics: Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor cards

---

### Testing

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **pytest** | 8.4.x | The project mandates TDD. pytest 8.x is the current stable series (8.4.0 released in 2025). Use `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` for configuration. Fixtures are the correct pattern for injecting fake market data and mock event queues into unit tests. | HIGH |
| **pytest-cov** | 5.x | Coverage measurement integrated into pytest via `--cov` flag. Target: 90%+ coverage on all engine components. Generate HTML reports to identify untested branches in order routing and position sizing logic. | HIGH |
| **pytest-mock** | 3.14.x | `mocker` fixture for patching `yfinance.download()`, `alpha_vantage` API calls, and Dash callbacks during unit tests. Prevents any test from making real network calls. | HIGH |
| **hypothesis** | 6.x | Property-based testing for critical financial math. Generate random `Decimal` prices, lot sizes, and pip values — verify that position sizing, PnL calculation, and slippage models hold their invariants under all inputs. Especially important for Forex pip arithmetic. | MEDIUM |
| **freezegun** | 1.5.x | Freeze time for deterministic timestamp tests. Critical for testing the data handler's temporal discipline (no lookahead bias) and timezone-aware bar generation. | HIGH |

TDD Strategy for Event-Driven Architecture:
1. Test each Event dataclass: construction, immutability, field types
2. Test each Handler in isolation: given this Event, expect these side effects on queue
3. Test the full event loop with a synthetic 10-bar dataset: verify correct event sequence
4. Test Strategy signal generation: known bar patterns → expected SignalEvent
5. Test Portfolio: fill events → correct position and cash updates using Decimal
6. Integration test: run full backtest on 30 days of synthetic data, assert PnL = known value

---

### Development Tools

| Library | Version | Rationale | Confidence |
|---------|---------|-----------|------------|
| **pydantic** | 2.12.x | Data validation for configuration objects (StrategyConfig, BacktestConfig, BrokerConfig). Use `model_validator` to enforce business rules (e.g., stop_loss_pct must be negative, start_date < end_date). Pydantic v2 is Rust-backed — validation of config at startup adds zero perceptible overhead. | HIGH |
| **loguru** | 0.7.x | Replace Python's standard `logging` with loguru. Single `from loguru import logger` import, zero configuration boilerplate, structured JSON sink for trade events, automatic exception traceback formatting, file rotation. For a personal project this drastically reduces logging ceremony. Bridge with stdlib `logging.Handler` if any dependency emits stdlib logs. | HIGH |
| **python-dotenv** | 1.0.x | Load API keys (`ALPHA_VANTAGE_API_KEY`) from a `.env` file. Never hardcode API keys. `.env` goes in `.gitignore`. | HIGH |
| **ruff** | 0.9.x | All-in-one linter + formatter replacing flake8 + black + isort. 10-100x faster than the tools it replaces. Single `ruff.toml` config. Run as pre-commit hook. Essential for maintaining consistent style across the `src/` package. | HIGH |
| **mypy** | 1.13.x | Static type checking. The event-driven architecture relies heavily on correct event types flowing between components — mypy catches `OrderEvent` being passed to a `MarketEvent` handler at compile time, not at runtime. Use `--strict` mode from day one. | HIGH |
| **pre-commit** | 3.8.x | Git pre-commit hooks running ruff + mypy on every commit. Prevents broken code from entering the codebase. `.pre-commit-config.yaml` with `ruff --fix` and `mypy`. | HIGH |
| **pip-tools** | 7.4.x | Pin all dependencies via `requirements.in` → `requirements.txt` (compiled, with hashes). Guarantees reproducible installs. Use `pip-compile --generate-hashes`. Alternative: use `uv` (Astral, 2025) which is 10-100x faster than pip-tools and compatible. | HIGH |

---

## Anti-Recommendations (What NOT to Use)

| Library | Why NOT |
|---------|---------|
| **Zipline / Zipline-Reloaded** | Designed for Python 3.5-3.6. Installing in 2025/2026 requires forks and workarounds. Per-bar Python execution is slow at minute-level data for thousands of assets. Not worth the dependency hell for a greenfield project. |
| **Backtrader** | Last meaningful commit was 2021. Unmaintained. Has its own ORM/data feed abstraction that fights against custom event-driven architecture. Plotting via matplotlib is inadequate vs Dash. |
| **VectorBT** | Excellent for vectorized backtesting but fundamentally incompatible with event-driven architecture. VectorBT operates on entire arrays at once — it cannot model realistic order routing, partial fills, or slippage in a bar-by-bar simulation. |
| **QuantConnect LEAN** | Cloud-first, Java/C# core, enormous dependency footprint. Not suitable for a lightweight personal Python engine. |
| **float arithmetic** | Never use Python `float` for price, quantity, or PnL calculations. `0.1 + 0.2 == 0.3` is `False` in float. Use `decimal.Decimal` with string literals throughout. The entire engine must enforce this at the type level. |
| **pandas 3.0.x** | Released January 21, 2026 with Copy-on-Write semantics as default. The new string dtype and removed chained-assignment behavior will silently break data pipeline code written against 2.x. Pin `pandas==2.2.3` until the engine is stable, then migrate deliberately. |
| **asyncio for the event loop** | Asyncio adds coroutine overhead and complexity that is not needed for a deterministic, single-threaded backtesting simulation. `collections.deque` with a `while queue: event = queue.popleft()` loop is simpler, faster, and easier to debug. Use asyncio only if you later add live trading with concurrent broker connections. |
| **ta-lib** | Requires compiling C extensions. On Windows this requires Visual Studio Build Tools and is brittle across Python versions. Use `pandas-ta` instead — pure Python, same indicators, easier to install. |
| **matplotlib** | Adequate for quick plots but insufficient for the interactive Dash dashboard. Do not mix matplotlib and Plotly in the same project. Commit to Plotly exclusively. |
| **NumPy 2.4.x (immediately)** | Latest release (Dec 20, 2025) — too new. Some annotation API changes may affect pandas 2.2.x compatibility. Use NumPy 2.2.4 (the stable LTS-equivalent) until pandas 2.2.x + NumPy 2.4.x compatibility is confirmed by the pandas team. |
| **Dash 4.0.x (immediately)** | Released Feb 2026, very fresh. Review the changelog for breaking changes before adopting. Use Dash 3.x until 4.0 stabilizes. |

---

## Version Compatibility Matrix

```
Python         3.12.x          (required minimum, avoid 3.13 for now)
├── pandas     2.2.3           (DO NOT use 3.x yet)
├── NumPy      2.2.4           (compatible with pandas 2.2.3, verified)
├── pyarrow    18.x            (Parquet support, compatible with pandas 2.2.x)
├── SQLAlchemy 2.0.46          (stable 2.0 series, not 2.1 beta)
├── pydantic   2.12.x          (Rust core, fast, Python 3.12 wheels available)
│
├── yfinance   1.0.x           (major release Jan 2026, Python 3.8+ compatible)
├── alpha_vantage 3.0.x        (Python 3.7+ compatible)
├── requests   2.32.x          (universal, no constraints)
│
├── pandas-ta  0.3.14b         (depends on pandas 2.x, NOT compatible with pandas 3.x yet)
├── scipy      1.14.x          (compatible with NumPy 2.2.x, Python 3.12)
│
├── dash       3.x             (Plotly ecosystem, avoid 4.0 until stabilized)
├── plotly     6.x             (bundled with Dash 3.x)
├── dash-bootstrap-components 1.6.x  (compatible with Dash 3.x)
│
├── pytest     8.4.x           (stable series)
├── pytest-cov 5.x
├── pytest-mock 3.14.x
├── hypothesis 6.x
├── freezegun  1.5.x
│
├── loguru     0.7.x           (no pandas/numpy dependency)
├── python-dotenv 1.0.x
├── ruff       0.9.x
├── mypy       1.13.x
└── pre-commit 3.8.x
```

### Critical Pinning Note

Create a `requirements.in` (editable list) and generate a locked `requirements.txt` via `pip-compile`. The most dangerous upgrade path for this project is:

1. `pandas 2.2.x` → `pandas 3.0.x` — breaking CoW semantics, string dtype
2. `dash 3.x` → `dash 4.x` — verify callback API compatibility
3. `NumPy 2.2.x` → `NumPy 2.4.x` — wait for pandas 2.2.x explicit support statement

---

## Architecture Notes (Stack Implications)

### Decimal Throughout

All price and quantity fields in Event dataclasses must be typed `decimal.Decimal`, not `float`. Enforce this with mypy `--strict`. At the data ingestion boundary (yfinance returns floats), convert immediately:

```python
from decimal import Decimal
price = Decimal(str(raw_float_price))  # correct
price = Decimal(raw_float_price)        # WRONG — inherits float imprecision
```

### Event Hierarchy (dataclasses)

```python
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from datetime import datetime

class EventType(Enum):
    MARKET  = auto()
    SIGNAL  = auto()
    ORDER   = auto()
    FILL    = auto()

@dataclass(frozen=True)
class Event:
    event_type: EventType
    timestamp: datetime        # always timezone-aware

@dataclass(frozen=True)
class MarketEvent(Event):
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
```

### Data Handler Temporal Discipline

The data handler must yield exactly one bar at a time and must never expose future bars to the strategy. Use a Python generator backed by SQLite `SELECT ... ORDER BY timestamp ASC` to enforce this. Test with freezegun to verify no lookahead.

### Forex Pip Precision

EUR/USD and GBP/USD prices are quoted to 5 decimal places (pipettes). Set `Decimal` context to at least precision 10 for Forex:

```python
from decimal import getcontext
getcontext().prec = 10
PIP = Decimal('0.0001')         # 1 pip for EUR/USD, GBP/USD
PIPETTE = Decimal('0.00001')    # 1 pipette (5th decimal)
```

---

## Sources

- [Event-Driven Backtesting with Python (QuantStart)](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/)
- [pandas 3.0.0 What's New (January 21, 2026)](https://pandas.pydata.org/docs/whatsnew/v3.0.0.html)
- [pandas 3.0 Copy-on-Write Migration Guide (Medium, Jan 2026)](https://medium.com/@kaushalsinh73/pandas-3-0-copy-on-write-migration-guide-the-surprising-performance-wins-and-the-silent-footguns-f6e76db73551)
- [NumPy 2.4.0 Release Notes](https://numpy.org/doc/stable/release.html)
- [yfinance on PyPI (1.0 release Jan 24, 2026)](https://pypi.org/project/yfinance/)
- [Pydantic v2.12.x Documentation](https://docs.pydantic.dev/latest/)
- [pytest 8.4.0 Release Announcement](https://docs.pytest.org/en/stable/announce/release-8.4.0.html)
- [SQLAlchemy 2.0.44 Released (Oct 2025)](https://www.sqlalchemy.org/blog/2025/10/10/sqlalchemy-2.0.44-released/)
- [Python decimal module documentation](https://docs.python.org/3/library/decimal.html)
- [Top Python Backtesting Libraries 2025 (QuantVPS)](https://www.quantvps.com/blog/best-python-backtesting-libraries-for-trading)
- [Loguru vs Standard Logging (Leapcell)](https://leapcell.io/blog/python-logging-vs-loguru)
- [Dash PyPI (latest version)](https://pypi.org/project/dash/)
