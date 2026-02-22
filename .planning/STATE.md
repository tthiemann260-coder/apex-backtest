# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse

## Current Milestone: v3.0 — ICT/Liquidity, Regime Detection, Risk Management & Multi-Asset

### Phase Status

| Phase | Name | Status | Tests |
|-------|------|--------|-------|
| 14 | ICT / Liquidity Concepts | Complete | 30 new (457 total) |
| 15 | Regime Detection | Complete | 25 new (482 total) |
| 16 | Advanced Risk Management | Complete | 26 new (508 total) |
| 17 | Multi-Asset Foundation | Pending | — |
| 18 | Dashboard Integration (v3.0) | Pending | — |

### Progress
- Requirements: 26 defined, 17 complete
- Phases: 3/5 complete
- Tests: 508 passing, 90% coverage

## Previous Milestones

| Version | Shipped | Phases | Requirements | Tests |
|---------|---------|--------|-------------|-------|
| v1.0 | 2026-02-22 | 8 | 54 | 250 (91%) |
| v2.0 | 2026-02-22 | 5 | 30 | 427 (90%) |

## Decisions
- All financial fields use Decimal with string constructor
- volume is int (counts units, not money)
- EventQueue wraps collections.deque
- FIFO PnL with accumulated_friction
- Engine: 10% fixed-fractional position sizing (to be replaced by RiskManager in Phase 16)
- Annualization: timeframe-specific factors
- v2.0: empyrical-reloaded for benchmark metrics, weasyprint/pdfkit for PDF export
- Phase 9: analytics.py for pure computation, dcc.Store for cross-tab data sharing
- Phase 9: Decimal->float conversion only at Plotly visualization boundary

## Context for Next Session
- Phase 16 (Advanced Risk Management) COMPLETE — 26 new tests, 508 total, 90% coverage
- Next: `/gsd:plan-phase 17` to plan Multi-Asset Foundation

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** Phase 16 implemented — RiskManager, Kelly, Heat, Drawdown + Engine integration

---
*Last updated: 2026-02-22 — v3.0 milestone started*
