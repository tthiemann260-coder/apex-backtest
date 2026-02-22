# Plan 10A: SMC Foundation — Swing Detection + Market Structure

## Requirements: SMC-02 (partial)

## Tasks

### 1. Create src/strategy/smc/__init__.py
Empty package init.

### 2. Create src/strategy/smc/swing_detector.py
- `SwingDetector` class with `detect_confirmed_swings(bar_buffer, bar_count, strength)` method
- Fractal-based: candidate at `buf[-(strength+1)]`, needs `2*strength+1` bars minimum
- Returns `(new_highs, new_lows)` as lists of `{price: Decimal, timestamp, abs_idx}`
- Strict `>` / `<` for tie-breaking (no equal highs count as swing)
- Max swing history: 50

### 3. Create src/strategy/smc/structure.py
- `TrendState` enum: UNDEFINED, UPTREND, DOWNTREND
- `StructureBreak` dataclass: break_type (BOS/CHOCH), direction, broken_level, timestamp
- `MarketStructureTracker` class:
  - `on_new_swing_high(sh)` / `on_new_swing_low(sl)` — register swings
  - `on_bar_close(close, bar_idx, timestamp)` → Optional[StructureBreak]
  - BOS: break in trend direction or UNDEFINED
  - CHOCH: break against current trend
  - Close-confirmation only (wick doesn't count)

## Success Criteria
- Swing detection confirmed only after `strength` bars to the right
- BOS/CHOCH correctly classified based on trend state
- No lookahead bias — only uses buffer data
