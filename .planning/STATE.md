# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v2.0 — Advanced Analytics, SMC & Optimization

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 9 | Advanced Analytics | Complete | 59 new (309 total) |
| 10 | Smart Money Concepts | Pending | - |
| 11 | Optimization Engine | Pending | - |
| 12 | Portfolio Enhancement | Pending | - |
| 13 | Report Export | Pending | - |

### Progress
- Requirements: 30 defined, 9 complete (ADV-01..09)
- Phases: 1/5 complete
- Tests: 309 passing, 91% coverage
- Next: `/gsd:plan-phase 10` for Smart Money Concepts

## Previous Milestone: v1.0 (SHIPPED 2026-02-22)
- 8 phases, 54 requirements, 250 tests, 91% coverage
- Archived: `.planning/milestones/v1.0-ROADMAP.md`

## Decisions
- All financial fields use Decimal with string constructor
- volume is int (counts units, not money)
- EventQueue wraps collections.deque
- FIFO PnL with accumulated_friction
- Engine: 10% fixed-fractional position sizing
- Annualization: timeframe-specific factors
- v2.0: empyrical-reloaded for benchmark metrics, weasyprint/pdfkit for PDF export
- Phase 9: analytics.py for pure computation, dcc.Store for cross-tab data sharing
- Phase 9: Decimal→float conversion only at Plotly visualization boundary

## Context for Next Session
- Phase 9 (Advanced Analytics) complete — all 9 requirements implemented + tested
- Dashboard has 4 tabs: Overview, Advanced Analytics, Trade Analysis, Sensitivity
- New files: src/analytics.py, tests/test_analytics.py
- Next: `/gsd:plan-phase 10` for Smart Money Concepts

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** Phase 9 complete — analytics.py, tabbed dashboard, 59 new tests

---
*Last updated: 2026-02-22 — Phase 9 complete*
