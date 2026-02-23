# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v4.0 — Strategy Builder, Trading Journal & Bayesian Optimization

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 19 | Trading Journal — Foundation | Plan B done (2/3) | 583 |
| 20 | Trading Journal — Dashboard & Analytics | Pending | — |
| 21 | Strategy Builder — Core Engine | Pending | — |
| 22 | Strategy Builder — Dashboard UI | Pending | — |
| 23 | Bayesian Optimization & Integration | Pending | — |

### Progress
- Requirements: 28 defined, 0 complete
- Phases: 0/5 complete
- Tests: 583 passing (+35 from 19-B)

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
- Phase 19 Plans A+B complete: data models + SQLite persistence
- Next: Execute PLAN-19C (TradeBuilder observer — fills to journal entries)
- 19-C depends on 19-B (done)

### Last Session
- **Timestamp:** 2026-02-23
- **Action:** Executed PLAN-19B — SQLite persistence (TradeJournal class, 10 CRUD methods, 35 tests)
- **Commits:** fd69cca (19-A), df4b089 (19-B)

---
*Last updated: 2026-02-23 — PLAN-19B complete*
