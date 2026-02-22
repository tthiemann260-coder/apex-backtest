"""
reversal.py — Mean Reversion strategy (STRAT-04).

Generates LONG signals when price is oversold (RSI < threshold)
and SHORT signals when overbought (RSI > 100 - threshold).
EXIT when RSI returns to neutral zone.

Uses pandas-ta for RSI and SMA indicators on the rolling buffer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd
import pandas_ta as ta

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy


class ReversalStrategy(BaseStrategy):
    """Mean Reversion strategy using RSI and SMA.

    Parameters
    ----------
    sma_period : int
        Simple Moving Average period for trend filter (default: 20).
    rsi_period : int
        RSI calculation period (default: 14).
    rsi_oversold : int
        RSI level below which a LONG signal is generated (default: 30).
    rsi_overbought : int
        RSI level above which a SHORT signal is generated (default: 70).
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1d",
        max_buffer_size: int = 500,
        params: Optional[dict] = None,
    ) -> None:
        super().__init__(
            symbol=symbol,
            timeframe=timeframe,
            max_buffer_size=max_buffer_size,
            params=params,
        )
        self._sma_period: int = self._params.get("sma_period", 20)
        self._rsi_period: int = self._params.get("rsi_period", 14)
        self._rsi_oversold: int = self._params.get("rsi_oversold", 30)
        self._rsi_overbought: int = self._params.get("rsi_overbought", 70)
        self._in_position: str = ""  # "long", "short", or ""

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Evaluate RSI for mean-reversion entry/exit."""
        self.update_buffer(event)

        # Need enough bars for RSI computation
        min_bars = max(self._sma_period, self._rsi_period) + 1
        if len(self.bars) < min_bars:
            return None

        # Build pandas Series from rolling buffer closes
        closes = pd.Series(
            [float(bar.close) for bar in self._bar_buffer],
            dtype=float,
        )

        # Compute indicators on rolling buffer
        rsi = ta.rsi(closes, length=self._rsi_period)
        if rsi is None or rsi.empty or pd.isna(rsi.iloc[-1]):
            return None

        current_rsi = rsi.iloc[-1]

        # Exit logic
        if self._in_position == "long" and current_rsi > 50:
            self._in_position = ""
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal(str(round(current_rsi / 100, 4))),
            )
        if self._in_position == "short" and current_rsi < 50:
            self._in_position = ""
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal(str(round(current_rsi / 100, 4))),
            )

        # Entry logic
        if not self._in_position and current_rsi < self._rsi_oversold:
            self._in_position = "long"
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.LONG,
                strength=Decimal(str(round((self._rsi_oversold - current_rsi) / self._rsi_oversold, 4))),
            )
        if not self._in_position and current_rsi > self._rsi_overbought:
            self._in_position = "short"
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.SHORT,
                strength=Decimal(str(round((current_rsi - self._rsi_overbought) / (100 - self._rsi_overbought), 4))),
            )

        return None
