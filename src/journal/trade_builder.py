"""
trade_builder.py — Observer that converts FillEvent pairs into TradeJournalEntry objects.

Attached to Portfolio via the trade_builder property. Portfolio calls:
- on_fill(fill, positions) after each FillEvent is processed
- on_bar(bar, positions)  after each equity update

The TradeBuilder detects open/close transitions by inspecting the positions dict
AFTER the fill was processed (quantity == 0 means position was closed).

Partial closes are NOT supported in v1 — a trade is only sealed when the
position quantity reaches exactly zero.

All financial math uses decimal.Decimal with string constructor.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from src.events import FillEvent, MarketEvent, OrderSide
from src.journal.models import TradeJournalEntry

if TYPE_CHECKING:
    from src.portfolio import Position


class TradeBuilder:
    """Observer that builds TradeJournalEntry objects from fill pairs.

    Parameters
    ----------
    strategy_name : str
        Name of the strategy (stored on each completed trade).
    timeframe : str
        Timeframe label (e.g. "15m", "1d").
    """

    def __init__(
        self,
        strategy_name: str = "",
        timeframe: str = "",
    ) -> None:
        self._strategy_name = strategy_name
        self._timeframe = timeframe
        self._open_trades: dict[str, dict] = {}  # symbol -> entry state
        self._completed: list[TradeJournalEntry] = []
        self._bar_count: int = 0
        self._price_highs: dict[str, Decimal] = {}  # symbol -> running high
        self._price_lows: dict[str, Decimal] = {}   # symbol -> running low

    # ------------------------------------------------------------------
    # Public API — called by Portfolio
    # ------------------------------------------------------------------

    def on_fill(self, fill: FillEvent, positions: dict[str, Position]) -> None:
        """Process a fill event — detect opening or closing of trades.

        Parameters
        ----------
        fill : FillEvent
            The fill that was just processed by Portfolio.
        positions : dict[str, Position]
            Current positions dict AFTER the fill was applied.
        """
        symbol = fill.symbol
        pos = positions.get(symbol)
        was_open = symbol in self._open_trades

        if was_open and (pos is None or pos.quantity == Decimal("0")):
            # Position was completely closed -> seal the trade
            self._close_trade(fill)
        elif was_open:
            # Position still open (partial close or add) -> ignore in v1
            pass
        else:
            # New position opened
            self._open_trade(fill)

    def on_bar(self, bar: MarketEvent, positions: dict[str, Position]) -> None:
        """Track MAE/MFE for open positions on each bar.

        Parameters
        ----------
        bar : MarketEvent
            The current bar.
        positions : dict[str, Position]
            Current positions dict.
        """
        self._bar_count += 1
        symbol = bar.symbol

        if symbol not in self._open_trades:
            return

        entry_data = self._open_trades[symbol]

        if entry_data["side"] == "LONG":
            # MFE = highest high (favorable for longs)
            self._price_highs[symbol] = max(
                self._price_highs.get(symbol, bar.high), bar.high
            )
            # MAE = lowest low (adverse for longs)
            self._price_lows[symbol] = min(
                self._price_lows.get(symbol, bar.low), bar.low
            )
        else:  # SHORT
            # MAE = highest high (adverse for shorts)
            self._price_highs[symbol] = max(
                self._price_highs.get(symbol, bar.high), bar.high
            )
            # MFE = lowest low (favorable for shorts)
            self._price_lows[symbol] = min(
                self._price_lows.get(symbol, bar.low), bar.low
            )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def completed_trades(self) -> list[TradeJournalEntry]:
        """Return a copy of all completed trades."""
        return list(self._completed)

    @property
    def open_trade_count(self) -> int:
        """Number of currently open trades."""
        return len(self._open_trades)

    @property
    def total_completed(self) -> int:
        """Total number of completed trades."""
        return len(self._completed)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _open_trade(self, fill: FillEvent) -> None:
        """Record a new trade opening."""
        symbol = fill.symbol
        # Convert OrderSide enum to "LONG"/"SHORT" string
        side_str = "LONG" if fill.side == OrderSide.BUY else "SHORT"

        self._open_trades[symbol] = {
            "entry_fill": fill,
            "side": side_str,
            "entry_bar_count": self._bar_count,
        }
        # Initialize MAE/MFE tracking at entry price
        self._price_highs[symbol] = fill.fill_price
        self._price_lows[symbol] = fill.fill_price

    def _close_trade(self, fill: FillEvent) -> None:
        """Seal a trade and create a TradeJournalEntry."""
        symbol = fill.symbol
        entry_data = self._open_trades.pop(symbol)
        entry_fill: FillEvent = entry_data["entry_fill"]
        side = entry_data["side"]
        entry_bar_count = entry_data["entry_bar_count"]

        entry_price = entry_fill.fill_price
        exit_price = fill.fill_price
        quantity = entry_fill.quantity

        # PnL calculation
        if side == "LONG":
            gross_pnl = (exit_price - entry_price) * quantity
        else:  # SHORT
            gross_pnl = (entry_price - exit_price) * quantity

        # Friction totals (entry + exit)
        commission_total = entry_fill.commission + fill.commission
        slippage_total = entry_fill.slippage + fill.slippage
        spread_cost_total = entry_fill.spread_cost + fill.spread_cost
        total_friction = commission_total + slippage_total + spread_cost_total

        net_pnl = gross_pnl - total_friction

        # Net PnL percentage (relative to position cost)
        position_cost = entry_price * quantity
        if position_cost > Decimal("0"):
            net_pnl_pct = net_pnl / position_cost
        else:
            net_pnl_pct = Decimal("0")

        # MAE/MFE from tracked price extremes
        price_high = self._price_highs.get(symbol, entry_price)
        price_low = self._price_lows.get(symbol, entry_price)

        if side == "LONG":
            mae = entry_price - price_low    # adverse = price went down
            mfe = price_high - entry_price   # favorable = price went up
        else:  # SHORT
            mae = price_high - entry_price   # adverse = price went up
            mfe = entry_price - price_low    # favorable = price went down

        # Duration in bars
        duration_bars = self._bar_count - entry_bar_count

        # Create the journal entry
        entry = TradeJournalEntry(
            trade_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            entry_time=entry_fill.timestamp,
            exit_time=fill.timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            commission_total=commission_total,
            slippage_total=slippage_total,
            spread_cost_total=spread_cost_total,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            net_pnl_pct=net_pnl_pct,
            mae=mae,
            mfe=mfe,
            duration_bars=duration_bars,
            timeframe=self._timeframe,
            strategy_name=self._strategy_name,
        )

        self._completed.append(entry)

        # Cleanup tracking dicts
        self._price_highs.pop(symbol, None)
        self._price_lows.pop(symbol, None)
