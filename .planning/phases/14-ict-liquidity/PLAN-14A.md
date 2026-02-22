# PLAN-14A: Liquidity Sweep + Inducement Detection

**Requirements:** ICT-01, ICT-02
**Estimated LOC:** ~180
**Dependencies:** SwingDetector, MarketStructureTracker (Phase 10)

## Deliverables

### 1. `src/strategy/smc/liquidity_sweep.py` (~100 LOC)

#### LiquiditySweep (frozen dataclass)
```
direction: str          # "bullish" (swept lows) or "bearish" (swept highs)
swept_level: Decimal    # The swing price that was taken
sweep_wick: Decimal     # Wick tip of the sweep candle
sweep_bar_idx: int
timestamp: datetime
confirmed: bool         # True once close back inside range
```

#### LiquiditySweepDetector
```python
class LiquiditySweepDetector:
    __init__(
        min_depth_atr_mult: float = 0.1,    # min sweep depth as ATR fraction
        cooldown_bars: int = 10,             # per-level cooldown
        max_sweeps: int = 30,                # memory limit
    )

    check_for_sweeps(
        event: MarketEvent,
        swing_highs: list[SwingPoint],
        swing_lows: list[SwingPoint],
        current_atr: Decimal,
        bar_idx: int,
    ) -> list[LiquiditySweep]
```

**Algorithm:**
1. For each unswept swing low: check if `event.low < swing_low.price`
2. Confirmation: `event.close > swing_low.price` (wick through, close back above)
3. Apply depth filter: `abs(event.low - swing_low.price) >= min_depth_atr_mult * atr`
4. Mark swing as "swept" (track in `_swept_levels: set[int]` by abs_idx)
5. Cooldown: skip swing if `bar_idx - last_sweep_bar < cooldown_bars`
6. Mirror logic for bearish sweeps (above swing highs)

**Properties:**
- `recent_sweeps -> list[LiquiditySweep]` — last N sweeps
- `last_bullish_sweep -> Optional[LiquiditySweep]`
- `last_bearish_sweep -> Optional[LiquiditySweep]`

### 2. `src/strategy/smc/inducement.py` (~80 LOC)

#### InducementPoint (frozen dataclass)
```
direction: str          # "bullish" or "bearish" (trap direction)
idm_level: Decimal      # The IDM swing price
idm_bar_idx: int
cleared: bool           # True once price swept through the IDM
cleared_bar_idx: Optional[int]
```

#### InducementDetector
```python
class InducementDetector:
    __init__(
        secondary_strength: int = 1,   # lower fractal strength for IDM
        max_idm: int = 10,
    )

    detect_inducement(
        primary_highs: list[SwingPoint],
        primary_lows: list[SwingPoint],
        last_bos: Optional[StructureBreak],
        bar_idx: int,
    ) -> Optional[InducementPoint]

    check_idm_cleared(
        event: MarketEvent,
        bar_idx: int,
    ) -> Optional[InducementPoint]

    has_cleared_idm(direction: str) -> bool
    # Returns True if any IDM in given direction was cleared
```

**Algorithm:**
1. After a bullish BOS, scan for the lowest minor swing low between BOS bar and current bar
2. This swing was detected by a secondary SwingDetector (strength=1, vs primary strength=2+)
3. The IDM exists as a "trap" — retail shorts enter here
4. When price sweeps through the IDM (`event.low < idm_level`), mark `cleared=True`
5. A cleared IDM increases entry conviction in the ICT strategy

**Integration with existing SMC:**
- `InducementDetector` takes a secondary `SwingDetector(strength=1)` internally
- It reads the primary swing list from the main SwingDetector
- It does NOT modify any existing modules

## Architecture Notes
- Both modules are companions to existing SMC detectors
- Both consume `SwingPoint` and `StructureBreak` — no circular imports
- All prices in `Decimal`, timestamps via `datetime`
- `_swept_levels` set prevents duplicate sweeps of same swing point
