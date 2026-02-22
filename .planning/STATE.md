# Project State: apex-backtest

## Project Reference
See: .planning/PROJECT.md (updated 2026-02-21)
**Core value:** Mathematisch korrekte Backtesting-Ergebnisse
**Current focus:** Phase 2 -- Data Layer COMPLETE

## Current Milestone: v1.0

### Phase Status

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 1 | Event Foundation | Complete | 2/2 |
| 2 | Data Layer | Complete | 3/3 |
| 3 | Strategy Layer | Pending | 0/0 |
| 4 | Execution Layer | Pending | 0/0 |
| 5 | Portfolio Layer | Pending | 0/0 |
| 6 | Engine Integration | Pending | 0/0 |
| 7 | Analytics Layer | Pending | 0/0 |
| 8 | Dashboard Layer | Pending | 0/0 |

### Progress
- Current Phase: 3 (Strategy Layer) -- Phase 2 complete
- Requirements completed: DATA-01 through DATA-09, TEST-05, EDA-01, EDA-02, TEST-01
- Phases: 2/8 complete

### Performance Metrics

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 01 | 01 | 2m 1s | 3 | 5 |
| 01 | 02 | 1m 52s | 3 | 3 |
| 02 | 01 | ~3m | 2 | 3 |
| 02 | 02 | ~4m | 2 | 2 |
| 02 | 03 | ~3m | 2 | 2 |

### Test Count
- Phase 1: 34 tests (21 event types + 11 EventQueue + 2 causality)
- Phase 2: 43 tests (19 core + 12 API/cache + 12 gap/adj/align)
- **Total: 77 tests**

## Decisions
- All financial fields use Decimal with string constructor -- no float anywhere
- Event union type uses Python 3.10+ pipe syntax (X | Y) not typing.Union
- volume is int (counts units, not money) -- only non-Decimal numeric field
- EventQueue wraps collections.deque -- no custom linked list or heap
- Type validation uses isinstance against _VALID_TYPES tuple -- not duck typing
- No thread-safety in EventQueue -- single-threaded backtest loop assumed
- Forward-filled bars get volume=1 (synthetic) to pass null-volume filter (DATA-06)
- Adjusted prices: ratio = Adj Close / Close, applied to all OHLC (DATA-07)
- Multi-symbol alignment: union of all dates, forward-fill per symbol (DATA-09)
- Parquet caching: float storage, Decimal conversion only in stream_bars() (DATA-04)
- yfinance 4h timeframe: fetch 1h and resample later (yf has no 4h interval)

## Context for Next Session
- Phase 2 COMPLETE: DataHandler with 3 plans (core, API/cache, gap/adj/align)
- 77 total tests, all passing
- DataHandler features: CSV, yfinance, Parquet cache, gap fill, adjusted prices, multi-symbol alignment
- Next: Phase 3 -- Strategy Layer (base strategy class + Reversal/Breakout/FVG strategies)

### Last Session
- **Timestamp:** 2026-02-22
- **Stopped at:** Completed Phase 2 Data Layer (all 3 plans)
- **Commits:** d5ed484, 218c142, d4c9ebe

---
*Last updated: 2026-02-22 after completing Phase 2 Data Layer*
