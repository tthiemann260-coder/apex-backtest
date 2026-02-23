---
phase: 19
plan: B
subsystem: journal
tags: [sqlite, persistence, crud, decimal-adapters, wal-mode]
dependency-graph:
  requires: [19-A (TradeJournalEntry)]
  provides: [TradeJournal, save_trade, save_trades, get_trade, get_all_trades, annotate, delete_trade, count]
  affects: [19-C, 20-A, 20-B]
tech-stack:
  added: []
  patterns: [sqlite3-stdlib, decimal-text-adapters, wal-mode, json-encoded-tags, insert-or-replace]
key-files:
  created: [src/journal/store.py, tests/test_journal_store.py]
  modified: [.gitignore]
decisions:
  - "stdlib sqlite3 only, no ORM — sufficient for single-user desktop"
  - "Decimal stored as TEXT via module-level adapters (round-trip safe)"
  - "tags stored as JSON TEXT via json.dumps/json.loads"
  - "WAL mode for concurrent reads (dashboard + engine)"
  - "INSERT OR REPLACE for idempotent save (re-runs safe)"
  - "annotate() warns on auto-filled fields instead of raising"
metrics:
  duration: 207s
  completed: 2026-02-23T18:15:35Z
  loc-added: 260
  tests-added: 35
  files-created: 2
  files-modified: 1
---

# Phase 19 Plan B: SQLite Persistence Summary

**One-liner:** TradeJournal class wrapping stdlib sqlite3 with Decimal adapters, WAL mode, JSON-encoded tags, and 10 CRUD methods backed by 35 tests.

## What Was Built

### TradeJournal Class (src/journal/store.py, ~260 LOC)

**Module-level setup:**
- Decimal adapter: `Decimal -> str` for storage, `bytes -> Decimal` for retrieval
- Schema constants: CREATE TABLE, 4 indexes, INSERT OR REPLACE SQL

**Initialization:**
- Auto-creates parent directories via `Path.mkdir(parents=True)`
- Connects with `detect_types=PARSE_DECLTYPES` for Decimal round-trip
- Enables WAL mode for concurrent reads
- Creates schema idempotently (CREATE IF NOT EXISTS)

**Write Operations:**
- `save_trade(entry)` — single INSERT OR REPLACE with commit
- `save_trades(entries)` — batch insert in one transaction (context manager)
- `annotate(trade_id, **kwargs)` — UPDATE only 8 allowed fields, warns on disallowed
- `delete_trade(trade_id)` — DELETE by ID

**Read Operations:**
- `get_trade(trade_id)` — SELECT by PK, returns Optional[TradeJournalEntry]
- `get_all_trades(symbol, strategy)` — optional WHERE filters, ORDER BY exit_time ASC
- `count()` — SELECT COUNT(*)

**Private Helpers:**
- `_entry_to_row()` — entry to tuple (Decimal pass-through, datetime isoformat, tags json.dumps, bool to int)
- `_row_to_entry()` — Row to TradeJournalEntry (str to Decimal, ISO to datetime, json.loads tags, int to bool)

### Schema
- 28 columns matching TradeJournalEntry fields exactly
- DECIMAL type for 14 financial fields (stored as TEXT, adapted back)
- 4 indexes: symbol, strategy_name, emotion_entry, exit_time

### .gitignore Update
- Added `data/journal.db` to prevent committing the journal database

### Tests (35 tests in tests/test_journal_store.py)
- **TestSchemaCreation** (5): file creation, WAL mode, table, indexes, idempotency
- **TestSaveAndGet** (7): round-trip, Decimal precision, datetime, tags, bool, None, all fields
- **TestIdempotentSave** (2): no duplicates, value updates on re-save
- **TestBatchSave** (2): multiple trades, empty batch
- **TestGetAllTrades** (7): empty, no filter, symbol filter, strategy filter, combined, ordering, no match
- **TestAnnotate** (5): single field, multiple fields, bool, auto-field warning, all-disallowed
- **TestDeleteAndCount** (4): empty count, after inserts, delete existing, delete nonexistent
- **TestEdgeCases** (3): empty tags, all defaults, close/reopen persistence

## Commits

| Hash | Message |
|------|---------|
| df4b089 | feat(19-B): add SQLite persistence layer for Trading Journal |

## Verification

- All 35 new tests pass
- Full suite: 583 tests pass (548 existing + 35 new), 0 regressions
- Decimal precision verified: `Decimal("182.50")` round-trips exactly
- Datetime round-trips via ISO-8601 fromisoformat
- Tags round-trip as JSON list
- rule_followed round-trips as bool (stored as INTEGER 0/1)
- WAL mode confirmed via PRAGMA query
- Schema idempotent (CREATE IF NOT EXISTS + re-open)
- Data persists across close/reopen cycles

## Deviations from Plan

None -- plan executed exactly as written.

## Self-Check: PASSED

- [x] src/journal/store.py exists
- [x] tests/test_journal_store.py exists
- [x] .gitignore contains data/journal.db
- [x] Commit df4b089 exists in git log
