# PLAN-14C: ICT Enhanced Strategy + Dashboard Integration

**Requirements:** ICT-05
**Estimated LOC:** ~180
**Dependencies:** PLAN-14A (sweeps, inducement), PLAN-14B (kill zones, premium/discount)

## Deliverables

### 1. `src/strategy/smc/ict_strategy.py` (~150 LOC)

#### ICTStrategy(BaseStrategy)
Extends existing SMCStrategy pipeline with 4 new ICT components.

```python
class ICTStrategy(BaseStrategy):
    __init__(
        symbol: str,
        timeframe: str = "1h",
        max_buffer_size: int = 500,
        params: Optional[dict] = None,
    )
```

**Additional params (on top of SMCStrategy params):**
- `sweep_min_depth_atr: float = 0.1` — min sweep depth as ATR multiple
- `sweep_cooldown_bars: int = 10` — per-level sweep cooldown
- `idm_secondary_strength: int = 1` — fractal strength for IDM swing detection
- `require_sweep: bool = True` — require liquidity sweep before entry
- `require_idm: bool = False` — require IDM clearance before entry
- `require_kill_zone: bool = True` — only enter during kill zone sessions
- `require_ote: bool = True` — only enter in OTE zone (discount for longs, premium for shorts)
- `active_sessions: list[str] = ["LONDON_OPEN", "NY_OPEN", "NY_CLOSE"]`

**Pipeline (14 steps, extends SMC 10-step):**
1. `update_buffer(event)` + `bar_count++`
2. Compute ATR
3. Warmup guard
4. Detect confirmed swings (SwingDetector)
5. Register swings with MarketStructureTracker
6. Check BOS/CHOCH
7. Detect new FVG
8. Detect new OB (on structure break)
9. **NEW: Check for liquidity sweeps** (LiquiditySweepDetector)
10. **NEW: Check for inducement clearance** (InducementDetector)
11. Update OB + FVG states
12. **Exit check** (CHOCH against position, OB invalidation — same as SMC)
13. **NEW: Entry filters** (Kill Zone + Premium/Discount + Sweep + IDM)
14. **Entry check** (OB + FVG confluence, gated by ICT filters)

**Entry Logic (enhanced):**
```python
def _check_entry(self, event):
    if self._in_position:
        return None

    # ICT Filters — all configurable, each can be disabled
    if self._require_kill_zone and not self._kz_filter.is_kill_zone(event.timestamp):
        return None

    trend = self._ms_tracker.trend

    # Long Entry
    if trend == TrendState.UPTREND:
        # Premium/Discount filter
        if self._require_ote:
            pd_zone = compute_premium_discount(
                self._swing_detector.swing_highs[-1].price,
                self._swing_detector.swing_lows[-1].price,
            )
            if not in_ote_zone(event.close, pd_zone, "long"):
                return None

        # Sweep filter
        if self._require_sweep:
            last_sweep = self._sweep_detector.last_bullish_sweep
            if last_sweep is None:
                return None

        # IDM filter
        if self._require_idm:
            if not self._idm_detector.has_cleared_idm("bullish"):
                return None

        # Core SMC confluence (OB + FVG) — same as SMCStrategy
        # ...OB zone + FVG overlap check...
```

**Key Design Decision: Composition over Inheritance**
- ICTStrategy does NOT subclass SMCStrategy
- Both subclass BaseStrategy directly
- ICTStrategy instantiates the same SMC components (SwingDetector, StructureTracker, etc.)
- This avoids fragile super() chains and makes each strategy independently testable

### 2. Dashboard Integration (~30 LOC changes)

#### `src/dashboard/callbacks.py`
Add to STRATEGY_MAP:
```python
"ict": ("src.strategy.smc.ict_strategy", "ICTStrategy"),
```

Add to SWEEP_PARAMS:
```python
"ict": {
    "swing_strength": [2, 3, 4],
    "atr_period": [10, 14, 20],
    "require_sweep": [True, False],
    "require_kill_zone": [True, False],
    "require_ote": [True, False],
},
```

#### `src/dashboard/layouts.py`
Add dropdown option:
```python
{"label": "ICT (Enhanced Liquidity)", "value": "ict"},
```

## Architecture Notes
- ICTStrategy is a parallel strategy to SMCStrategy, not a replacement
- Users choose between "SMC" (basic) and "ICT" (enhanced) in dashboard dropdown
- All ICT filters are configurable and can be individually disabled
- `current_atr` property exposed for integration with future RiskManager (Phase 16)
