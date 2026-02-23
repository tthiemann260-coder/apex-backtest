---
phase: 19
plan: A
subsystem: journal
tags: [models, enums, dataclass, serialization]
dependency-graph:
  requires: []
  provides: [TradeJournalEntry, EntryEmotion, ExitEmotion, SetupType, MarketCondition, entry_to_dict, entry_from_dict]
  affects: [19-B, 19-C]
tech-stack:
  added: []
  patterns: [str-enum, mutable-dataclass, explicit-decimal-field-sets]
key-files:
  created: [src/journal/__init__.py, src/journal/models.py]
  modified: []
decisions:
  - "NOT frozen dataclass: manual annotation fields are mutable post-trade"
  - "Explicit Decimal/datetime field sets in entry_from_dict (reliable with __future__ annotations)"
  - "str(Enum) for all enums: allows direct string comparison and JSON serialization"
metrics:
  duration: 136s
  completed: 2026-02-23T18:10:24Z
  loc-added: 175
  files-created: 2
  files-modified: 0
---

# Phase 19 Plan A: Trading Journal Data Models Summary

**One-liner:** Four str-enums (emotion, setup, condition) plus mutable TradeJournalEntry dataclass with Decimal financials and JSON round-trip serialization.

## What Was Built

### Enums (4)
- **EntryEmotion** (8 values): CALM, CONFIDENT, ANXIOUS, FOMO, REVENGE, BORED, EXCITED, HESITANT
- **ExitEmotion** (5 values): DISCIPLINED, IMPATIENT, GREEDY, FEARFUL, OVERRODE_SYSTEM
- **SetupType** (8 values): FVG, ORDER_BLOCK, BREAKOUT, REVERSAL, KILL_ZONE, LIQUIDITY_SWEEP, SMC_BOS, CUSTOM
- **MarketCondition** (7 values): TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOL, LOW_VOL, PRE_NEWS, POST_NEWS

### TradeJournalEntry Dataclass
- 12 Decimal financial fields (entry/exit price, quantity, commissions, slippage, spread, PnL)
- Auto-filled identity + execution fields set at construction
- Manual annotation fields (setup_type, emotions, tags, notes, rating) mutable post-trade
- Defaults: mae/mfe=0, duration_bars=0, rule_followed=True, rating=0

### Serialization Helpers
- `entry_to_dict()`: Decimal to str, datetime to isoformat, list shallow-copy
- `entry_from_dict()`: Explicit field-set based reconstruction (no annotation introspection)

## Commits

| Hash | Message |
|------|---------|
| fd69cca | feat(19-A): add Trading Journal data models |

## Verification

- All 4 enums have correct member counts (8, 5, 8, 7)
- TradeJournalEntry is NOT frozen (manual fields mutable)
- All 12 Decimal fields survive JSON round-trip as Decimal
- Both datetime fields survive round-trip via isoformat
- Existing 548 tests still pass (0 regressions)

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

- [x] src/journal/__init__.py exists
- [x] src/journal/models.py exists
- [x] Commit fd69cca exists in git log
