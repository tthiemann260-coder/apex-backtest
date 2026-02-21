"""
event_queue.py — Central FIFO event queue for apex-backtest.

Wraps collections.deque to enforce strict FIFO ordering.
Accepts only valid Event instances (MarketEvent, SignalEvent, OrderEvent, FillEvent).
Thread-safety is NOT guaranteed — single-threaded backtest loop assumed.
"""

from __future__ import annotations

from collections import deque

from src.events import Event, MarketEvent, SignalEvent, OrderEvent, FillEvent


class EventQueue:
    """Central FIFO event queue wrapping collections.deque.

    Enforces type safety: only accepts MarketEvent, SignalEvent,
    OrderEvent, and FillEvent instances. Rejects all other types
    with a descriptive TypeError.
    """

    _VALID_TYPES: tuple[type, ...] = (
        MarketEvent,
        SignalEvent,
        OrderEvent,
        FillEvent,
    )

    def __init__(self) -> None:
        self._queue: deque[Event] = deque()

    def put(self, event: Event) -> None:
        """Enqueue an event. Raises TypeError if not a valid Event type."""
        if not isinstance(event, self._VALID_TYPES):
            raise TypeError(
                f"EventQueue only accepts Event types "
                f"({[t.__name__ for t in self._VALID_TYPES]}), "
                f"got {type(event).__name__!r}"
            )
        self._queue.append(event)

    def get(self) -> Event:
        """Dequeue the next event (FIFO). Raises IndexError if empty."""
        if not self._queue:
            raise IndexError(
                "EventQueue is empty — call is_empty() before get()"
            )
        return self._queue.popleft()

    def is_empty(self) -> bool:
        """Return True if the queue has no events."""
        return len(self._queue) == 0

    def size(self) -> int:
        """Return the number of events in the queue."""
        return len(self._queue)

    def clear(self) -> None:
        """Remove all events from the queue."""
        self._queue.clear()

    def __len__(self) -> int:
        """Return the number of events in the queue."""
        return len(self._queue)

    def __repr__(self) -> str:
        """Return a string representation including queue size."""
        return f"EventQueue(size={len(self._queue)})"
