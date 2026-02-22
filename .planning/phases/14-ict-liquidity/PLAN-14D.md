# PLAN-14D: ICT Unit Tests

**Requirements:** TEST-20
**Estimated Tests:** ~30
**Dependencies:** PLAN-14A, PLAN-14B, PLAN-14C

## Deliverables

### `tests/test_ict.py`

#### Test Groups

**1. LiquiditySweepDetector (8 tests)**
- `test_bullish_sweep_detected` — bar.low < swing_low, close > swing_low → sweep confirmed
- `test_bearish_sweep_detected` — bar.high > swing_high, close < swing_high → sweep confirmed
- `test_sweep_rejected_depth_too_small` — sweep depth < min_depth_atr_mult * ATR → no sweep
- `test_sweep_rejected_no_close_back` — bar.low < swing_low but close also < swing_low → not confirmed
- `test_cooldown_prevents_resweep` — same level swept again within cooldown → ignored
- `test_swept_level_marked` — after sweep, same swing not swept again (marked in _swept_levels)
- `test_multiple_sweeps_in_sequence` — two different swing lows swept on consecutive bars
- `test_empty_swings_no_crash` — empty swing_highs/swing_lows → no sweeps, no exception

**2. InducementDetector (5 tests)**
- `test_bullish_idm_detected` — minor swing low between bullish BOS and current bar identified
- `test_bearish_idm_detected` — minor swing high between bearish BOS and current bar identified
- `test_idm_cleared` — price sweeps through IDM → cleared=True
- `test_no_idm_without_bos` — no BOS → no IDM detected
- `test_secondary_strength_lower_than_primary` — IDM uses strength=1 while primary uses strength=2

**3. KillZoneFilter (5 tests)**
- `test_ny_open_session` — 08:00 ET → NY_OPEN
- `test_london_open_session` — 03:00 ET → LONDON_OPEN
- `test_off_session` — 22:00 ET → OFF_SESSION
- `test_is_kill_zone_true` — 08:30 ET with NY_OPEN in active_sessions → True
- `test_is_kill_zone_false` — 22:00 ET → False

**4. PremiumDiscountZone (5 tests)**
- `test_equilibrium_computation` — (100 + 90) / 2 = 95.0
- `test_price_in_discount` — price=92 < equilibrium → "discount"
- `test_price_in_premium` — price=98 > equilibrium → "premium"
- `test_ote_long_zone` — price in 61.8-79% retracement → in_ote_zone True
- `test_flat_range_edge_case` — high==low → equilibrium=high, zone disabled

**5. ICTStrategy (7 tests)**
- `test_basic_long_signal_with_all_filters` — sweep + kill zone + OTE + OB+FVG → LONG signal
- `test_signal_blocked_outside_kill_zone` — all conditions met except kill zone → None
- `test_signal_blocked_in_premium_zone` — long setup but price in premium → None
- `test_signal_blocked_without_sweep` — all conditions except sweep → None
- `test_exit_on_choch` — CHOCH against position → EXIT signal
- `test_warmup_no_signals` — first N bars → all None
- `test_ict_importable_from_dashboard` — import works, STRATEGY_MAP key exists

#### Test Utilities
```python
BASE_TS = datetime(2024, 1, 1, 14, 0, tzinfo=ZoneInfo("America/New_York"))  # NY Open

def _make_bar(high, low, open_, close, ts=None, symbol="TEST"):
    """Create MarketEvent with Decimal prices."""

def _make_swing(price, ts, abs_idx):
    """Create SwingPoint for testing."""

def _make_bos(direction, broken_level, bar_idx, ts):
    """Create StructureBreak for testing."""
```

## Verification Criteria
- All 30 tests pass
- No test accesses future data
- All prices use Decimal with string constructor
- KillZone tests use timezone-aware timestamps
- Coverage of new modules >= 90%
