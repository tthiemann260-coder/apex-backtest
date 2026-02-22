# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Shipped Milestones

| Version | Shipped | Phases | Requirements | Tests |
|---------|---------|--------|-------------|-------|
| v1.0 | 2026-02-22 | 8 | 54 | 250 (91%) |
| v2.0 | 2026-02-22 | 5 | 30 | 427 (90%) |

## Current State

- **Latest version:** v2.0
- **Total tests:** 427 passing, 90% coverage
- **No active milestone** — run `/gsd:new-milestone` to start next

## Decisions
- All financial fields use Decimal with string constructor
- volume is int (counts units, not money)
- EventQueue wraps collections.deque
- FIFO PnL with accumulated_friction
- Engine: 10% fixed-fractional position sizing
- Annualization: timeframe-specific factors
- v2.0: empyrical-reloaded for benchmark metrics, weasyprint/pdfkit for PDF export
- Phase 9: analytics.py for pure computation, dcc.Store for cross-tab data sharing
- Phase 9: Decimal->float conversion only at Plotly visualization boundary

## Context for Next Session
- v2.0 MILESTONE COMPLETE and archived
- Git tag v2.0 created
- Next: `/gsd:new-milestone` to define v3.0 scope

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** v2.0 archived — tag created, milestones/ updated

---
*Last updated: 2026-02-22 — v2.0 archived*
