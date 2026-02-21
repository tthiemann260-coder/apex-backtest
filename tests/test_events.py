"""
test_events.py — Tests for apex-backtest event types.

Covers: frozen immutability, field types, enum values, Decimal correctness.
Run: pytest tests/test_events.py -v
"""

import pytest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

from src.events import (
    MarketEvent,
    SignalEvent,
    OrderEvent,
    FillEvent,
    SignalType,
    OrderType,
    OrderSide,
    Event,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def now() -> datetime:
    return datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def market_event(now: datetime) -> MarketEvent:
    return MarketEvent(
        symbol="AAPL",
        timestamp=now,
        open=Decimal("182.15"),
        high=Decimal("183.50"),
        low=Decimal("181.00"),
        close=Decimal("182.80"),
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
        commission=Decimal("1.50"),
        slippage=Decimal("0.05"),
        spread_cost=Decimal("0.02"),
    )


# ---------------------------------------------------------------------------
# TestFrozenImmutability — 4 tests
# ---------------------------------------------------------------------------

class TestFrozenImmutability:
    """Every event type must raise FrozenInstanceError on field mutation."""

    def test_market_event_is_frozen(self, market_event: MarketEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            market_event.close = Decimal("999.99")

    def test_signal_event_is_frozen(self, signal_event: SignalEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            signal_event.strength = Decimal("0.50")

    def test_order_event_is_frozen(self, order_event: OrderEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            order_event.quantity = Decimal("200")

    def test_fill_event_is_frozen(self, fill_event: FillEvent) -> None:
        with pytest.raises(FrozenInstanceError):
            fill_event.fill_price = Decimal("200.00")


# ---------------------------------------------------------------------------
# TestFieldTypes — 8 tests
# ---------------------------------------------------------------------------

class TestFieldTypes:
    """Verify every field has the correct Python type."""

    def test_market_event_ohlc_are_decimal(self, market_event: MarketEvent) -> None:
        assert isinstance(market_event.open, Decimal)
        assert isinstance(market_event.high, Decimal)
        assert isinstance(market_event.low, Decimal)
        assert isinstance(market_event.close, Decimal)

    def test_market_event_volume_is_int(self, market_event: MarketEvent) -> None:
        assert isinstance(market_event.volume, int)
        # Explicitly verify it's not bool (bool is a subclass of int)
        assert not isinstance(market_event.volume, bool)

    def test_market_event_symbol_and_timeframe_are_str(
        self, market_event: MarketEvent
    ) -> None:
        assert isinstance(market_event.symbol, str)
        assert isinstance(market_event.timeframe, str)

    def test_signal_event_strength_is_decimal(
        self, signal_event: SignalEvent
    ) -> None:
        assert isinstance(signal_event.strength, Decimal)

    def test_order_event_quantity_is_decimal(
        self, order_event: OrderEvent
    ) -> None:
        assert isinstance(order_event.quantity, Decimal)

    def test_order_event_price_is_none_for_market(
        self, order_event: OrderEvent
    ) -> None:
        assert order_event.order_type == OrderType.MARKET
        assert order_event.price is None

    def test_order_event_price_is_decimal_for_limit(self, now: datetime) -> None:
        limit_order = OrderEvent(
            symbol="AAPL",
            timestamp=now,
            order_type=OrderType.LIMIT,
            side=OrderSide.BUY,
            quantity=Decimal("50"),
            price=Decimal("180.00"),
        )
        assert isinstance(limit_order.price, Decimal)

    def test_fill_event_financial_fields_are_decimal(
        self, fill_event: FillEvent
    ) -> None:
        assert isinstance(fill_event.quantity, Decimal)
        assert isinstance(fill_event.fill_price, Decimal)
        assert isinstance(fill_event.commission, Decimal)
        assert isinstance(fill_event.slippage, Decimal)
        assert isinstance(fill_event.spread_cost, Decimal)


# ---------------------------------------------------------------------------
# TestEnums — 5 tests
# ---------------------------------------------------------------------------

class TestEnums:
    """Verify enum members, values, and correct type usage on events."""

    def test_signal_type_has_exactly_three_members(self) -> None:
        members = list(SignalType)
        assert len(members) == 3
        assert SignalType.LONG.value == "LONG"
        assert SignalType.SHORT.value == "SHORT"
        assert SignalType.EXIT.value == "EXIT"

    def test_order_type_has_exactly_three_members(self) -> None:
        members = list(OrderType)
        assert len(members) == 3
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP.value == "STOP"

    def test_order_side_has_exactly_two_members(self) -> None:
        members = list(OrderSide)
        assert len(members) == 2
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

    def test_signal_event_signal_type_is_enum(
        self, signal_event: SignalEvent
    ) -> None:
        assert isinstance(signal_event.signal_type, SignalType)

    def test_order_event_enums_are_correct_types(
        self, order_event: OrderEvent
    ) -> None:
        assert isinstance(order_event.order_type, OrderType)
        assert isinstance(order_event.side, OrderSide)


# ---------------------------------------------------------------------------
# TestDecimalPrecision — 4 tests
# ---------------------------------------------------------------------------

class TestDecimalPrecision:
    """Prove why string-constructed Decimals are mandatory for financial math."""

    def test_string_constructor_preserves_exact_value(self) -> None:
        d = Decimal("0.10")
        assert str(d) == "0.10"

    def test_constructor_difference_documents_why_no_binary_fp(self) -> None:
        from_string = Decimal("0.10")
        from_binary_fp = Decimal(0.10)
        # These differ — the binary representation introduces imprecision
        assert from_string != from_binary_fp

    def test_market_event_close_exact_value(
        self, market_event: MarketEvent
    ) -> None:
        assert market_event.close == Decimal("182.80")

    def test_fill_event_commission_exact_value(
        self, fill_event: FillEvent
    ) -> None:
        assert fill_event.commission == Decimal("1.50")
