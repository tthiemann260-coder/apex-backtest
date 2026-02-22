"""
base.py — Abstract base class for all backtesting strategies.

Provides:
- Rolling buffer of historical bars (structurally prevents future access)
- Parameter injection via constructor kwargs
- Abstract calculate_signals() hook that concrete strategies must implement

The rolling buffer pattern ensures STRAT-08: strategies only see historical data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.events import MarketEvent, SignalEvent


class BaseStrategy(ABC):
    """Abstract strategy base class.

    Subclasses MUST implement ``calculate_signals(event)`` which receives
    the current MarketEvent and returns an Optional[SignalEvent].

    The rolling buffer (``self.bars``) holds the last ``max_buffer_size``
    bars. Call ``update_buffer(event)`` before ``calculate_signals()``
    in the main loop to keep the buffer current.
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str,
        max_buffer_size: int = 500,
        params: Optional[dict] = None,
    ) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._max_buffer_size = max_buffer_size
        self._params: dict = dict(params) if params else {}
        self._bar_buffer: list[MarketEvent] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def bars(self) -> list[MarketEvent]:
        """Return a copy of the rolling buffer (read-only)."""
        return list(self._bar_buffer)

    @property
    def params(self) -> dict:
        """Return a copy of strategy parameters (read-only)."""
        return dict(self._params)

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    def update_buffer(self, event: MarketEvent) -> None:
        """Append a bar to the rolling buffer, trimming oldest if needed."""
        self._bar_buffer.append(event)
        if len(self._bar_buffer) > self._max_buffer_size:
            self._bar_buffer = self._bar_buffer[-self._max_buffer_size:]

    # ------------------------------------------------------------------
    # Abstract hook
    # ------------------------------------------------------------------

    @abstractmethod
    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Evaluate the current bar and return a signal or None.

        Parameters
        ----------
        event : MarketEvent
            The current bar. The rolling buffer (self.bars) contains
            all historical bars up to and including this one.

        Returns
        -------
        Optional[SignalEvent]
            A LONG, SHORT, or EXIT signal, or None if no action.
        """
        ...
