"""
events.py — Immutable event types for the apex-backtest EDA pipeline.

All dataclasses are frozen (immutable after construction).
All financial fields use decimal.Decimal with string constructor:
    Decimal('123.45')  # correct
    Decimal(123.45)    # FORBIDDEN — imprecise due to binary representation
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    EXIT = "EXIT"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


# ---------------------------------------------------------------------------
# Frozen Dataclasses (causal order: Market → Signal → Order → Fill)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketEvent:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: str


@dataclass(frozen=True)
class SignalEvent:
    symbol: str
    timestamp: datetime
    signal_type: SignalType
    strength: Decimal


@dataclass(frozen=True)
class OrderEvent:
    symbol: str
    timestamp: datetime
    order_type: OrderType
    side: OrderSide
    quantity: Decimal
    price: Optional[Decimal]


@dataclass(frozen=True)
class FillEvent:
    symbol: str
    timestamp: datetime
    side: OrderSide
    quantity: Decimal
    fill_price: Decimal
    commission: Decimal
    slippage: Decimal
    spread_cost: Decimal


# ---------------------------------------------------------------------------
# Union type alias for downstream type hints
# ---------------------------------------------------------------------------

Event = MarketEvent | SignalEvent | OrderEvent | FillEvent
