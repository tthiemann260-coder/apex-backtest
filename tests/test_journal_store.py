"""
test_journal_store.py — Tests for the SQLite persistence layer (store.py).

Covers:
- Schema creation, WAL mode
- save_trade / get_trade round-trip with Decimal precision
- save_trades batch operation
- get_all_trades with filters and ordering
- annotate (allowed + disallowed fields)
- delete_trade, count
- Idempotent INSERT OR REPLACE
- Edge cases (empty journal, missing trade, empty tags)

Run: pytest tests/test_journal_store.py -v
"""

import json
import warnings
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.journal.models import TradeJournalEntry
from src.journal.store import TradeJournal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def journal(tmp_path: Path) -> TradeJournal:
    """Create a TradeJournal backed by a temp SQLite file."""
    db_path = str(tmp_path / "test_journal.db")
    j = TradeJournal(db_path=db_path)
    yield j
    j.close()


@pytest.fixture
def sample_entry() -> TradeJournalEntry:
    """A fully populated TradeJournalEntry for testing."""
    return TradeJournalEntry(
        trade_id="T-001",
        symbol="AAPL",
        side="LONG",
        entry_time=datetime(2024, 3, 15, 9, 30, 0, tzinfo=timezone.utc),
        exit_time=datetime(2024, 3, 15, 10, 15, 0, tzinfo=timezone.utc),
        entry_price=Decimal("182.50"),
        exit_price=Decimal("185.25"),
        quantity=Decimal("100"),
        commission_total=Decimal("2.00"),
        slippage_total=Decimal("0.50"),
        spread_cost_total=Decimal("0.25"),
        gross_pnl=Decimal("275.00"),
        net_pnl=Decimal("272.25"),
        net_pnl_pct=Decimal("1.4918"),
        mae=Decimal("0.75"),
        mfe=Decimal("3.10"),
        duration_bars=18,
        timeframe="15m",
        strategy_name="FVG",
        signal_strength=Decimal("0.85"),
        setup_type="FVG",
        market_condition="TRENDING_UP",
        tags=["earnings", "tech"],
        emotion_entry="CONFIDENT",
        emotion_exit="DISCIPLINED",
        rule_followed=True,
        notes="Clean FVG fill, held to target.",
        rating=5,
    )


@pytest.fixture
def second_entry() -> TradeJournalEntry:
    """A second entry for multi-trade tests."""
    return TradeJournalEntry(
        trade_id="T-002",
        symbol="MSFT",
        side="SHORT",
        entry_time=datetime(2024, 3, 16, 14, 0, 0, tzinfo=timezone.utc),
        exit_time=datetime(2024, 3, 16, 15, 30, 0, tzinfo=timezone.utc),
        entry_price=Decimal("420.00"),
        exit_price=Decimal("418.50"),
        quantity=Decimal("50"),
        commission_total=Decimal("1.50"),
        slippage_total=Decimal("0.30"),
        spread_cost_total=Decimal("0.20"),
        gross_pnl=Decimal("75.00"),
        net_pnl=Decimal("73.00"),
        net_pnl_pct=Decimal("0.3476"),
        mae=Decimal("1.20"),
        mfe=Decimal("2.00"),
        duration_bars=6,
        timeframe="15m",
        strategy_name="BREAKOUT",
        signal_strength=Decimal("0.70"),
        setup_type="BREAKOUT",
        market_condition="TRENDING_DOWN",
        tags=["sector_rotation"],
        emotion_entry="CALM",
        emotion_exit="DISCIPLINED",
        rule_followed=True,
        notes="Trend continuation short.",
        rating=4,
    )


# ---------------------------------------------------------------------------
# Schema & Initialization
# ---------------------------------------------------------------------------

class TestSchemaCreation:
    """Tests for database schema and initialization."""

    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "sub" / "dir" / "journal.db"
        j = TradeJournal(db_path=str(db_path))
        assert db_path.exists()
        j.close()

    def test_wal_mode_enabled(self, journal: TradeJournal) -> None:
        cursor = journal._conn.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode == "wal"

    def test_trades_table_exists(self, journal: TradeJournal) -> None:
        cursor = journal._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
        )
        assert cursor.fetchone() is not None

    def test_indexes_exist(self, journal: TradeJournal) -> None:
        cursor = journal._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_trades_%'"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        expected = {
            "idx_trades_symbol",
            "idx_trades_strategy",
            "idx_trades_emotion",
            "idx_trades_exit_time",
        }
        assert indexes == expected

    def test_schema_idempotent(self, tmp_path: Path) -> None:
        """Creating schema twice should not raise."""
        db_path = str(tmp_path / "journal.db")
        j1 = TradeJournal(db_path=db_path)
        j1.close()
        j2 = TradeJournal(db_path=db_path)
        j2.close()


# ---------------------------------------------------------------------------
# Save & Get (round-trip)
# ---------------------------------------------------------------------------

class TestSaveAndGet:
    """Tests for save_trade / get_trade round-trip."""

    def test_save_and_get_roundtrip(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.trade_id == sample_entry.trade_id
        assert loaded.symbol == sample_entry.symbol
        assert loaded.side == sample_entry.side

    def test_decimal_precision_preserved(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.entry_price == Decimal("182.50")
        assert loaded.exit_price == Decimal("185.25")
        assert loaded.net_pnl == Decimal("272.25")
        assert loaded.net_pnl_pct == Decimal("1.4918")
        assert loaded.signal_strength == Decimal("0.85")

    def test_datetime_preserved(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.entry_time == sample_entry.entry_time
        assert loaded.exit_time == sample_entry.exit_time

    def test_tags_preserved_as_list(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.tags == ["earnings", "tech"]
        assert isinstance(loaded.tags, list)

    def test_rule_followed_bool_roundtrip(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.rule_followed is True

        # Also test False
        sample_entry.trade_id = "T-001b"
        sample_entry.rule_followed = False
        journal.save_trade(sample_entry)
        loaded2 = journal.get_trade("T-001b")
        assert loaded2 is not None
        assert loaded2.rule_followed is False

    def test_get_nonexistent_trade_returns_none(
        self, journal: TradeJournal
    ) -> None:
        result = journal.get_trade("DOES_NOT_EXIST")
        assert result is None

    def test_all_fields_roundtrip(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """Every field must survive save/load exactly."""
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.trade_id == sample_entry.trade_id
        assert loaded.symbol == sample_entry.symbol
        assert loaded.side == sample_entry.side
        assert loaded.entry_time == sample_entry.entry_time
        assert loaded.exit_time == sample_entry.exit_time
        assert loaded.entry_price == sample_entry.entry_price
        assert loaded.exit_price == sample_entry.exit_price
        assert loaded.quantity == sample_entry.quantity
        assert loaded.commission_total == sample_entry.commission_total
        assert loaded.slippage_total == sample_entry.slippage_total
        assert loaded.spread_cost_total == sample_entry.spread_cost_total
        assert loaded.gross_pnl == sample_entry.gross_pnl
        assert loaded.net_pnl == sample_entry.net_pnl
        assert loaded.net_pnl_pct == sample_entry.net_pnl_pct
        assert loaded.mae == sample_entry.mae
        assert loaded.mfe == sample_entry.mfe
        assert loaded.duration_bars == sample_entry.duration_bars
        assert loaded.timeframe == sample_entry.timeframe
        assert loaded.strategy_name == sample_entry.strategy_name
        assert loaded.signal_strength == sample_entry.signal_strength
        assert loaded.setup_type == sample_entry.setup_type
        assert loaded.market_condition == sample_entry.market_condition
        assert loaded.tags == sample_entry.tags
        assert loaded.emotion_entry == sample_entry.emotion_entry
        assert loaded.emotion_exit == sample_entry.emotion_exit
        assert loaded.rule_followed == sample_entry.rule_followed
        assert loaded.notes == sample_entry.notes
        assert loaded.rating == sample_entry.rating


# ---------------------------------------------------------------------------
# INSERT OR REPLACE (idempotent)
# ---------------------------------------------------------------------------

class TestIdempotentSave:
    """INSERT OR REPLACE should overwrite, not duplicate."""

    def test_save_same_id_twice_no_duplicate(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        journal.save_trade(sample_entry)
        assert journal.count() == 1

    def test_save_same_id_updates_values(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        sample_entry.notes = "Updated note"
        journal.save_trade(sample_entry)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.notes == "Updated note"
        assert journal.count() == 1


# ---------------------------------------------------------------------------
# Batch save
# ---------------------------------------------------------------------------

class TestBatchSave:
    """Tests for save_trades batch operation."""

    def test_save_multiple_trades(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        assert journal.count() == 2
        assert journal.get_trade("T-001") is not None
        assert journal.get_trade("T-002") is not None

    def test_batch_save_is_transactional(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """Empty batch should still work."""
        journal.save_trades([])
        assert journal.count() == 0


# ---------------------------------------------------------------------------
# get_all_trades with filters
# ---------------------------------------------------------------------------

class TestGetAllTrades:
    """Tests for get_all_trades with optional filters."""

    def test_get_all_empty_journal(self, journal: TradeJournal) -> None:
        result = journal.get_all_trades()
        assert result == []

    def test_get_all_no_filter(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        result = journal.get_all_trades()
        assert len(result) == 2

    def test_filter_by_symbol(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        result = journal.get_all_trades(symbol="AAPL")
        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_filter_by_strategy(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        result = journal.get_all_trades(strategy="FVG")
        assert len(result) == 1
        assert result[0].strategy_name == "FVG"

    def test_filter_by_symbol_and_strategy(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        result = journal.get_all_trades(symbol="AAPL", strategy="FVG")
        assert len(result) == 1
        result_empty = journal.get_all_trades(symbol="AAPL", strategy="BREAKOUT")
        assert len(result_empty) == 0

    def test_ordered_by_exit_time_asc(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        # Save in reverse order to verify sorting
        journal.save_trades([second_entry, sample_entry])
        result = journal.get_all_trades()
        assert result[0].trade_id == "T-001"  # earlier exit_time
        assert result[1].trade_id == "T-002"  # later exit_time

    def test_filter_no_match(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trade(sample_entry)
        result = journal.get_all_trades(symbol="TSLA")
        assert result == []


# ---------------------------------------------------------------------------
# Annotate
# ---------------------------------------------------------------------------

class TestAnnotate:
    """Tests for the annotate method."""

    def test_annotate_single_field(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        journal.annotate("T-001", notes="Updated via annotate")
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.notes == "Updated via annotate"

    def test_annotate_multiple_fields(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        journal.annotate(
            "T-001",
            setup_type="ORDER_BLOCK",
            emotion_entry="ANXIOUS",
            rating=3,
            tags=["updated", "retagged"],
        )
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.setup_type == "ORDER_BLOCK"
        assert loaded.emotion_entry == "ANXIOUS"
        assert loaded.rating == 3
        assert loaded.tags == ["updated", "retagged"]

    def test_annotate_rule_followed_bool(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        journal.annotate("T-001", rule_followed=False)
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.rule_followed is False

    def test_annotate_ignores_auto_fields_with_warning(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            journal.annotate("T-001", symbol="HACK", notes="legit update")
            assert len(w) == 1
            assert "symbol" in str(w[0].message)
        # symbol should NOT have changed
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.symbol == "AAPL"
        # notes SHOULD have changed
        assert loaded.notes == "legit update"

    def test_annotate_all_disallowed_does_nothing(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            journal.annotate("T-001", entry_price="999")
            assert len(w) == 1
        loaded = journal.get_trade("T-001")
        assert loaded is not None
        assert loaded.entry_price == Decimal("182.50")


# ---------------------------------------------------------------------------
# Delete & Count
# ---------------------------------------------------------------------------

class TestDeleteAndCount:
    """Tests for delete_trade and count."""

    def test_count_empty(self, journal: TradeJournal) -> None:
        assert journal.count() == 0

    def test_count_after_inserts(
        self,
        journal: TradeJournal,
        sample_entry: TradeJournalEntry,
        second_entry: TradeJournalEntry,
    ) -> None:
        journal.save_trades([sample_entry, second_entry])
        assert journal.count() == 2

    def test_delete_existing_trade(
        self, journal: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        journal.save_trade(sample_entry)
        assert journal.count() == 1
        journal.delete_trade("T-001")
        assert journal.count() == 0
        assert journal.get_trade("T-001") is None

    def test_delete_nonexistent_no_error(
        self, journal: TradeJournal
    ) -> None:
        """Deleting a non-existent trade should not raise."""
        journal.delete_trade("NOPE")
        assert journal.count() == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_tags_roundtrip(self, journal: TradeJournal) -> None:
        entry = TradeJournalEntry(
            trade_id="T-EMPTY",
            symbol="SPY",
            side="LONG",
            entry_time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc),
            entry_price=Decimal("470.00"),
            exit_price=Decimal("471.00"),
            quantity=Decimal("10"),
            commission_total=Decimal("0.50"),
            slippage_total=Decimal("0.10"),
            spread_cost_total=Decimal("0.05"),
            gross_pnl=Decimal("10.00"),
            net_pnl=Decimal("9.35"),
            net_pnl_pct=Decimal("0.1989"),
            tags=[],
        )
        journal.save_trade(entry)
        loaded = journal.get_trade("T-EMPTY")
        assert loaded is not None
        assert loaded.tags == []

    def test_default_values_roundtrip(self, journal: TradeJournal) -> None:
        """Entry with all defaults should round-trip cleanly."""
        entry = TradeJournalEntry(
            trade_id="T-DEFAULT",
            symbol="QQQ",
            side="SHORT",
            entry_time=datetime(2024, 6, 1, 9, 30, 0, tzinfo=timezone.utc),
            exit_time=datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
            entry_price=Decimal("450.00"),
            exit_price=Decimal("449.00"),
            quantity=Decimal("20"),
            commission_total=Decimal("1.00"),
            slippage_total=Decimal("0.20"),
            spread_cost_total=Decimal("0.10"),
            gross_pnl=Decimal("20.00"),
            net_pnl=Decimal("18.70"),
            net_pnl_pct=Decimal("0.2078"),
        )
        journal.save_trade(entry)
        loaded = journal.get_trade("T-DEFAULT")
        assert loaded is not None
        assert loaded.mae == Decimal("0")
        assert loaded.mfe == Decimal("0")
        assert loaded.duration_bars == 0
        assert loaded.timeframe == ""
        assert loaded.strategy_name == ""
        assert loaded.signal_strength == Decimal("0")
        assert loaded.setup_type == ""
        assert loaded.market_condition == ""
        assert loaded.tags == []
        assert loaded.emotion_entry == ""
        assert loaded.emotion_exit == ""
        assert loaded.rule_followed is True
        assert loaded.notes == ""
        assert loaded.rating == 0

    def test_close_and_reopen(
        self, tmp_path: Path, sample_entry: TradeJournalEntry
    ) -> None:
        """Data persists across close/reopen cycles."""
        db_path = str(tmp_path / "persist.db")
        j1 = TradeJournal(db_path=db_path)
        j1.save_trade(sample_entry)
        j1.close()

        j2 = TradeJournal(db_path=db_path)
        loaded = j2.get_trade("T-001")
        assert loaded is not None
        assert loaded.net_pnl == Decimal("272.25")
        j2.close()
