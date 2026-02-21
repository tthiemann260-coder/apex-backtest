---
phase: 1
plan: 02
title: Event Queue + Tests
wave: 2
depends_on: [01]
files_modified:
  - src/event_queue.py
  - tests/__init__.py
  - tests/test_events.py
  - tests/test_causality.py
autonomous: true
---

# Plan 02: Event Queue + Tests

## Goal
Implement the central FIFO EventQueue wrapper and write the full test suite for events and queue, plus the test_causality.py skeleton, so that `pytest tests/test_events.py` passes with zero warnings.

## must_haves
- EventQueue wraps `collections.deque` — 100 events enqueued and dequeued in identical (FIFO) order
- EventQueue rejects non-Event objects with `TypeError`
- `test_events.py` covers: frozen immutability, field types, enum membership, Decimal (no float), FIFO order
- `test_causality.py` exists and contains at least one passing placeholder test
- `pytest tests/test_events.py` exits 0 with zero warnings

## Tasks

<task id="1" file="src/event_queue.py">
Create src/event_queue.py implementing the central event queue for the EDA pipeline.

Module docstring:
```
"""
event_queue.py — Central FIFO event queue for apex-backtest.

Wraps collections.deque to enforce strict FIFO ordering.
Accepts only valid Event instances (MarketEvent, SignalEvent, OrderEvent, FillEvent).
Thread-safety is NOT guaranteed — single-threaded backtest loop assumed.
"""
```

Imports:
```python
from __future__ import annotations
from collections import deque
from typing import TYPE_CHECKING

from src.events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent
```

Implement `EventQueue` class:

```python
class EventQueue:
    """
    Strict FIFO event queue. Only accepts instances of the four Event subtypes.
    Uses collections.deque internally for O(1) append and popleft.
    """

    _VALID_TYPES = (MarketEvent, SignalEvent, OrderEvent, FillEvent)

    def __init__(self) -> None:
        self._queue: deque[Event] = deque()

    def put(self, event: Event) -> None:
        """
        Enqueue an event. Raises TypeError if event is not a valid Event subtype.
        """
        if not isinstance(event, self._VALID_TYPES):
            raise TypeError(
                f"EventQueue only accepts Event types "
                f"({[t.__name__ for t in self._VALID_TYPES]}), "
                f"got {type(event).__name__!r}"
            )
        self._queue.append(event)

    def get(self) -> Event:
        """
        Dequeue and return the oldest event (FIFO). Raises IndexError if empty.
        """
        if self._queue:
            return self._queue.popleft()
        raise IndexError("EventQueue is empty — call is_empty() before get()")

    def is_empty(self) -> bool:
        """Return True if the queue contains no events."""
        return len(self._queue) == 0

    def size(self) -> int:
        """Return the number of events currently in the queue."""
        return len(self._queue)

    def clear(self) -> None:
        """Remove all events from the queue."""
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)

    def __repr__(self) -> str:
        return f"EventQueue(size={len(self._queue)})"
```
</task>

<task id="2" file="tests/__init__.py">
Create tests/__init__.py as an empty file (zero bytes). This marks `tests` as a Python package so pytest can discover and import test modules correctly without path manipulation.
</task>

<task id="3" file="tests/test_events.py">
Create tests/test_events.py with the full event test suite. Every test must pass with zero warnings under `pytest -v --tb=short`.

Module docstring:
```
"""
test_events.py — Tests for apex-backtest event types.

Covers: frozen immutability, field types, enum values, Decimal correctness,
EventQueue FIFO ordering, EventQueue type validation.

Run: pytest tests/test_events.py -v
"""
```

Imports:
```python
import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

from src.events import (
    MarketEvent, SignalEvent, OrderEvent, FillEvent,
    SignalType, OrderType, OrderSide, Event,
)
from src.event_queue import EventQueue
```

--- Fixtures ---

```python
@pytest.fixture
def now() -> datetime:
    return datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)

@pytest.fixture
def market_event(now: datetime) -> MarketEvent:
    return MarketEvent(
        symbol="AAPL",
        timestamp=now,
        open=Decimal("180.00"),
        high=Decimal("182.50"),
        low=Decimal("179.25"),
        close=Decimal("181.75"),
        volume=1_500_000,
        timeframe="1d",
    )

@pytest.fixture
def signal_event(now: datetime) -> SignalEvent:
    return SignalEvent(
        symbol="AAPL",
        timestamp=now,
        signal_type=SignalType.LONG,
        strength=Decimal("0.80"),
    )

@pytest.fixture
def order_event(now: datetime) -> OrderEvent:
    return OrderEvent(
        symbol="AAPL",
        timestamp=now,
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        price=None,
    )

@pytest.fixture
def fill_event(now: datetime) -> FillEvent:
    return FillEvent(
        symbol="AAPL",
        timestamp=now,
        side=OrderSide.BUY,
        quantity=Decimal("100"),
        fill_price=Decimal("181.80"),
        commission=Decimal("1.00"),
        slippage=Decimal("0.05"),
        spread_cost=Decimal("0.03"),
    )
```

--- Immutability tests (one per event type) ---

```python
class TestFrozenImmutability:
    def test_market_event_is_frozen(self, market_event: MarketEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            market_event.close = Decimal("999.99")  # type: ignore[misc]

    def test_signal_event_is_frozen(self, signal_event: SignalEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            signal_event.strength = Decimal("0.01")  # type: ignore[misc]

    def test_order_event_is_frozen(self, order_event: OrderEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            order_event.quantity = Decimal("999")  # type: ignore[misc]

    def test_fill_event_is_frozen(self, fill_event: FillEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            fill_event.fill_price = Decimal("0.01")  # type: ignore[misc]
```

--- Field type tests ---

```python
class TestFieldTypes:
    def test_market_event_decimal_fields(self, market_event: MarketEvent) -> None:
        for field_name in ("open", "high", "low", "close"):
            value = getattr(market_event, field_name)
            assert isinstance(value, Decimal), (
                f"MarketEvent.{field_name} must be Decimal, got {type(value).__name__}"
            )

    def test_market_event_volume_is_int(self, market_event: MarketEvent) -> None:
        assert isinstance(market_event.volume, int)
        assert not isinstance(market_event.volume, bool)

    def test_market_event_symbol_and_timeframe_are_str(self, market_event: MarketEvent) -> None:
        assert isinstance(market_event.symbol, str)
        assert isinstance(market_event.timeframe, str)

    def test_signal_event_strength_is_decimal(self, signal_event: SignalEvent) -> None:
        assert isinstance(signal_event.strength, Decimal)

    def test_order_event_quantity_is_decimal(self, order_event: OrderEvent) -> None:
        assert isinstance(order_event.quantity, Decimal)

    def test_order_event_price_none_for_market(self, order_event: OrderEvent) -> None:
        assert order_event.price is None

    def test_order_event_price_decimal_for_limit(self, now: datetime) -> None:
        limit_order = OrderEvent(
            symbol="TSLA",
            timestamp=now,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal("50"),
            price=Decimal("200.00"),
        )
        assert isinstance(limit_order.price, Decimal)

    def test_fill_event_financial_fields_are_decimal(self, fill_event: FillEvent) -> None:
        for field_name in ("quantity", "fill_price", "commission", "slippage", "spread_cost"):
            value = getattr(fill_event, field_name)
            assert isinstance(value, Decimal), (
                f"FillEvent.{field_name} must be Decimal, got {type(value).__name__}"
            )
```

--- Enum tests ---

```python
class TestEnums:
    def test_signal_type_members(self) -> None:
        assert SignalType.LONG.value == "LONG"
        assert SignalType.SHORT.value == "SHORT"
        assert SignalType.EXIT.value == "EXIT"
        assert len(SignalType) == 3

    def test_order_type_members(self) -> None:
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP.value == "STOP"
        assert len(OrderType) == 3

    def test_order_side_members(self) -> None:
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"
        assert len(OrderSide) == 2

    def test_signal_event_signal_type_is_enum(self, signal_event: SignalEvent) -> None:
        assert isinstance(signal_event.signal_type, SignalType)

    def test_order_event_enums_are_correct_types(self, order_event: OrderEvent) -> None:
        assert isinstance(order_event.order_type, OrderType)
        assert isinstance(order_event.side, OrderSide)
```

--- Decimal precision tests ---

```python
class TestDecimalPrecision:
    def test_decimal_string_constructor_preserves_precision(self) -> None:
        # Decimal from string is exact; Decimal from float is not
        d = Decimal("0.10")
        assert str(d) == "0.10"

    def test_decimal_float_constructor_is_imprecise(self) -> None:
        # This documents WHY we forbid float — informational, always passes
        d_float = Decimal(0.1)
        d_str = Decimal("0.1")
        assert d_float != d_str, (
            "Decimal(0.1) != Decimal('0.1') — always use string constructor"
        )

    def test_market_event_close_exact_value(self, market_event: MarketEvent) -> None:
        assert market_event.close == Decimal("181.75")

    def test_fill_event_commission_exact_value(self, fill_event: FillEvent) -> None:
        assert fill_event.commission == Decimal("1.00")
```

--- EventQueue tests ---

```python
class TestEventQueue:
    def test_empty_on_init(self) -> None:
        q = EventQueue()
        assert q.is_empty()
        assert q.size() == 0
        assert len(q) == 0

    def test_put_and_get_single_event(self, market_event: MarketEvent) -> None:
        q = EventQueue()
        q.put(market_event)
        assert not q.is_empty()
        assert q.size() == 1
        result = q.get()
        assert result is market_event
        assert q.is_empty()

    def test_fifo_ordering_100_events(self, now: datetime) -> None:
        """100 MarketEvents enqueued — must dequeue in identical order."""
        q = EventQueue()
        events = [
            MarketEvent(
                symbol=f"SYM{i:04d}",
                timestamp=now,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=i,
                timeframe="1d",
            )
            for i in range(100)
        ]
        for e in events:
            q.put(e)

        assert q.size() == 100

        dequeued = [q.get() for _ in range(100)]
        assert dequeued == events, "FIFO ordering violated"
        assert q.is_empty()

    def test_mixed_event_types_fifo(
        self,
        market_event: MarketEvent,
        signal_event: SignalEvent,
        order_event: OrderEvent,
        fill_event: FillEvent,
    ) -> None:
        q = EventQueue()
        sequence = [market_event, signal_event, order_event, fill_event]
        for e in sequence:
            q.put(e)
        assert [q.get() for _ in range(4)] == sequence

    def test_get_raises_on_empty_queue(self) -> None:
        q = EventQueue()
        with pytest.raises(IndexError):
            q.get()

    def test_put_rejects_non_event(self) -> None:
        q = EventQueue()
        with pytest.raises(TypeError, match="EventQueue only accepts Event types"):
            q.put("not an event")  # type: ignore[arg-type]

    def test_put_rejects_int(self) -> None:
        q = EventQueue()
        with pytest.raises(TypeError):
            q.put(42)  # type: ignore[arg-type]

    def test_put_rejects_none(self) -> None:
        q = EventQueue()
        with pytest.raises(TypeError):
            q.put(None)  # type: ignore[arg-type]

    def test_clear_empties_queue(self, market_event: MarketEvent) -> None:
        q = EventQueue()
        q.put(market_event)
        q.put(market_event)
        q.clear()
        assert q.is_empty()
        assert q.size() == 0

    def test_repr(self) -> None:
        q = EventQueue()
        assert "EventQueue" in repr(q)
        assert "size=0" in repr(q)
```
</task>

<task id="4" file="tests/test_causality.py">
Create tests/test_causality.py as a skeleton for future Phase 6 causality/temporal integrity tests.

Module docstring:
```
"""
test_causality.py — Causality and temporal integrity tests for apex-backtest.

PHASE 1 STATUS: Skeleton only. One placeholder test passes to ensure
the module is importable and pytest-discoverable.

FULL CAUSALITY TESTS (Phase 6 — Reporting & Validation) will cover:
  - No SignalEvent timestamp precedes its generating MarketEvent timestamp
  - No OrderEvent timestamp precedes its generating SignalEvent timestamp
  - No FillEvent timestamp precedes its generating OrderEvent timestamp
  - EventQueue never produces events out of chronological order when
    events are enqueued in timestamp order
  - Replay of historical events maintains strict monotonic timestamp ordering
  - No look-ahead bias: strategy cannot access close[t] before bar[t] closes
  - Trade log entries are sorted by fill timestamp ascending

These tests will use the full backtest loop introduced in Phase 3 (Backtester Core)
and the portfolio/trade log introduced in Phase 4 (Portfolio & Risk).
"""
```

Imports:
```python
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.events import MarketEvent, SignalEvent, OrderEvent, FillEvent, OrderSide, SignalType, OrderType
from src.event_queue import EventQueue
```

Placeholder test class:
```python
class TestCausalityInfrastructure:
    """
    Phase 1 placeholder — verifies that causality test infrastructure is in place.
    Full temporal ordering assertions are added in Phase 6.
    """

    def test_placeholder_causality_module_importable(self) -> None:
        """
        Placeholder: confirms this module loads without errors.
        Causality enforcement tests are scheduled for Phase 6.
        """
        # Infrastructure check: all event types needed for causality tests are importable
        assert MarketEvent is not None
        assert SignalEvent is not None
        assert OrderEvent is not None
        assert FillEvent is not None
        assert EventQueue is not None

    def test_basic_timestamp_ordering_precondition(self) -> None:
        """
        Smoke test: a MarketEvent timestamp can be compared to a SignalEvent timestamp.
        This is a prerequisite for all causality checks in Phase 6.
        """
        t0 = datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(seconds=1)

        market = MarketEvent(
            symbol="AAPL",
            timestamp=t0,
            open=Decimal("180"),
            high=Decimal("182"),
            low=Decimal("179"),
            close=Decimal("181"),
            volume=100_000,
            timeframe="1d",
        )
        signal = SignalEvent(
            symbol="AAPL",
            timestamp=t1,
            signal_type=SignalType.LONG,
            strength=Decimal("0.9"),
        )

        # Causality invariant: signal must not precede the market bar that generated it
        assert signal.timestamp >= market.timestamp, (
            "CAUSALITY VIOLATION: signal precedes market bar"
        )
```
</task>

## Verification
- [ ] `pytest tests/test_events.py -v` exits with code 0, all tests pass, zero warnings
- [ ] `pytest tests/test_causality.py -v` exits with code 0, placeholder tests pass
- [ ] `pytest tests/ -v` runs both files with zero failures and zero errors
- [ ] FIFO test: enqueue 100 events, dequeue all — order matches exactly
- [ ] Immutability: assigning to any field on any frozen event raises `FrozenInstanceError`
- [ ] Type rejection: `EventQueue().put("string")` raises `TypeError`
- [ ] `pytest tests/ --tb=short -q` shows `passed` with no warnings in output
