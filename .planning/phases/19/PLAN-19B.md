# PLAN-19B: SQLite Persistence

**Requirements:** JOURNAL-04
**LOC:** ~180
**Dependencies:** PLAN-19A (models.py)
**Wave:** 2

## Neue Dateien

### `src/journal/store.py` (~180 LOC)

#### Decimal-Adapter (Modulebene)
```python
import sqlite3
from decimal import Decimal

sqlite3.register_adapter(Decimal, lambda d: str(d))
sqlite3.register_converter("DECIMAL", lambda b: Decimal(b.decode()))
```

#### TradeJournal Klasse

**__init__(db_path: str = "data/journal.db")**
- Verbindung mit `detect_types=sqlite3.PARSE_DECLTYPES`
- `self._conn.execute("PRAGMA journal_mode=WAL")` fuer bessere Concurrent-Reads
- Automatisch Schema erstellen via `_create_schema()`

**_create_schema()**
```sql
CREATE TABLE IF NOT EXISTS trades (
    trade_id         TEXT PRIMARY KEY,
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL,
    entry_time       TEXT NOT NULL,
    exit_time        TEXT NOT NULL,
    entry_price      DECIMAL NOT NULL,
    exit_price       DECIMAL NOT NULL,
    quantity         DECIMAL NOT NULL,
    commission_total DECIMAL NOT NULL,
    slippage_total   DECIMAL NOT NULL,
    spread_cost_total DECIMAL NOT NULL,
    gross_pnl        DECIMAL NOT NULL,
    net_pnl          DECIMAL NOT NULL,
    net_pnl_pct      DECIMAL NOT NULL,
    mae              DECIMAL,
    mfe              DECIMAL,
    duration_bars    INTEGER,
    timeframe        TEXT,
    strategy_name    TEXT,
    signal_strength  DECIMAL,
    setup_type       TEXT,
    market_condition TEXT,
    tags             TEXT,
    emotion_entry    TEXT,
    emotion_exit     TEXT,
    rule_followed    INTEGER,
    notes            TEXT,
    rating           INTEGER
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy  ON trades(strategy_name);
CREATE INDEX IF NOT EXISTS idx_trades_emotion   ON trades(emotion_entry);
CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades(exit_time);
```

**save_trade(entry: TradeJournalEntry) -> None**
- INSERT OR REPLACE INTO trades (...)
- tags als JSON-Array: `json.dumps(entry.tags)`
- datetime als ISO-8601: `entry.entry_time.isoformat()`
- rule_followed als INTEGER (0/1)

**save_trades(entries: list[TradeJournalEntry]) -> None**
- Batch-Insert in einer Transaktion
- `with self._conn: for entry in entries: self.save_trade(entry)`

**get_trade(trade_id: str) -> Optional[TradeJournalEntry]**
- SELECT * FROM trades WHERE trade_id = ?
- Reconstruct via `_row_to_entry()`

**get_all_trades(symbol: str | None = None, strategy: str | None = None) -> list[TradeJournalEntry]**
- Optionale Filter per WHERE clause
- ORDER BY exit_time ASC

**annotate(trade_id: str, **kwargs) -> None**
- UPDATE trades SET key=val, ... WHERE trade_id = ?
- Erlaubte Felder: setup_type, market_condition, tags, emotion_entry, emotion_exit, rule_followed, notes, rating
- Unerlaubte Felder (auto-filled) werden ignoriert mit Warning

**delete_trade(trade_id: str) -> None**
- DELETE FROM trades WHERE trade_id = ?

**count() -> int**
- SELECT COUNT(*) FROM trades

**close() -> None**
- self._conn.close()

#### Private Helper

**_row_to_entry(row: sqlite3.Row) -> TradeJournalEntry**
- Reconstruct: str → Decimal, ISO → datetime, TEXT → json.loads(tags), INTEGER → bool

## Architektur-Entscheidungen

1. **db_path = "data/journal.db"** — im bestehenden data/ Verzeichnis, separate vom Parquet-Cache
2. **WAL-Mode** — erlaubt parallele Reads waehrend Dashboard offen ist
3. **tags als JSON TEXT** — kein separates Tag-Table noetig fuer Single-User
4. **INSERT OR REPLACE** — idempotent, erlaubt Re-Runs ohne Duplikate
5. **Kein ORM** — stdlib sqlite3 ist ausreichend fuer Single-User

## .gitignore Update
```
data/journal.db
```
