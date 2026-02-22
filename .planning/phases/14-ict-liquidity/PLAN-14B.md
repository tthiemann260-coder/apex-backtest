# PLAN-14B: Kill Zones + Premium/Discount Zones

**Requirements:** ICT-03, ICT-04
**Estimated LOC:** ~120
**Dependencies:** None (independent utility modules)

## Deliverables

### 1. `src/strategy/smc/kill_zone.py` (~60 LOC)

#### SessionType (Enum)
```python
class SessionType(Enum):
    LONDON_OPEN   = "LONDON_OPEN"     # 02:00-05:00 ET
    NY_OPEN       = "NY_OPEN"         # 07:00-10:00 ET
    NY_CLOSE      = "NY_CLOSE"        # 14:00-16:00 ET
    LONDON_CLOSE  = "LONDON_CLOSE"    # 10:00-12:00 ET (optional)
    OFF_SESSION   = "OFF_SESSION"     # Outside all kill zones
```

#### KillZoneFilter
```python
class KillZoneFilter:
    __init__(
        active_sessions: Optional[list[SessionType]] = None,
        # Default: [LONDON_OPEN, NY_OPEN, NY_CLOSE]
    )

    classify_session(timestamp: datetime) -> SessionType
    is_kill_zone(timestamp: datetime) -> bool
```

**Algorithm:**
1. Convert UTC timestamp to ET using `zoneinfo.ZoneInfo("America/New_York")`
2. Extract hour from ET time
3. Match against session windows (handles DST automatically via zoneinfo)
4. `is_kill_zone()` returns True if session is in `active_sessions` list

**Key Detail: zoneinfo handles EDT/EST automatically**
```python
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
et_time = timestamp.astimezone(ET)
hour = et_time.hour
```

### 2. `src/strategy/smc/premium_discount.py` (~60 LOC)

#### PremiumDiscountZone (frozen dataclass)
```
range_high: Decimal
range_low: Decimal
equilibrium: Decimal        # (high + low) / 2
ote_long_low: Decimal       # high - span * 0.79  (deep discount)
ote_long_high: Decimal      # high - span * 0.618 (shallow discount)
ote_short_low: Decimal      # low + span * 0.205  (shallow premium)
ote_short_high: Decimal     # low + span * 0.382  (deep premium)
```

#### Functions
```python
def compute_premium_discount(
    swing_high: Decimal,
    swing_low: Decimal,
) -> PremiumDiscountZone

def price_zone(
    price: Decimal,
    zone: PremiumDiscountZone,
) -> str  # "premium", "discount", or "equilibrium"

def in_ote_zone(
    price: Decimal,
    zone: PremiumDiscountZone,
    direction: str,  # "long" or "short"
) -> bool
```

**Algorithm:**
1. `equilibrium = (high + low) / Decimal('2')`
2. `span = high - low`
3. OTE Long zone: between 61.8% and 79% retracement from high (= discount)
4. OTE Short zone: between 20.5% and 38.2% retracement from low (= premium)
5. `price_zone()` returns "premium" if above equilibrium, "discount" if below
6. `in_ote_zone()` returns True if price is within the OTE range for the given direction

**Edge Case: Flat range**
- If `swing_high == swing_low`, return equilibrium = high, all OTE bounds = high
- Effectively disables filtering (all prices are "at equilibrium")

**All math uses Decimal with string constructor:**
```python
Decimal('0.79'), Decimal('0.618'), Decimal('0.382'), Decimal('0.205')
```

## Architecture Notes
- Both modules are pure utility — no strategy state, no event dependencies
- `KillZoneFilter` requires Python 3.9+ for `zoneinfo` (already required by project)
- `PremiumDiscountZone` is a pure function — takes swing prices, returns zone
- Both integrate into ICTStrategy as entry filters (not signal generators)
