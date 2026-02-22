# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v2.0 — Advanced Analytics, SMC & Optimization

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 9 | Advanced Analytics | Complete | 59 new (309 total) |
| 10 | Smart Money Concepts | Complete | 47 new (356 total) |
| 11 | Optimization Engine | Complete | 30 new (386 total) |
| 12 | Portfolio Enhancement | Pending | - |
| 13 | Report Export | Pending | - |

### Progress
- Requirements: 30 defined, 19 complete (ADV-01..09, SMC-01..04, TEST-10, OPT-01..04, TEST-11)
- Phases: 3/5 complete
- Tests: 386 passing, 90% coverage
- Next: `/gsd:plan-phase 12` for Portfolio Enhancement

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
- Phase 11 (Optimization Engine) complete — all 5 requirements (OPT-01..04, TEST-11)
- New package: src/optimization/ with 4 modules (walk_forward, sensitivity, monte_carlo, robustness)
- Walk-Forward: rolling IS/OOS windows, efficiency ratio
- Monte Carlo: trade PnL shuffling, p5/p95 percentiles
- Parameter Sensitivity: perturbation grid, CV stability metrics
- Robustness Report: composite score with pass/fail assessment
- Next: `/gsd:plan-phase 12` for Portfolio Enhancement

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** Phase 11 complete — optimization package (4 modules), 30 new tests

---
*Last updated: 2026-02-22 — Phase 11 complete*
