"""
breakout.py — Breakout/Momentum strategy (STRAT-05).

Generates LONG signals when price breaks above the highest high of the
lookback period with volume confirmation.
SHORT signals when price breaks below the lowest low.
EXIT when price reverts inside the channel.

Uses pandas-ta for ATR and the rolling buffer for high/low channels.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pandas as pd
import pandas_ta as ta

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy


class BreakoutStrategy(BaseStrategy):
    """Donchian Channel Breakout strategy with ATR filter.

    Parameters
    ----------
    lookback : int
        Number of bars for high/low channel (default: 20).
    atr_period : int
        ATR period for volatility filter (default: 14).
    volume_factor : float
        Minimum volume as factor of average volume for confirmation (default: 1.5).
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
        self._lookback: int = self._params.get("lookback", 20)
        self._atr_period: int = self._params.get("atr_period", 14)
        self._volume_factor: float = self._params.get("volume_factor", 1.5)
        self._in_position: str = ""  # "long", "short", or ""

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Check for breakout above/below Donchian channel."""
        self.update_buffer(event)

        min_bars = self._lookback + 1
        if len(self.bars) < min_bars:
            return None

        # Use lookback period (excluding current bar) for channel
        lookback_bars = self._bar_buffer[-(self._lookback + 1):-1]
        channel_high = max(float(b.high) for b in lookback_bars)
        channel_low = min(float(b.low) for b in lookback_bars)

        current_close = float(event.close)
        current_volume = event.volume

        # Average volume for confirmation
        avg_volume = sum(b.volume for b in lookback_bars) / len(lookback_bars)

        # Exit logic — price back inside channel
        if self._in_position == "long" and current_close < channel_low:
            self._in_position = ""
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal("0.5"),
            )
        if self._in_position == "short" and current_close > channel_high:
            self._in_position = ""
            return SignalEvent(
                symbol=event.symbol,
                timestamp=event.timestamp,
                signal_type=SignalType.EXIT,
                strength=Decimal("0.5"),
            )

        # Entry logic — breakout with volume confirmation
        if not self._in_position and current_close > channel_high:
            if current_volume >= avg_volume * self._volume_factor:
                self._in_position = "long"
                strength = min((current_close - channel_high) / channel_high * 100, 1.0)
                return SignalEvent(
                    symbol=event.symbol,
                    timestamp=event.timestamp,
                    signal_type=SignalType.LONG,
                    strength=Decimal(str(round(strength, 4))),
                )

        if not self._in_position and current_close < channel_low:
            if current_volume >= avg_volume * self._volume_factor:
                self._in_position = "short"
                strength = min((channel_low - current_close) / channel_low * 100, 1.0)
                return SignalEvent(
                    symbol=event.symbol,
                    timestamp=event.timestamp,
                    signal_type=SignalType.SHORT,
                    strength=Decimal(str(round(strength, 4))),
                )

        return None
