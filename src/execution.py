"""
execution.py — Realistic order execution simulation for apex-backtest.

ExecutionHandler processes OrderEvents and produces FillEvents with:
- Market orders: fill at NEXT bar's open (EXEC-01)
- Limit orders: fill if intra-bar price reaches limit (EXEC-02)
- Stop orders: fill at next open if gapped through, else at stop price (EXEC-03/06)
- Slippage model: percentage-based (EXEC-06)
- Spread model: bid/ask simulation (EXEC-05)
- Commission model: flat per-trade + per-share (EXEC-04)

All arithmetic uses decimal.Decimal exclusively (EXEC-07).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.events import FillEvent, MarketEvent, OrderEvent, OrderSide, OrderType


class ExecutionHandler:
    """Simulates realistic order execution with market frictions.

    Parameters
    ----------
    slippage_pct : Decimal
        Slippage as a percentage of fill price (default: 0.01% = 1 bps).
    commission_per_trade : Decimal
        Flat commission per trade (default: 1.00).
    commission_per_share : Decimal
        Commission per share/unit (default: 0.005).
    spread_pct : Decimal
        Bid/Ask spread as percentage of price (default: 0.02%).
    """

    def __init__(
        self,
        slippage_pct: Decimal = Decimal("0.0001"),
        commission_per_trade: Decimal = Decimal("1.00"),
        commission_per_share: Decimal = Decimal("0.005"),
        spread_pct: Decimal = Decimal("0.0002"),
    ) -> None:
        self._slippage_pct = slippage_pct
        self._commission_per_trade = commission_per_trade
        self._commission_per_share = commission_per_share
        self._spread_pct = spread_pct
        self._pending_orders: list[OrderEvent] = []

    @property
    def pending_orders(self) -> list[OrderEvent]:
        """Return a copy of pending orders."""
        return list(self._pending_orders)

    def submit_order(self, order: OrderEvent) -> None:
        """Submit an order for execution on the next bar."""
        self._pending_orders.append(order)

    def _calculate_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """Calculate slippage cost (always adverse to trader)."""
        slip = price * self._slippage_pct
        if side == OrderSide.BUY:
            return slip   # Buy: price moves up
        return -slip      # Sell: price moves down (net effect same)

    def _calculate_spread_cost(self, price: Decimal, side: OrderSide) -> Decimal:
        """Calculate half-spread cost (trader pays half the spread)."""
        return price * self._spread_pct / Decimal("2")

    def _calculate_commission(self, quantity: Decimal) -> Decimal:
        """Calculate total commission: flat + per-share."""
        return self._commission_per_trade + (self._commission_per_share * abs(quantity))

    def _apply_fill_price(
        self, base_price: Decimal, side: OrderSide,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Apply slippage and spread to base price.

        Returns (fill_price, slippage_amount, spread_cost).
        """
        slippage = self._calculate_slippage(base_price, side)
        spread_cost = self._calculate_spread_cost(base_price, side)

        if side == OrderSide.BUY:
            fill_price = base_price + slippage + spread_cost
        else:
            fill_price = base_price - abs(slippage) - spread_cost

        return fill_price, abs(slippage), spread_cost

    def process_bar(self, bar: MarketEvent) -> list[FillEvent]:
        """Process all pending orders against the current bar.

        Market orders fill at bar's open (EXEC-01).
        Limit orders fill if intra-bar range reaches the limit (EXEC-02).
        Stop orders fill at bar's open if gapped through (EXEC-06),
        or at stop price if touched intra-bar (EXEC-03).

        Parameters
        ----------
        bar : MarketEvent
            The current bar (this is the NEXT bar after signal generation).

        Returns
        -------
        list[FillEvent]
            Fill events for all orders that were executed this bar.
        """
        fills: list[FillEvent] = []
        remaining: list[OrderEvent] = []

        for order in self._pending_orders:
            fill = self._try_fill(order, bar)
            if fill is not None:
                fills.append(fill)
            else:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    def _try_fill(self, order: OrderEvent, bar: MarketEvent) -> Optional[FillEvent]:
        """Attempt to fill a single order against the current bar."""
        if order.order_type == OrderType.MARKET:
            return self._fill_market(order, bar)
        elif order.order_type == OrderType.LIMIT:
            return self._fill_limit(order, bar)
        elif order.order_type == OrderType.STOP:
            return self._fill_stop(order, bar)
        return None

    def _fill_market(self, order: OrderEvent, bar: MarketEvent) -> FillEvent:
        """Market order: fill at this bar's open (EXEC-01)."""
        fill_price, slippage, spread_cost = self._apply_fill_price(
            bar.open, order.side,
        )
        commission = self._calculate_commission(order.quantity)

        return FillEvent(
            symbol=order.symbol,
            timestamp=bar.timestamp,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage,
            spread_cost=spread_cost,
        )

    def _fill_limit(
        self, order: OrderEvent, bar: MarketEvent,
    ) -> Optional[FillEvent]:
        """Limit order: fill if intra-bar range reaches limit price (EXEC-02).

        BUY limit: fills if bar's low <= limit price (price dips to limit).
        SELL limit: fills if bar's high >= limit price (price rises to limit).
        """
        if order.price is None:
            return None

        filled = False
        if order.side == OrderSide.BUY and bar.low <= order.price:
            filled = True
        elif order.side == OrderSide.SELL and bar.high >= order.price:
            filled = True

        if not filled:
            return None

        # Fill at the limit price (not at open)
        fill_price, slippage, spread_cost = self._apply_fill_price(
            order.price, order.side,
        )
        commission = self._calculate_commission(order.quantity)

        return FillEvent(
            symbol=order.symbol,
            timestamp=bar.timestamp,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage,
            spread_cost=spread_cost,
        )

    def _fill_stop(
        self, order: OrderEvent, bar: MarketEvent,
    ) -> Optional[FillEvent]:
        """Stop order: gap-through fills at open, else at stop price (EXEC-03/06).

        BUY stop: triggers if bar's high >= stop price.
        SELL stop (stop-loss): triggers if bar's low <= stop price.
        Gap-through: if open already past stop, fill at open (not stop price).
        """
        if order.price is None:
            return None

        base_price: Optional[Decimal] = None

        if order.side == OrderSide.SELL:
            # Stop-loss for long position
            if bar.open <= order.price:
                # Gap-through: open is already below stop
                base_price = bar.open  # EXEC-06: fill at open, not stop
            elif bar.low <= order.price:
                # Intra-bar touch: fill at stop price
                base_price = order.price
        elif order.side == OrderSide.BUY:
            # Buy stop (breakout entry)
            if bar.open >= order.price:
                # Gap-through: open is already above stop
                base_price = bar.open
            elif bar.high >= order.price:
                # Intra-bar touch: fill at stop price
                base_price = order.price

        if base_price is None:
            return None

        fill_price, slippage, spread_cost = self._apply_fill_price(
            base_price, order.side,
        )
        commission = self._calculate_commission(order.quantity)

        return FillEvent(
            symbol=order.symbol,
            timestamp=bar.timestamp,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            slippage=slippage,
            spread_cost=spread_cost,
        )
