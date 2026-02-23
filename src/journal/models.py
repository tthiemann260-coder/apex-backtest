"""
models.py — Data models for the Trading Journal.

Enums for trade emotions, setup types, and market conditions.
TradeJournalEntry dataclass (NOT frozen — manual annotation fields are mutable).
Serialization helpers for JSON persistence.

All financial fields use decimal.Decimal with string constructor:
    Decimal('123.45')  # correct
    Decimal(123.45)    # FORBIDDEN — imprecise due to binary representation
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EntryEmotion(str, Enum):
    """Emotion felt when entering a trade."""
    CALM = "CALM"
    CONFIDENT = "CONFIDENT"
    ANXIOUS = "ANXIOUS"
    FOMO = "FOMO"
    REVENGE = "REVENGE"
    BORED = "BORED"
    EXCITED = "EXCITED"
    HESITANT = "HESITANT"


class ExitEmotion(str, Enum):
    """Emotion felt when exiting a trade."""
    DISCIPLINED = "DISCIPLINED"
    IMPATIENT = "IMPATIENT"
    GREEDY = "GREEDY"
    FEARFUL = "FEARFUL"
    OVERRODE_SYSTEM = "OVERRODE_SYSTEM"


class SetupType(str, Enum):
    """Type of trade setup identified."""
    FVG = "FVG"
    ORDER_BLOCK = "ORDER_BLOCK"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"
    KILL_ZONE = "KILL_ZONE"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    SMC_BOS = "SMC_BOS"
    CUSTOM = "CUSTOM"


class MarketCondition(str, Enum):
    """Market condition at time of trade."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOL = "HIGH_VOL"
    LOW_VOL = "LOW_VOL"
    PRE_NEWS = "PRE_NEWS"
    POST_NEWS = "POST_NEWS"


# ---------------------------------------------------------------------------
# TradeJournalEntry
# ---------------------------------------------------------------------------

@dataclass
class TradeJournalEntry:
    """
    A single trade journal entry combining auto-filled execution data
    with manually annotated reflection fields.

    NOT frozen: manual fields (setup_type, emotions, notes, etc.) are
    annotated post-trade via the dashboard. Auto-filled fields are set
    once at construction and should not be modified afterwards.
    """

    # --- Identity (auto-filled) ---
    trade_id: str
    symbol: str
    side: str                            # "LONG" or "SHORT"

    # --- Execution (all Decimal, auto-filled from FillEvent pairs) ---
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    commission_total: Decimal            # sum of entry + exit commissions
    slippage_total: Decimal              # sum of entry + exit slippage
    spread_cost_total: Decimal           # sum of entry + exit spread
    gross_pnl: Decimal                   # before friction
    net_pnl: Decimal                     # after all friction
    net_pnl_pct: Decimal                 # net_pnl / (entry_price * quantity)

    # --- Excursion (auto-tracked during open position) ---
    mae: Decimal = Decimal("0")          # Maximum Adverse Excursion
    mfe: Decimal = Decimal("0")          # Maximum Favorable Excursion
    duration_bars: int = 0

    # --- Context (auto-filled from strategy/engine) ---
    timeframe: str = ""
    strategy_name: str = ""
    signal_strength: Decimal = Decimal("0")

    # --- Manual Annotation (user-filled post-trade) ---
    setup_type: str = ""                 # SetupType value or custom string
    market_condition: str = ""           # MarketCondition value
    tags: list[str] = field(default_factory=list)
    emotion_entry: str = ""              # EntryEmotion value
    emotion_exit: str = ""               # ExitEmotion value
    rule_followed: bool = True
    notes: str = ""
    rating: int = 0                      # 1-5 stars, 0 = unrated


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def entry_to_dict(entry: TradeJournalEntry) -> dict[str, Any]:
    """Convert a TradeJournalEntry to a JSON-serializable dict.

    Decimal values are converted to str to preserve precision.
    datetime values are converted to ISO 8601 format strings.
    """
    result: dict[str, Any] = {}
    for f in fields(entry):
        value = getattr(entry, f.name)
        if isinstance(value, Decimal):
            result[f.name] = str(value)
        elif isinstance(value, datetime):
            result[f.name] = value.isoformat()
        elif isinstance(value, list):
            result[f.name] = list(value)  # shallow copy
        else:
            result[f.name] = value
    return result


def entry_from_dict(d: dict[str, Any]) -> TradeJournalEntry:
    """Reconstruct a TradeJournalEntry from a dict.

    str values for Decimal fields are converted back via Decimal(str).
    ISO 8601 strings for datetime fields are parsed via fromisoformat().
    """
    # Explicit field sets (reliable with __future__ annotations)
    _DECIMAL_FIELDS = {
        "entry_price", "exit_price", "quantity",
        "commission_total", "slippage_total", "spread_cost_total",
        "gross_pnl", "net_pnl", "net_pnl_pct",
        "mae", "mfe", "signal_strength",
    }
    _DATETIME_FIELDS = {"entry_time", "exit_time"}

    kwargs: dict[str, Any] = {}
    for key, value in d.items():
        if key in _DECIMAL_FIELDS and value is not None:
            kwargs[key] = Decimal(str(value))
        elif key in _DATETIME_FIELDS and isinstance(value, str):
            kwargs[key] = datetime.fromisoformat(value)
        elif key == "tags" and isinstance(value, list):
            kwargs[key] = list(value)
        else:
            kwargs[key] = value

    return TradeJournalEntry(**kwargs)
