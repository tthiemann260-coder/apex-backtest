# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: None (v3.0 archived)

No active milestone. Run `/gsd:new-milestone` to start the next development cycle.

## Previous Milestones

| Version | Shipped | Phases | Requirements | Tests |
|---------|---------|--------|-------------|-------|
| v1.0 | 2026-02-22 | 8 | 54 | 250 (91%) |
| v2.0 | 2026-02-22 | 5 | 30 | 427 (90%) |
| v3.0 | 2026-02-23 | 5 | 26 | 548 (87%) |

## Decisions
- All financial fields use Decimal with string constructor
- volume is int (counts units, not money)
- EventQueue wraps collections.deque
- FIFO PnL with accumulated_friction
- Engine: 10% fixed-fractional position sizing (replaced by RiskManager in Phase 16)
- Annualization: timeframe-specific factors
- v2.0: empyrical-reloaded for benchmark metrics, weasyprint/pdfkit for PDF export
- Phase 9: analytics.py for pure computation, dcc.Store for cross-tab data sharing
- Phase 9: Decimal->float conversion only at Plotly visualization boundary
- Phase 17: Per-symbol ExecutionHandlers for cross-symbol fill isolation
- Phase 17: Multi-price equity snapshots via compute_equity(all_prices)

## Context for Next Session
- v3.0 milestone archived (2026-02-23)
- 548 tests, 87% coverage, 18 phases total across 3 milestones
- Dashboard: 6 tabs (Overview, Analytics, Trade Analysis, Sensitivity, Risk Dashboard, Multi-Asset)
- Next: `/gsd:new-milestone` to define v4.0

---
*Last updated: 2026-02-23 — v3.0 archived*
