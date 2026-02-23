# Phase 19: Trading Journal — Foundation

**Goal:** Erstelle das Trading-Journal-Datenmodell mit automatischer Trade-Erfassung aus FillEvents, Emotion-Taxonomie, Tag-System und SQLite-Persistenz.
**Requirements:** JOURNAL-01, JOURNAL-02, JOURNAL-03, JOURNAL-04, JOURNAL-05
**Status:** Planned (3 Plans, 3 Waves)
**Verification:** PASS (1 Warning resolved)

## Plans

| Plan | Wave | LOC | Content |
|------|------|-----|---------|
| PLAN-19A | 1 | ~150 | Data Models: TradeJournalEntry, Emotion/Tag/Setup Enums |
| PLAN-19B | 2 | ~180 | SQLite Persistence: TradeJournal CRUD + annotate |
| PLAN-19C | 3 | ~500 | TradeBuilder Observer + Portfolio/Engine Hooks + 25 Tests |

## Neue Dateien (4)
- `src/journal/__init__.py`
- `src/journal/models.py`
- `src/journal/store.py`
- `src/journal/trade_builder.py`
- `tests/test_journal.py`

## Modifizierte Dateien (3)
- `src/portfolio.py` (+15 LOC: trade_builder property + hooks)
- `src/engine.py` (+10 LOC: trade_builder parameter in create_engine)
- `.gitignore` (+1 LOC: data/journal.db)

## Verification Targets
- `pytest tests/test_journal.py -v` — 25 Tests gruen
- `pytest tests/ -v` — 573+ Tests gruen (548 + 25)
- Bestehende Tests unveraendert (trade_builder=None default)

---
*Planned: 2026-02-23*
