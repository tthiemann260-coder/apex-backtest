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
| 17 | Multi-Asset Foundation | Complete | 28 new (536 total) |
| 18 | Dashboard Integration (v3.0) | Pending | — |

### Progress
- Requirements: 26 defined, 21 complete
- Phases: 4/5 complete
- Tests: 536 passing, 90% coverage

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
- Engine: 10% fixed-fractional position sizing (replaced by RiskManager in Phase 16)
- Annualization: timeframe-specific factors
- v2.0: empyrical-reloaded for benchmark metrics, weasyprint/pdfkit for PDF export
- Phase 9: analytics.py for pure computation, dcc.Store for cross-tab data sharing
- Phase 9: Decimal->float conversion only at Plotly visualization boundary
- Phase 17: Per-symbol ExecutionHandlers for cross-symbol fill isolation
- Phase 17: Multi-price equity snapshots via compute_equity(all_prices)

## Context for Next Session
- Phase 17 (Multi-Asset Foundation) COMPLETE — 28 new tests, 536 total, 90% coverage
- Next: `/gsd:plan-phase 18` to plan Dashboard Integration (v3.0)

### Last Session
- **Timestamp:** 2026-02-22
- **Action:** Phase 17 implemented — merge_bars, MultiAssetEngine, rolling correlation, per-asset limits

---
*Last updated: 2026-02-22 — Phase 17 complete*
