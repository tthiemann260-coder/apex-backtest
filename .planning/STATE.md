# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v4.0 — Strategy Builder, Trading Journal & Bayesian Optimization

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 19 | Trading Journal — Foundation | Pending | — |
| 20 | Trading Journal — Dashboard & Analytics | Pending | — |
| 21 | Strategy Builder — Core Engine | Pending | — |
| 22 | Strategy Builder — Dashboard UI | Pending | — |
| 23 | Bayesian Optimization & Integration | Pending | — |

### Progress
- Requirements: 28 defined, 0 complete
- Phases: 0/5 complete
- Tests: 548 passing (from v3.0), 87% coverage

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
- v4.0: SQLite for Journal persistence (stdlib, zero dependencies)
- v4.0: type() metaclass for Strategy Builder compiler (kein exec/eval)
- v4.0: Optuna TPESampler with multivariate=True for parameter optimization

## Context for Next Session
- v4.0 milestone started (2026-02-23)
- Research complete for all 3 domains (journal, builder, optuna)
- Next: `/gsd:plan-phase 19` to start Trading Journal Foundation

### Last Session
- **Timestamp:** 2026-02-23
- **Action:** v3.0 archived, v4.0 milestone defined (28 requirements, 5 phases)

---
*Last updated: 2026-02-23 — v4.0 milestone started*
