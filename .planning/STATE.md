# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md (updated 2026-02-21)
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse
**Current focus:** ALL 8 PHASES COMPLETE

## Current Milestone: v1.0

### Phase Status

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 1 | Event Foundation | Complete | 2/2 |
| 2 | Data Layer | Complete | 3/3 |
| 3 | Strategy Layer | Complete | 1/1 |
| 4 | Execution Layer | Complete | 1/1 |
| 5 | Portfolio Layer | Complete | 1/1 |
| 6 | Engine Integration | Complete | 1/1 |
| 7 | Analytics Layer | Complete | 1/1 |
| 8 | Dashboard Layer | Complete | 1/1 |

### Progress
- ALL PHASES COMPLETE
- Requirements completed: ALL 54+ requirements (EDA, DATA, STRAT, EXEC, PORT, METR, DASH, TEST)
- Phases: 8/8 complete

### Test Count
- Phase 1: 34 tests (21 event types + 11 EventQueue + 2 causality)
- Phase 2: 43 tests (19 core + 12 API/cache + 12 gap/adj/align)
- Phase 3: 33 tests (11 BaseStrategy + 8 Reversal + 7 Breakout + 7 FVG)
- Phase 4: 30 tests (market/limit/stop fills, slippage, commission, spread)
- Phase 5: 22 tests (cash tracking, PnL, margin, FIFO, equity log)
- Phase 6: 11 tests (engine orchestration, causality, sweep isolation)
- Phase 7: 20 tests (PnL, Sharpe, Sortino, MDD, Calmar, trade stats, exposure)
- Phase 8: 31 tests (layout, candlestick, equity, drawdown, heatmap, app creation)
- **Total: 224 tests**

## Decisions
- All financial fields use Decimal with string constructor -- no float anywhere
- Event union type uses Python 3.10+ pipe syntax (X | Y) not typing.Union
- volume is int (counts units, not money) -- only non-Decimal numeric field
- EventQueue wraps collections.deque -- no custom linked list or heap
- Forward-filled bars get volume=1 (synthetic) to pass null-volume filter (DATA-06)
- Adjusted prices: ratio = Adj Close / Close, applied to all OHLC (DATA-07)
- Multi-symbol alignment: union of all dates, forward-fill per symbol (DATA-09)
- Parquet caching: float storage, Decimal conversion only in stream_bars() (DATA-04)
- FIFO PnL: Opening friction tracked in Position.accumulated_friction, deducted proportionally
- Engine: 10% fixed-fractional position sizing (equity * 0.10 / price)
- Annualization: timeframe-specific factors in ANNUALIZATION_FACTORS dict

## Context for Next Session
- ALL 8 PHASES COMPLETE: Full event-driven backtesting engine + dashboard operational
- 224 total tests, all passing
- Launch dashboard: `python -m src.dashboard` from project root
- All requirements fulfilled: EDA, DATA, STRAT, EXEC, PORT, METR, DASH, TEST

### Last Session
- **Timestamp:** 2026-02-22
- **Stopped at:** All phases complete, project v1.0 done
- **Commits:** 2dac6c2 (Phase 7), 17d4853 (Phase 8)

---
*Last updated: 2026-02-22 after completing Phase 8 Dashboard Layer — PROJECT COMPLETE*
