"""Tests for ExecutionHandler — order execution, slippage, commission, spread."""

from __future__ import annotations

import pytest
from datetime import datetime
from decimal import Decimal

from src.events import (
    FillEvent, MarketEvent, OrderEvent, OrderSide, OrderType,
)
from src.execution import ExecutionHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(
    open_: str = "100.00",
    high: str = "102.00",
    low: str = "98.00",
    close: str = "101.00",
    volume: int = 1000,
    day: int = 16,
) -> MarketEvent:
    return MarketEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        timeframe="1d",
    )


def _make_order(
    side: OrderSide = OrderSide.BUY,
    order_type: OrderType = OrderType.MARKET,
    quantity: str = "100",
    price: str | None = None,
    day: int = 15,
) -> OrderEvent:
    return OrderEvent(
        symbol="TEST",
        timestamp=datetime(2024, 1, day, 10, 0),
        order_type=order_type,
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price) if price else None,
    )


# ===========================================================================
# TestMarketOrderExecution
# ===========================================================================

class TestMarketOrderExecution:
    """EXEC-01: Market orders fill at next bar's open."""

    def test_market_buy_fills_at_open(self):
        """Market BUY fills at the bar's open price (plus friction)."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(side=OrderSide.BUY, day=15)
        bar = _make_bar(open_="100.00", day=16)

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("100.00")

    def test_market_sell_fills_at_open(self):
        """Market SELL fills at the bar's open price (minus friction)."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(side=OrderSide.SELL, day=15)
        bar = _make_bar(open_="100.00", day=16)

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("100.00")

    def test_fill_timestamp_is_bar_timestamp(self):
        """Fill timestamp equals the fill bar's timestamp (TEST-03)."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(day=15)
        bar = _make_bar(day=16)

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        # Fill timestamp must be bar's timestamp, NOT order's timestamp
        assert fills[0].timestamp == bar.timestamp
        assert fills[0].timestamp != order.timestamp

    def test_fill_returns_fill_event(self):
        """Fill produces a FillEvent with correct type."""
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0], FillEvent)

    def test_fill_has_correct_symbol(self):
        """FillEvent carries the correct symbol."""
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].symbol == "TEST"

    def test_fill_has_correct_quantity(self):
        """FillEvent carries the correct quantity."""
        handler = ExecutionHandler()
        order = _make_order(quantity="50")
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].quantity == Decimal("50")


# ===========================================================================
# TestLimitOrderExecution
# ===========================================================================

class TestLimitOrderExecution:
    """EXEC-02: Limit orders check intra-bar H/L range."""

    def test_limit_buy_fills_when_price_dips(self):
        """BUY limit fills when bar's low <= limit price."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price="99.00",
        )
        bar = _make_bar(low="98.00")  # Low reaches below limit

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("99.00")

    def test_limit_buy_not_filled_when_price_above(self):
        """BUY limit NOT filled when bar's low > limit price."""
        handler = ExecutionHandler()
        order = _make_order(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price="95.00",
        )
        bar = _make_bar(low="98.00")  # Low doesn't reach limit

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 0

    def test_limit_sell_fills_when_price_rises(self):
        """SELL limit fills when bar's high >= limit price."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            price="101.50",
        )
        bar = _make_bar(high="102.00")  # High reaches above limit

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("101.50")

    def test_unfilled_limit_carries_over(self):
        """Unfilled limit order remains pending for next bar."""
        handler = ExecutionHandler()
        order = _make_order(
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price="90.00",
        )
        bar = _make_bar(low="98.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 0
        assert len(handler.pending_orders) == 1


# ===========================================================================
# TestStopOrderExecution
# ===========================================================================

class TestStopOrderExecution:
    """EXEC-03/06: Stop orders with gap-through handling."""

    def test_stop_loss_fills_at_stop_price(self):
        """SELL stop fills at stop price when intra-bar touch."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            price="99.00",
        )
        bar = _make_bar(open_="100.00", low="98.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("99.00")

    def test_gap_through_stop_fills_at_open(self):
        """TEST-04: Gap-through stop fills at open, NOT at stop price.

        Stop at 1.2000, next bar opens at 1.1950 (gapped through).
        Fill price should be 1.1950, not 1.2000.
        """
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            price="1.2000",
        )
        bar = _make_bar(open_="1.1950", high="1.1960", low="1.1900", close="1.1920")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        # CRITICAL: fill at open (1.1950), NOT at stop price (1.2000)
        assert fills[0].fill_price == Decimal("1.1950")

    def test_stop_not_triggered_when_not_reached(self):
        """Stop order NOT filled when price doesn't reach stop level."""
        handler = ExecutionHandler()
        order = _make_order(
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            price="95.00",
        )
        bar = _make_bar(low="98.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 0

    def test_buy_stop_triggered(self):
        """BUY stop triggers when bar's high >= stop price."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            price="103.00",
        )
        bar = _make_bar(open_="100.00", high="105.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert len(fills) == 1
        assert fills[0].fill_price == Decimal("103.00")


# ===========================================================================
# TestSlippageModel
# ===========================================================================

class TestSlippageModel:
    """EXEC-06: Slippage percentage model."""

    def test_buy_slippage_increases_price(self):
        """BUY slippage makes fill price higher than base."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0.001"),  # 0.1%
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(side=OrderSide.BUY)
        bar = _make_bar(open_="100.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].fill_price > Decimal("100.00")

    def test_sell_slippage_decreases_price(self):
        """SELL slippage makes fill price lower than base."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0.001"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(side=OrderSide.SELL)
        bar = _make_bar(open_="100.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].fill_price < Decimal("100.00")

    def test_slippage_stored_in_fill(self):
        """Slippage amount is stored as a separate field in FillEvent."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0.001"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(side=OrderSide.BUY)
        bar = _make_bar(open_="100.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].slippage == Decimal("0.100")  # 0.1% of 100


# ===========================================================================
# TestCommissionModel
# ===========================================================================

class TestCommissionModel:
    """EXEC-04: Commission per-trade + per-share."""

    def test_commission_calculated(self):
        """Commission = flat + per_share * quantity."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("5.00"),
            commission_per_share=Decimal("0.01"),
            spread_pct=Decimal("0"),
        )
        order = _make_order(quantity="100")
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        # Commission = 5.00 + 0.01 * 100 = 6.00
        assert fills[0].commission == Decimal("6.00")

    def test_commission_is_decimal(self):
        """Commission field is Decimal, not float."""
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0].commission, Decimal)


# ===========================================================================
# TestSpreadModel
# ===========================================================================

class TestSpreadModel:
    """EXEC-05: Spread simulation."""

    def test_spread_cost_stored(self):
        """Spread cost is stored in FillEvent."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0.001"),  # 0.1%
        )
        order = _make_order(side=OrderSide.BUY)
        bar = _make_bar(open_="100.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        # Half spread: 100.00 * 0.001 / 2 = 0.050
        assert fills[0].spread_cost == Decimal("0.050")

    def test_spread_affects_fill_price(self):
        """Spread increases BUY fill price."""
        handler = ExecutionHandler(
            slippage_pct=Decimal("0"),
            commission_per_trade=Decimal("0"),
            commission_per_share=Decimal("0"),
            spread_pct=Decimal("0.002"),  # 0.2%
        )
        order = _make_order(side=OrderSide.BUY)
        bar = _make_bar(open_="100.00")

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert fills[0].fill_price > Decimal("100.00")


# ===========================================================================
# TestDecimalArithmetic
# ===========================================================================

class TestDecimalArithmetic:
    """EXEC-07: All arithmetic in decimal.Decimal."""

    def test_fill_price_is_decimal(self):
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0].fill_price, Decimal)

    def test_slippage_is_decimal(self):
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0].slippage, Decimal)

    def test_commission_is_decimal(self):
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0].commission, Decimal)

    def test_spread_cost_is_decimal(self):
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        assert isinstance(fills[0].spread_cost, Decimal)

    def test_no_float_in_fill(self):
        """No float values anywhere in the FillEvent."""
        handler = ExecutionHandler()
        order = _make_order()
        bar = _make_bar()

        handler.submit_order(order)
        fills = handler.process_bar(bar)

        fill = fills[0]
        for field_name in ["fill_price", "commission", "slippage", "spread_cost", "quantity"]:
            val = getattr(fill, field_name)
            assert isinstance(val, Decimal), f"{field_name} is {type(val)}, not Decimal"


# ===========================================================================
# TestPendingOrders
# ===========================================================================

class TestPendingOrders:
    """Test pending order management."""

    def test_no_fill_without_bar(self):
        """Orders stay pending until a bar is processed."""
        handler = ExecutionHandler()
        order = _make_order()
        handler.submit_order(order)
        assert len(handler.pending_orders) == 1

    def test_filled_orders_removed_from_pending(self):
        """Filled orders are removed from pending list."""
        handler = ExecutionHandler()
        order = _make_order()
        handler.submit_order(order)

        bar = _make_bar()
        handler.process_bar(bar)

        assert len(handler.pending_orders) == 0

    def test_multiple_orders_same_bar(self):
        """Multiple orders can be filled on the same bar."""
        handler = ExecutionHandler()
        handler.submit_order(_make_order(side=OrderSide.BUY))
        handler.submit_order(_make_order(side=OrderSide.SELL))

        bar = _make_bar()
        fills = handler.process_bar(bar)

        assert len(fills) == 2

    def test_no_orders_no_fills(self):
        """Processing a bar with no pending orders returns empty list."""
        handler = ExecutionHandler()
        bar = _make_bar()
        fills = handler.process_bar(bar)
        assert len(fills) == 0
