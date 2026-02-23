# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v4.0 — Strategy Builder, Trading Journal & Bayesian Optimization

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 19 | Trading Journal — Foundation | COMPLETE (3/3) | 608 |
| 20 | Trading Journal — Dashboard & Analytics | Pending | — |
| 21 | Strategy Builder — Core Engine | Pending | — |
| 22 | Strategy Builder — Dashboard UI | Pending | — |
| 23 | Bayesian Optimization & Integration | Pending | — |

### Progress
- Requirements: 28 defined, 0 complete
- Phases: 1/5 complete
- Tests: 608 passing (+25 from 19-C)

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
- Phase 19: TradeBuilder uses Observer pattern — Portfolio calls on_fill/on_bar
- Phase 19: OrderSide.BUY/SELL converted to LONG/SHORT at TradeBuilder boundary
- Phase 19: Partial close not supported in v1 — trade sealed when qty=0

## Context for Next Session
- Phase 19 COMPLETE: data models + SQLite persistence + TradeBuilder integration
- Next: Plan Phase 20 — Trading Journal Dashboard & Analytics
- Full pipeline: FillEvent -> TradeBuilder -> TradeJournalEntry -> TradeJournal (SQLite)

### Last Session
- **Timestamp:** 2026-02-23
- **Action:** Executed PLAN-19C — TradeBuilder observer + Portfolio/Engine hooks + 25 tests
- **Commits:** f755786 (TradeBuilder), 9303923 (Portfolio hooks), 512b638 (Engine), 3865c2c (tests)

### Performance Metrics

| Phase-Plan | Duration | Tasks | Tests Added | Files |
|---|---|---|---|---|
| 19-C | 4m 38s | 4 | 25 | 4 |

---
*Last updated: 2026-02-23 — Phase 19 COMPLETE*
