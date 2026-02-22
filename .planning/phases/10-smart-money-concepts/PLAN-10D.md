# Plan 10D: Combined SMC Strategy

## Requirements: SMC-04

## Tasks

### 1. Create src/strategy/smc/smc_strategy.py
- `SMCStrategy(BaseStrategy)` combining all SMC components
- Pipeline per bar:
  1. update_buffer(event)
  2. Detect confirmed swings (SwingDetector)
  3. Check BOS/CHOCH (MarketStructureTracker)
  4. Detect new FVG (FVGTracker)
  5. Detect new OB (OrderBlockDetector, triggered by BOS)
  6. Update OB states
  7. Update FVG states
  8. Check exit conditions (priority over entry)
  9. Check entry conditions

### Entry Conditions (Long)
- Trend = UPTREND
- Active bullish OB exists
- Price in OB zone
- Overlapping bullish FVG (OPEN/TOUCHED)

### Entry Conditions (Short)
- Trend = DOWNTREND
- Active bearish OB exists
- Price in OB zone
- Overlapping bearish FVG (OPEN/TOUCHED)

### Exit Conditions
- OB invalidated (close beyond 50%)
- CHOCH against position direction

### 2. Update STRATEGY_MAP in callbacks.py
Add "smc" to strategy selector dropdown and STRATEGY_MAP.

## Success Criteria
- Generates correct SignalEvents
- Warmup guard prevents premature signals
- Exit fires on CHOCH or OB invalidation
