"""
fvg.py — Fair Value Gap strategy (STRAT-06).

ICT-style 3-candle pattern detection:
- Bullish FVG: candle[i-2].high < candle[i].low (gap between bar 1's high and bar 3's low)
- Bearish FVG: candle[i-2].low > candle[i].high (gap between bar 1's low and bar 3's high)

Generates LONG when price returns into a bullish FVG zone.
Generates SHORT when price returns into a bearish FVG zone.
EXIT when price moves through the FVG zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent, SignalEvent, SignalType
from src.strategy.base import BaseStrategy


@dataclass
class FVGZone:
    """Represents a Fair Value Gap zone."""
    direction: str  # "bullish" or "bearish"
    top: Decimal    # Upper boundary of the gap
    bottom: Decimal # Lower boundary of the gap
    bar_index: int  # Buffer index when detected


class FVGStrategy(BaseStrategy):
    """Fair Value Gap (ICT 3-Candle Pattern) strategy.

    Parameters
    ----------
    max_open_gaps : int
        Maximum number of tracked open FVG zones (default: 5).
    min_gap_size_pct : float
        Minimum gap size as percentage of price to qualify (default: 0.1).
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
        self._max_open_gaps: int = self._params.get("max_open_gaps", 5)
        self._min_gap_size_pct: float = self._params.get("min_gap_size_pct", 0.1)
        self._open_gaps: list[FVGZone] = []
        self._in_position: str = ""
        self._bar_count: int = 0

    def _detect_fvg(self) -> Optional[FVGZone]:
        """Check last 3 bars for a Fair Value Gap pattern."""
        if len(self._bar_buffer) < 3:
            return None

        bar1 = self._bar_buffer[-3]  # Oldest of the 3
        bar3 = self._bar_buffer[-1]  # Current / newest

        # Bullish FVG: bar1.high < bar3.low (gap up)
        if bar1.high < bar3.low:
            gap_size = bar3.low - bar1.high
            mid_price = (bar3.low + bar1.high) / 2
            if mid_price > 0 and float(gap_size / mid_price) * 100 >= self._min_gap_size_pct:
                return FVGZone(
                    direction="bullish",
                    top=bar3.low,
                    bottom=bar1.high,
                    bar_index=self._bar_count,
                )

        # Bearish FVG: bar1.low > bar3.high (gap down)
        if bar1.low > bar3.high:
            gap_size = bar1.low - bar3.high
            mid_price = (bar1.low + bar3.high) / 2
            if mid_price > 0 and float(gap_size / mid_price) * 100 >= self._min_gap_size_pct:
                return FVGZone(
                    direction="bearish",
                    top=bar1.low,
                    bottom=bar3.high,
                    bar_index=self._bar_count,
                )

        return None

    def _check_gap_fill(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Check if current bar enters any open FVG zone."""
        filled_gaps: list[int] = []

        for i, gap in enumerate(self._open_gaps):
            # Bullish FVG: LONG when price dips into gap zone
            if gap.direction == "bullish":
                if event.low <= gap.top and event.close >= gap.bottom:
                    if not self._in_position:
                        self._in_position = "long"
                        filled_gaps.append(i)
                        return SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type=SignalType.LONG,
                            strength=Decimal("0.7"),
                        )

            # Bearish FVG: SHORT when price rises into gap zone
            if gap.direction == "bearish":
                if event.high >= gap.bottom and event.close <= gap.top:
                    if not self._in_position:
                        self._in_position = "short"
                        filled_gaps.append(i)
                        return SignalEvent(
                            symbol=event.symbol,
                            timestamp=event.timestamp,
                            signal_type=SignalType.SHORT,
                            strength=Decimal("0.7"),
                        )

        # Remove filled gaps
        for i in sorted(filled_gaps, reverse=True):
            self._open_gaps.pop(i)

        return None

    def calculate_signals(self, event: MarketEvent) -> Optional[SignalEvent]:
        """Detect FVG zones and generate signals on gap fill."""
        self.update_buffer(event)
        self._bar_count += 1

        # Exit logic: if in position and price moves significantly
        if self._in_position == "long":
            if len(self._bar_buffer) >= 2:
                prev = self._bar_buffer[-2]
                if event.close < prev.low:
                    self._in_position = ""
                    return SignalEvent(
                        symbol=event.symbol,
                        timestamp=event.timestamp,
                        signal_type=SignalType.EXIT,
                        strength=Decimal("0.5"),
                    )

        if self._in_position == "short":
            if len(self._bar_buffer) >= 2:
                prev = self._bar_buffer[-2]
                if event.close > prev.high:
                    self._in_position = ""
                    return SignalEvent(
                        symbol=event.symbol,
                        timestamp=event.timestamp,
                        signal_type=SignalType.EXIT,
                        strength=Decimal("0.5"),
                    )

        # Detect new FVG zones
        new_gap = self._detect_fvg()
        if new_gap is not None:
            self._open_gaps.append(new_gap)
            # Trim to max tracked gaps (remove oldest)
            if len(self._open_gaps) > self._max_open_gaps:
                self._open_gaps = self._open_gaps[-self._max_open_gaps:]

        # Check if current bar fills any open gap
        signal = self._check_gap_fill(event)
        if signal is not None:
            return signal

        return None
