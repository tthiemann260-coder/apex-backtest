"""
store.py — SQLite persistence layer for the Trading Journal.

TradeJournal class wraps stdlib sqlite3 with:
- Decimal adapters (stored as TEXT, round-trip safe)
- WAL mode for concurrent reads
- JSON-encoded tags
- ISO-8601 datetime strings
- Boolean rule_followed as INTEGER (0/1)

No ORM — plain SQL for a single-user desktop application.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import warnings
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from src.journal.models import TradeJournalEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decimal adapters (module-level registration)
# ---------------------------------------------------------------------------

sqlite3.register_adapter(Decimal, lambda d: str(d))
sqlite3.register_converter("DECIMAL", lambda b: Decimal(b.decode()))

# ---------------------------------------------------------------------------
# Annotatable fields (user may update post-trade)
# ---------------------------------------------------------------------------

_ANNOTATABLE_FIELDS = frozenset({
    "setup_type",
    "market_condition",
    "tags",
    "emotion_entry",
    "emotion_exit",
    "rule_followed",
    "notes",
    "rating",
})

# ---------------------------------------------------------------------------
# Schema SQL
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id          TEXT PRIMARY KEY,
    symbol            TEXT NOT NULL,
    side              TEXT NOT NULL,
    entry_time        TEXT NOT NULL,
    exit_time         TEXT NOT NULL,
    entry_price       DECIMAL NOT NULL,
    exit_price        DECIMAL NOT NULL,
    quantity          DECIMAL NOT NULL,
    commission_total  DECIMAL NOT NULL,
    slippage_total    DECIMAL NOT NULL,
    spread_cost_total DECIMAL NOT NULL,
    gross_pnl         DECIMAL NOT NULL,
    net_pnl           DECIMAL NOT NULL,
    net_pnl_pct       DECIMAL NOT NULL,
    mae               DECIMAL,
    mfe               DECIMAL,
    duration_bars     INTEGER,
    timeframe         TEXT,
    strategy_name     TEXT,
    signal_strength   DECIMAL,
    setup_type        TEXT,
    market_condition  TEXT,
    tags              TEXT,
    emotion_entry     TEXT,
    emotion_exit      TEXT,
    rule_followed     INTEGER,
    notes             TEXT,
    rating            INTEGER
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON trades(symbol);",
    "CREATE INDEX IF NOT EXISTS idx_trades_strategy  ON trades(strategy_name);",
    "CREATE INDEX IF NOT EXISTS idx_trades_emotion   ON trades(emotion_entry);",
    "CREATE INDEX IF NOT EXISTS idx_trades_exit_time ON trades(exit_time);",
]

_INSERT_SQL = """
INSERT OR REPLACE INTO trades (
    trade_id, symbol, side,
    entry_time, exit_time,
    entry_price, exit_price, quantity,
    commission_total, slippage_total, spread_cost_total,
    gross_pnl, net_pnl, net_pnl_pct,
    mae, mfe, duration_bars,
    timeframe, strategy_name, signal_strength,
    setup_type, market_condition, tags,
    emotion_entry, emotion_exit, rule_followed,
    notes, rating
) VALUES (
    ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?
);
"""


# ---------------------------------------------------------------------------
# TradeJournal
# ---------------------------------------------------------------------------

class TradeJournal:
    """SQLite-backed trade journal for single-user desktop use.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.  Parent directories are created
        automatically.  Defaults to ``data/journal.db``.
    """

    def __init__(self, db_path: str = "data/journal.db") -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            str(path),
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        """Create the trades table and indexes if they don't exist."""
        self._conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            self._conn.execute(idx_sql)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save_trade(self, entry: TradeJournalEntry) -> None:
        """Persist a single trade (INSERT OR REPLACE — idempotent)."""
        self._conn.execute(_INSERT_SQL, self._entry_to_row(entry))
        self._conn.commit()

    def save_trades(self, entries: list[TradeJournalEntry]) -> None:
        """Batch-persist multiple trades in a single transaction."""
        with self._conn:
            for entry in entries:
                self._conn.execute(_INSERT_SQL, self._entry_to_row(entry))

    def annotate(self, trade_id: str, **kwargs: object) -> None:
        """Update manual-annotation fields on an existing trade.

        Only the following fields may be annotated:
        setup_type, market_condition, tags, emotion_entry, emotion_exit,
        rule_followed, notes, rating.

        Unknown or auto-filled fields are silently ignored with a warning.
        """
        updates: dict[str, object] = {}
        for key, value in kwargs.items():
            if key not in _ANNOTATABLE_FIELDS:
                warnings.warn(
                    f"annotate(): ignoring non-annotatable field '{key}'",
                    stacklevel=2,
                )
                continue
            # Convert Python types to SQLite-compatible values
            if key == "tags" and isinstance(value, list):
                updates[key] = json.dumps(value)
            elif key == "rule_followed" and isinstance(value, bool):
                updates[key] = int(value)
            else:
                updates[key] = value

        if not updates:
            return

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [trade_id]
        self._conn.execute(
            f"UPDATE trades SET {set_clause} WHERE trade_id = ?",
            values,
        )
        self._conn.commit()

    def delete_trade(self, trade_id: str) -> None:
        """Remove a trade by ID."""
        self._conn.execute("DELETE FROM trades WHERE trade_id = ?", (trade_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_trade(self, trade_id: str) -> Optional[TradeJournalEntry]:
        """Fetch a single trade by ID, or None if not found."""
        cursor = self._conn.execute(
            "SELECT * FROM trades WHERE trade_id = ?",
            (trade_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def get_all_trades(
        self,
        symbol: str | None = None,
        strategy: str | None = None,
    ) -> list[TradeJournalEntry]:
        """Return trades with optional filters, ordered by exit_time ASC."""
        query = "SELECT * FROM trades"
        params: list[str] = []
        conditions: list[str] = []

        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if strategy is not None:
            conditions.append("strategy_name = ?")
            params.append(strategy)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY exit_time ASC"

        cursor = self._conn.execute(query, params)
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Return total number of trades in the journal."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM trades")
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_row(entry: TradeJournalEntry) -> tuple:
        """Convert a TradeJournalEntry to a tuple for INSERT."""
        return (
            entry.trade_id,
            entry.symbol,
            entry.side,
            entry.entry_time.isoformat(),
            entry.exit_time.isoformat(),
            entry.entry_price,
            entry.exit_price,
            entry.quantity,
            entry.commission_total,
            entry.slippage_total,
            entry.spread_cost_total,
            entry.gross_pnl,
            entry.net_pnl,
            entry.net_pnl_pct,
            entry.mae,
            entry.mfe,
            entry.duration_bars,
            entry.timeframe,
            entry.strategy_name,
            entry.signal_strength,
            entry.setup_type,
            entry.market_condition,
            json.dumps(entry.tags),
            entry.emotion_entry,
            entry.emotion_exit,
            int(entry.rule_followed),
            entry.notes,
            entry.rating,
        )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> TradeJournalEntry:
        """Reconstruct a TradeJournalEntry from a database row."""
        return TradeJournalEntry(
            trade_id=row["trade_id"],
            symbol=row["symbol"],
            side=row["side"],
            entry_time=datetime.fromisoformat(row["entry_time"]),
            exit_time=datetime.fromisoformat(row["exit_time"]),
            entry_price=Decimal(str(row["entry_price"])),
            exit_price=Decimal(str(row["exit_price"])),
            quantity=Decimal(str(row["quantity"])),
            commission_total=Decimal(str(row["commission_total"])),
            slippage_total=Decimal(str(row["slippage_total"])),
            spread_cost_total=Decimal(str(row["spread_cost_total"])),
            gross_pnl=Decimal(str(row["gross_pnl"])),
            net_pnl=Decimal(str(row["net_pnl"])),
            net_pnl_pct=Decimal(str(row["net_pnl_pct"])),
            mae=Decimal(str(row["mae"])) if row["mae"] is not None else Decimal("0"),
            mfe=Decimal(str(row["mfe"])) if row["mfe"] is not None else Decimal("0"),
            duration_bars=row["duration_bars"] or 0,
            timeframe=row["timeframe"] or "",
            strategy_name=row["strategy_name"] or "",
            signal_strength=(
                Decimal(str(row["signal_strength"]))
                if row["signal_strength"] is not None
                else Decimal("0")
            ),
            setup_type=row["setup_type"] or "",
            market_condition=row["market_condition"] or "",
            tags=json.loads(row["tags"]) if row["tags"] else [],
            emotion_entry=row["emotion_entry"] or "",
            emotion_exit=row["emotion_exit"] or "",
            rule_followed=bool(row["rule_followed"]) if row["rule_followed"] is not None else True,
            notes=row["notes"] or "",
            rating=row["rating"] or 0,
        )
