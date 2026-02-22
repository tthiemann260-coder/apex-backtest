# Plan 10C: Order Block Detection

## Requirements: SMC-01

## Tasks

### 1. Create src/strategy/smc/order_block.py
- `OrderBlock` dataclass: direction, ob_high, ob_low, ob_50pct, state (ACTIVE/MITIGATED/INVALIDATED)
- `OrderBlockDetector` class:
  - `scan_for_new_ob(buf, bar_count, atr, swing_highs, swing_lows, ms_tracker)` → Optional[OrderBlock]
  - ATR-based displacement filter: displacement >= atr * threshold
  - BOS-triggered: only detect OB when a BOS just confirmed
  - Last opposing candle before displacement = the OB
  - `update_ob_states(event, bar_count, close_mitigation)` — mitigation/invalidation
  - Invalidation: close beyond 50% Mean Threshold
  - Parameters: atr_mult_threshold, ob_lookback_bars, max_active_obs, ob_max_age_bars

## Key Design
- OB formed at buf[-k] (past), confirmed at buf[-1] (current BOS bar)
- No lookahead: OB candle is always in the past relative to BOS
- Mitigation on return to zone: wick or close mode

## Success Criteria
- ATR displacement correctly filters weak moves
- OB state transitions: ACTIVE → MITIGATED or INVALIDATED
- No lookahead bias (confirmation after N bars)
