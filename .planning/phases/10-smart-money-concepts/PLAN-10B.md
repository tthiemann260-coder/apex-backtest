# Plan 10B: FVG Mitigation Tracker

## Requirements: SMC-03

## Tasks

### 1. Create src/strategy/smc/fvg_tracker.py
- `FVGState` enum: OPEN, TOUCHED, MITIGATED, INVERTED, EXPIRED
- `FairValueGap` dataclass with state machine fields
- `FVGTracker` class:
  - `detect_and_register(buf, bar_idx, atr)` — detect new FVGs from last 3 bars
  - `update_all_states(event, bar_idx)` — transition all tracked gaps
  - `get_active_fvgs(direction)` — filter OPEN/TOUCHED gaps
  - Parameters: max_fvgs, max_age_bars, min_size_atr_mult, mitigation_mode
  - Mitigation modes: "wick", "50pct", "close"
  - Memory limit enforcement: oldest OPEN gap expired when max exceeded
  - Age-based expiry: gaps older than max_age_bars auto-expire

## State Transitions
- OPEN → TOUCHED: wick enters zone
- TOUCHED → MITIGATED: based on mitigation_mode
- MITIGATED → INVERTED: price re-enters and closes beyond opposite boundary
- Any → EXPIRED: age > max_age_bars

## Success Criteria
- State machine transitions are correct and deterministic
- No same-bar detect+mitigate (formed_bar_idx guard)
- Memory bounded by max_fvgs
