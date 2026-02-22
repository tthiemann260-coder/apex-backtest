"""
premium_discount.py — ICT Premium / Discount zone calculations.

Computes equilibrium, premium/discount classification, and Optimal
Trade Entry (OTE) zones from a swing-high / swing-low range.
All math uses ``decimal.Decimal`` with string constructors.

Requirement: ICT-04
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class PremiumDiscountZone:
    """Immutable record of premium/discount levels for a swing range."""
    range_high: Decimal
    range_low: Decimal
    equilibrium: Decimal
    ote_long_low: Decimal
    ote_long_high: Decimal
    ote_short_low: Decimal
    ote_short_high: Decimal


def compute_premium_discount(
    swing_high: Decimal,
    swing_low: Decimal,
) -> PremiumDiscountZone:
    """Compute premium/discount zone from a swing range.

    Parameters
    ----------
    swing_high : Decimal
        Upper bound of the swing range.
    swing_low : Decimal
        Lower bound of the swing range.

    Returns
    -------
    PremiumDiscountZone
        Frozen dataclass with equilibrium and OTE boundaries.
    """
    if swing_high == swing_low:
        return PremiumDiscountZone(
            range_high=swing_high,
            range_low=swing_low,
            equilibrium=swing_high,
            ote_long_low=swing_high,
            ote_long_high=swing_high,
            ote_short_low=swing_high,
            ote_short_high=swing_high,
        )

    equilibrium = (swing_high + swing_low) / Decimal('2')
    span = swing_high - swing_low

    return PremiumDiscountZone(
        range_high=swing_high,
        range_low=swing_low,
        equilibrium=equilibrium,
        ote_long_low=swing_high - span * Decimal('0.79'),
        ote_long_high=swing_high - span * Decimal('0.618'),
        ote_short_low=swing_low + span * Decimal('0.205'),
        ote_short_high=swing_low + span * Decimal('0.382'),
    )


def price_zone(price: Decimal, zone: PremiumDiscountZone) -> str:
    """Classify *price* as ``"premium"``, ``"discount"``, or ``"equilibrium"``."""
    if price > zone.equilibrium:
        return "premium"
    if price < zone.equilibrium:
        return "discount"
    return "equilibrium"


def in_ote_zone(
    price: Decimal,
    zone: PremiumDiscountZone,
    direction: str,
) -> bool:
    """Return True if *price* is within the OTE zone for *direction*.

    Parameters
    ----------
    price : Decimal
        Current market price.
    zone : PremiumDiscountZone
        Precomputed zone from :func:`compute_premium_discount`.
    direction : str
        ``"long"`` or ``"short"``.
    """
    if direction == "long":
        return zone.ote_long_low <= price <= zone.ote_long_high
    if direction == "short":
        return zone.ote_short_low <= price <= zone.ote_short_high
    raise ValueError(f"direction must be 'long' or 'short', got {direction!r}")
