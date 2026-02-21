---
phase: 1
plan: 01
title: Project Setup + Event Types
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - src/__init__.py
  - src/events.py
autonomous: true
---

# Plan 01: Project Setup + Event Types

## Goal
Bootstrap the apex-backtest project with pyproject.toml and implement all four immutable event dataclasses (MarketEvent, SignalEvent, OrderEvent, FillEvent) plus supporting enums.

## must_haves
- All four event dataclasses carry `frozen=True` — mutating any field raises `FrozenInstanceError`
- All financial fields (open, high, low, close, fill_price, commission, slippage, spread_cost, strength, quantity, price) are typed as `decimal.Decimal` — no float anywhere
- `SignalType`, `OrderType`, `OrderSide` enums are defined with correct members
- `pytest tests/test_events.py` is importable (no import errors from events.py)

## Tasks

<task id="1" file="pyproject.toml">
Create pyproject.toml at the project root (apex-backtest/) with the following content:

- Build system: setuptools
- Project name: apex-backtest
- Version: 0.1.0
- Requires Python >=3.12
- Dependencies (pinned or minimum versions):
    pandas==2.2.3
    numpy>=1.26
    yfinance>=0.2
    alpha_vantage>=2.3
    pandas-ta>=0.3
    dash>=2.17
    plotly>=5.22
    pyarrow>=15.0
    pytest>=8.0
    pytest-cov>=5.0

- [tool.pytest.ini_options]:
    testpaths = ["tests"]
    addopts = "-v --tb=short"

- [tool.coverage.run]:
    source = ["src"]

Example structure:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "apex-backtest"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandas==2.2.3",
    "numpy>=1.26",
    "yfinance>=0.2",
    "alpha_vantage>=2.3",
    "pandas-ta>=0.3",
    "dash>=2.17",
    "plotly>=5.22",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.coverage.run]
source = ["src"]
```
</task>

<task id="2" file="src/__init__.py">
Create src/__init__.py as an empty file (zero bytes). This marks `src` as a Python package so that `from src.events import MarketEvent` works correctly in tests.
</task>

<task id="3" file="src/events.py">
Create src/events.py with all event types for the EDA pipeline. Follow these rules with NO exceptions:

RULE 1: decimal.Decimal for ALL financial fields — use string constructor in examples/defaults.
RULE 2: frozen=True on every @dataclass.
RULE 3: No float type annotations anywhere.

File structure (in order):

--- Imports ---
```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
```

--- Enums ---

```python
class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"

class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"

class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"
```

--- Event dataclasses (ALL frozen=True) ---

MarketEvent — represents one OHLCV bar:
```python
@dataclass(frozen=True)
class MarketEvent:
    symbol: str          # e.g. "AAPL"
    timestamp: datetime  # bar close time (timezone-aware recommended)
    open: Decimal        # opening price — Decimal('123.45')
    high: Decimal        # session high
    low: Decimal         # session low
    close: Decimal       # closing price
    volume: int          # share/contract volume (integer, not Decimal)
    timeframe: str       # e.g. "1d", "1h", "5m"
```

SignalEvent — strategy output, NOT yet an order:
```python
@dataclass(frozen=True)
class SignalEvent:
    symbol: str
    timestamp: datetime
    signal_type: SignalType   # LONG / SHORT / EXIT
    strength: Decimal         # 0.0–1.0 conviction; Decimal('0.75')
```

OrderEvent — risk manager output, actionable instruction:
```python
@dataclass(frozen=True)
class OrderEvent:
    symbol: str
    timestamp: datetime
    order_type: OrderType        # MARKET / LIMIT / STOP
    side: OrderSide              # BUY / SELL
    quantity: Decimal            # number of units; Decimal('100')
    price: Optional[Decimal]     # None for MARKET orders; limit/stop price otherwise
```

FillEvent — broker/execution handler output, confirms a trade:
```python
@dataclass(frozen=True)
class FillEvent:
    symbol: str
    timestamp: datetime
    side: OrderSide
    quantity: Decimal     # units actually filled
    fill_price: Decimal   # actual execution price
    commission: Decimal   # broker commission cost; Decimal('0.00')
    slippage: Decimal     # slippage cost (positive = adverse); Decimal('0.00')
    spread_cost: Decimal  # half-spread cost; Decimal('0.00')
```

--- Module-level type alias ---
After all dataclasses, add:
```python
# Union type for type hints throughout the system
Event = MarketEvent | SignalEvent | OrderEvent | FillEvent
```

Add a module docstring at the top:
```
"""
events.py — Immutable event types for the apex-backtest EDA pipeline.

All dataclasses are frozen (immutable after construction).
All financial fields use decimal.Decimal with string constructor:
    Decimal('123.45')  # correct
    Decimal(123.45)    # FORBIDDEN — floating-point imprecision
"""
```
</task>

## Verification
- [ ] `python -c "from src.events import MarketEvent, SignalEvent, OrderEvent, FillEvent, SignalType, OrderType, OrderSide, Event; print('OK')"` prints `OK` with no errors
- [ ] `python -c "from src.events import MarketEvent; from datetime import datetime; from decimal import Decimal; e = MarketEvent('AAPL', datetime.now(), Decimal('100'), Decimal('101'), Decimal('99'), Decimal('100.5'), 1000, '1d'); e.close = Decimal('999')"` raises `FrozenInstanceError`
- [ ] `grep -n 'float' src/events.py` returns no matches (no float type annotations)
- [ ] `python -m pytest --collect-only` shows no import errors from src/events.py
