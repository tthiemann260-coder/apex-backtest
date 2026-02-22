# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v1.0 SHIPPED

### Summary
- All 8 phases complete
- 54/54 requirements fulfilled
- 250 tests, 91% coverage
- 28 commits, 11,076 LOC
- Archived: `.planning/milestones/v1.0-ROADMAP.md`, `.planning/milestones/v1.0-REQUIREMENTS.md`
- Git tag: `v1.0`

## Next Milestone: v2.0 (TBD)

Potential scope (from v2 requirements in archived REQUIREMENTS.md):
- Advanced Analytics (Monthly Returns Heatmap, Rolling Sharpe, MAE/MFE)
- Smart Money Concepts (Order Blocks, BOS, FVG Mitigation)
- Optimization (Grid Search, Walk-Forward, Robustness Report)

Use `/gsd:new-milestone` to define v2.0.

## Decisions
- All financial fields use Decimal with string constructor
- Event union type uses Python 3.10+ pipe syntax
- volume is int (counts units, not money)
- EventQueue wraps collections.deque
- Forward-filled bars get volume=1 (synthetic)
- Adjusted prices: ratio = Adj Close / Close
- Multi-symbol alignment: union of all dates, forward-fill per symbol
- Parquet caching: float storage, Decimal conversion only in stream_bars()
- FIFO PnL: accumulated_friction tracked proportionally
- Engine: 10% fixed-fractional position sizing
- Annualization: timeframe-specific factors in ANNUALIZATION_FACTORS dict

## Context for Next Session
- v1.0 SHIPPED and tagged
- Launch dashboard: `python -m src.dashboard` from project root
- Next: `/gsd:new-milestone` for v2.0

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** Health-check (250 tests, 91% coverage) + v1.0 milestone archived

---
*Last updated: 2026-02-22 — v1.0 shipped and archived*
