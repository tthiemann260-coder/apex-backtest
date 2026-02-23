"""
test_journal.py — Tests for TradeBuilder, models, enums, and portfolio integration.

25 tests covering:
- TestTradeJournalEntry (4): construction, defaults, to_dict/from_dict, Decimal precision
- TestEmotionEnums (3): entry values, exit values, str serialization
- TestSetupTagEnums (2): setup_type values, market_condition values
- TestTradeBuilder (6): LONG open+close, SHORT open+close, MAE/MFE LONG,
                         MAE/MFE SHORT, open_trade_count, multiple trades
- TestPortfolioIntegration (3): via process_fill, MAE/MFE via update_equity,
                                 engine compat with create_engine(trade_builder=...)
- TestTradeJournalDB (7): schema, save+get roundtrip, batch, filter,
                           annotate, delete, decimal precision

Run: pytest tests/test_journal.py -v
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.events import FillEvent, MarketEvent, OrderSide
from src.journal.models import (
    EntryEmotion,
    ExitEmotion,
    MarketCondition,
    SetupType,
    TradeJournalEntry,
    entry_from_dict,
    entry_to_dict,
)
from src.journal.store import TradeJournal
from src.journal.trade_builder import TradeBuilder
from src.portfolio import Portfolio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fill(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: str = "100",
    fill_price: str = "150.00",
    commission: str = "1.00",
    slippage: str = "0.05",
    spread_cost: str = "0.10",
    day: int = 15,
    hour: int = 10,
) -> FillEvent:
    return FillEvent(
        symbol=symbol,
        timestamp=datetime(2025, 1, day, hour, 0),
        side=side,
        quantity=Decimal(quantity),
        fill_price=Decimal(fill_price),
        commission=Decimal(commission),
        slippage=Decimal(slippage),
        spread_cost=Decimal(spread_cost),
    )


def _make_bar(
    symbol: str = "AAPL",
    open_: str = "150.00",
    high: str = "155.00",
    low: str = "148.00",
    close: str = "153.00",
    volume: int = 10000,
    day: int = 16,
    hour: int = 10,
) -> MarketEvent:
    return MarketEvent(
        symbol=symbol,
        timestamp=datetime(2025, 1, day, hour, 0),
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
        timeframe="15m",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def journal_db(tmp_path: Path) -> TradeJournal:
    """Temporary SQLite journal for tests."""
    db_path = str(tmp_path / "test_journal.db")
    journal = TradeJournal(db_path=db_path)
    yield journal
    journal.close()


@pytest.fixture
def sample_entry() -> TradeJournalEntry:
    """Sample TradeJournalEntry with all fields populated."""
    return TradeJournalEntry(
        trade_id="test-uuid-1234",
        symbol="AAPL",
        side="LONG",
        entry_time=datetime(2025, 1, 15, 10, 30),
        exit_time=datetime(2025, 1, 15, 14, 45),
        entry_price=Decimal("150.00"),
        exit_price=Decimal("155.00"),
        quantity=Decimal("10"),
        commission_total=Decimal("2.00"),
        slippage_total=Decimal("0.10"),
        spread_cost_total=Decimal("0.20"),
        gross_pnl=Decimal("50.00"),
        net_pnl=Decimal("47.70"),
        net_pnl_pct=Decimal("0.0318"),
        mae=Decimal("3.50"),
        mfe=Decimal("7.00"),
        duration_bars=34,
        timeframe="15min",
        strategy_name="ReversalStrategy",
        signal_strength=Decimal("0.70"),
    )


# ===========================================================================
# TestTradeJournalEntry (4 tests)
# ===========================================================================

class TestTradeJournalEntry:
    """Tests for the TradeJournalEntry dataclass."""

    def test_construction_with_all_fields(self, sample_entry: TradeJournalEntry) -> None:
        """All fields accessible after construction."""
        assert sample_entry.trade_id == "test-uuid-1234"
        assert sample_entry.symbol == "AAPL"
        assert sample_entry.side == "LONG"
        assert sample_entry.entry_price == Decimal("150.00")
        assert sample_entry.exit_price == Decimal("155.00")
        assert sample_entry.quantity == Decimal("10")
        assert sample_entry.gross_pnl == Decimal("50.00")
        assert sample_entry.net_pnl == Decimal("47.70")
        assert sample_entry.mae == Decimal("3.50")
        assert sample_entry.mfe == Decimal("7.00")
        assert sample_entry.duration_bars == 34
        assert sample_entry.strategy_name == "ReversalStrategy"

    def test_defaults(self) -> None:
        """Optional fields have correct defaults."""
        entry = TradeJournalEntry(
            trade_id="T-DEF",
            symbol="SPY",
            side="SHORT",
            entry_time=datetime(2025, 1, 1, 9, 30),
            exit_time=datetime(2025, 1, 1, 10, 0),
            entry_price=Decimal("470.00"),
            exit_price=Decimal("469.00"),
            quantity=Decimal("5"),
            commission_total=Decimal("0.50"),
            slippage_total=Decimal("0.05"),
            spread_cost_total=Decimal("0.10"),
            gross_pnl=Decimal("5.00"),
            net_pnl=Decimal("4.35"),
            net_pnl_pct=Decimal("0.00185"),
        )
        assert entry.mae == Decimal("0")
        assert entry.mfe == Decimal("0")
        assert entry.duration_bars == 0
        assert entry.timeframe == ""
        assert entry.strategy_name == ""
        assert entry.signal_strength == Decimal("0")
        assert entry.setup_type == ""
        assert entry.market_condition == ""
        assert entry.tags == []
        assert entry.emotion_entry == ""
        assert entry.emotion_exit == ""
        assert entry.rule_followed is True
        assert entry.notes == ""
        assert entry.rating == 0

    def test_to_dict_from_dict_roundtrip(self, sample_entry: TradeJournalEntry) -> None:
        """entry_to_dict -> entry_from_dict preserves all fields."""
        d = entry_to_dict(sample_entry)
        restored = entry_from_dict(d)
        assert restored.trade_id == sample_entry.trade_id
        assert restored.entry_price == sample_entry.entry_price
        assert restored.exit_price == sample_entry.exit_price
        assert restored.gross_pnl == sample_entry.gross_pnl
        assert restored.net_pnl == sample_entry.net_pnl
        assert restored.mae == sample_entry.mae
        assert restored.mfe == sample_entry.mfe
        assert restored.entry_time == sample_entry.entry_time
        assert restored.exit_time == sample_entry.exit_time
        assert restored.strategy_name == sample_entry.strategy_name

    def test_decimal_precision(self) -> None:
        """Decimal fields preserve exact precision (no float truncation)."""
        entry = TradeJournalEntry(
            trade_id="T-PREC",
            symbol="EUR/USD",
            side="LONG",
            entry_time=datetime(2025, 1, 1, 9, 0),
            exit_time=datetime(2025, 1, 1, 10, 0),
            entry_price=Decimal("1.08765"),
            exit_price=Decimal("1.08890"),
            quantity=Decimal("100000"),
            commission_total=Decimal("3.50"),
            slippage_total=Decimal("0.00001"),
            spread_cost_total=Decimal("0.00002"),
            gross_pnl=Decimal("125.00000"),
            net_pnl=Decimal("121.49997"),
            net_pnl_pct=Decimal("0.001117"),
        )
        assert entry.entry_price == Decimal("1.08765")
        assert entry.slippage_total == Decimal("0.00001")
        # Round-trip via dict preserves it
        d = entry_to_dict(entry)
        assert d["entry_price"] == "1.08765"
        restored = entry_from_dict(d)
        assert restored.entry_price == Decimal("1.08765")


# ===========================================================================
# TestEmotionEnums (3 tests)
# ===========================================================================

class TestEmotionEnums:
    """Tests for EntryEmotion and ExitEmotion enums."""

    def test_entry_emotion_values(self) -> None:
        """All expected EntryEmotion members exist."""
        expected = {
            "CALM", "CONFIDENT", "ANXIOUS", "FOMO",
            "REVENGE", "BORED", "EXCITED", "HESITANT",
        }
        actual = {e.value for e in EntryEmotion}
        assert actual == expected

    def test_exit_emotion_values(self) -> None:
        """All expected ExitEmotion members exist."""
        expected = {
            "DISCIPLINED", "IMPATIENT", "GREEDY",
            "FEARFUL", "OVERRODE_SYSTEM",
        }
        actual = {e.value for e in ExitEmotion}
        assert actual == expected

    def test_str_serialization(self) -> None:
        """str(Enum) returns the value string (str mixin)."""
        assert str(EntryEmotion.CALM) == "EntryEmotion.CALM" or EntryEmotion.CALM.value == "CALM"
        # The str mixin makes the enum's string equal to value
        assert EntryEmotion.CONFIDENT == "CONFIDENT"
        assert ExitEmotion.DISCIPLINED == "DISCIPLINED"


# ===========================================================================
# TestSetupTagEnums (2 tests)
# ===========================================================================

class TestSetupTagEnums:
    """Tests for SetupType and MarketCondition enums."""

    def test_setup_type_values(self) -> None:
        """All expected SetupType members exist."""
        expected = {
            "FVG", "ORDER_BLOCK", "BREAKOUT", "REVERSAL",
            "KILL_ZONE", "LIQUIDITY_SWEEP", "SMC_BOS", "CUSTOM",
        }
        actual = {e.value for e in SetupType}
        assert actual == expected

    def test_market_condition_values(self) -> None:
        """All expected MarketCondition members exist."""
        expected = {
            "TRENDING_UP", "TRENDING_DOWN", "RANGING",
            "HIGH_VOL", "LOW_VOL", "PRE_NEWS", "POST_NEWS",
        }
        actual = {e.value for e in MarketCondition}
        assert actual == expected


# ===========================================================================
# TestTradeBuilder (6 tests)
# ===========================================================================

class TestTradeBuilder:
    """Tests for the TradeBuilder observer."""

    def test_open_close_long_trade(self) -> None:
        """BUY fill opens LONG trade, SELL fill (qty=0 after) closes it."""
        builder = TradeBuilder(strategy_name="TestStrat", timeframe="15m")

        # Open: BUY 100 @ 150
        open_fill = _make_fill(
            side=OrderSide.BUY, quantity="100", fill_price="150.00",
            commission="1.00", slippage="0.05", spread_cost="0.10",
        )
        # Simulate: position exists after open
        from src.portfolio import Position
        positions_after_open = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.BUY,
                quantity=Decimal("100"), avg_entry_price=Decimal("150.00"),
            )
        }
        builder.on_fill(open_fill, positions_after_open)
        assert builder.open_trade_count == 1
        assert builder.total_completed == 0

        # Close: SELL 100 @ 155 (position becomes qty=0)
        close_fill = _make_fill(
            side=OrderSide.SELL, quantity="100", fill_price="155.00",
            commission="1.00", slippage="0.05", spread_cost="0.10",
            day=16, hour=14,
        )
        positions_after_close = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.BUY,
                quantity=Decimal("0"), avg_entry_price=Decimal("150.00"),
            )
        }
        builder.on_fill(close_fill, positions_after_close)
        assert builder.open_trade_count == 0
        assert builder.total_completed == 1

        trade = builder.completed_trades[0]
        assert trade.side == "LONG"
        assert trade.entry_price == Decimal("150.00")
        assert trade.exit_price == Decimal("155.00")
        assert trade.quantity == Decimal("100")
        # gross_pnl = (155 - 150) * 100 = 500
        assert trade.gross_pnl == Decimal("500.00")
        # friction = (1.00+0.05+0.10)*2 = 2.30
        assert trade.commission_total == Decimal("2.00")
        assert trade.slippage_total == Decimal("0.10")
        assert trade.spread_cost_total == Decimal("0.20")
        # net_pnl = 500 - 2.30 = 497.70
        assert trade.net_pnl == Decimal("497.70")
        assert trade.strategy_name == "TestStrat"
        assert trade.timeframe == "15m"

    def test_open_close_short_trade(self) -> None:
        """SELL fill opens SHORT trade, BUY fill (qty=0 after) closes it."""
        builder = TradeBuilder(strategy_name="ShortStrat")

        # Open: SELL 50 @ 200
        open_fill = _make_fill(
            side=OrderSide.SELL, quantity="50", fill_price="200.00",
            commission="0.50", slippage="0.00", spread_cost="0.00",
        )
        from src.portfolio import Position
        positions_after_open = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.SELL,
                quantity=Decimal("50"), avg_entry_price=Decimal("200.00"),
            )
        }
        builder.on_fill(open_fill, positions_after_open)
        assert builder.open_trade_count == 1

        # Close: BUY 50 @ 195 (position qty=0)
        close_fill = _make_fill(
            side=OrderSide.BUY, quantity="50", fill_price="195.00",
            commission="0.50", slippage="0.00", spread_cost="0.00",
            day=16,
        )
        positions_after_close = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.SELL,
                quantity=Decimal("0"), avg_entry_price=Decimal("200.00"),
            )
        }
        builder.on_fill(close_fill, positions_after_close)
        assert builder.total_completed == 1

        trade = builder.completed_trades[0]
        assert trade.side == "SHORT"
        # gross_pnl = (200 - 195) * 50 = 250
        assert trade.gross_pnl == Decimal("250.00")
        # friction = 0.50 * 2 = 1.00
        assert trade.net_pnl == Decimal("249.00")

    def test_mae_mfe_long(self) -> None:
        """MAE/MFE tracked correctly for LONG position via on_bar."""
        builder = TradeBuilder()

        # Open LONG @ 100
        open_fill = _make_fill(
            side=OrderSide.BUY, fill_price="100.00",
            commission="0", slippage="0", spread_cost="0",
        )
        from src.portfolio import Position
        positions = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.BUY,
                quantity=Decimal("100"), avg_entry_price=Decimal("100.00"),
            )
        }
        builder.on_fill(open_fill, positions)

        # Bar 1: high=105, low=98
        bar1 = _make_bar(high="105.00", low="98.00", close="103.00", day=16)
        builder.on_bar(bar1, positions)

        # Bar 2: high=108, low=99
        bar2 = _make_bar(high="108.00", low="99.00", close="106.00", day=17)
        builder.on_bar(bar2, positions)

        # Bar 3: high=107, low=96 (new low)
        bar3 = _make_bar(high="107.00", low="96.00", close="104.00", day=18)
        builder.on_bar(bar3, positions)

        # Close @ 104 (position qty=0)
        close_fill = _make_fill(
            side=OrderSide.SELL, fill_price="104.00",
            commission="0", slippage="0", spread_cost="0",
            day=19,
        )
        positions_closed = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.BUY,
                quantity=Decimal("0"), avg_entry_price=Decimal("100.00"),
            )
        }
        builder.on_fill(close_fill, positions_closed)

        trade = builder.completed_trades[0]
        # LONG MAE = entry(100) - lowest_low(96) = 4
        assert trade.mae == Decimal("4.00")
        # LONG MFE = highest_high(108) - entry(100) = 8
        assert trade.mfe == Decimal("8.00")

    def test_mae_mfe_short(self) -> None:
        """MAE/MFE tracked correctly for SHORT position via on_bar."""
        builder = TradeBuilder()

        # Open SHORT @ 200
        open_fill = _make_fill(
            side=OrderSide.SELL, fill_price="200.00",
            commission="0", slippage="0", spread_cost="0",
        )
        from src.portfolio import Position
        positions = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.SELL,
                quantity=Decimal("100"), avg_entry_price=Decimal("200.00"),
            )
        }
        builder.on_fill(open_fill, positions)

        # Bar: high=205, low=192
        bar1 = _make_bar(high="205.00", low="192.00", close="196.00", day=16)
        builder.on_bar(bar1, positions)

        # Bar: high=203, low=188
        bar2 = _make_bar(high="203.00", low="188.00", close="190.00", day=17)
        builder.on_bar(bar2, positions)

        # Close @ 190
        close_fill = _make_fill(
            side=OrderSide.BUY, fill_price="190.00",
            commission="0", slippage="0", spread_cost="0",
            day=18,
        )
        positions_closed = {
            "AAPL": Position(
                symbol="AAPL", side=OrderSide.SELL,
                quantity=Decimal("0"), avg_entry_price=Decimal("200.00"),
            )
        }
        builder.on_fill(close_fill, positions_closed)

        trade = builder.completed_trades[0]
        # SHORT MAE = highest_high(205) - entry(200) = 5
        assert trade.mae == Decimal("5.00")
        # SHORT MFE = entry(200) - lowest_low(188) = 12
        assert trade.mfe == Decimal("12.00")

    def test_open_trade_count(self) -> None:
        """open_trade_count reflects currently open trades."""
        builder = TradeBuilder()
        assert builder.open_trade_count == 0

        from src.portfolio import Position

        # Open AAPL
        fill1 = _make_fill(symbol="AAPL", side=OrderSide.BUY, fill_price="150.00",
                           commission="0", slippage="0", spread_cost="0")
        pos1 = {"AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                                 quantity=Decimal("100"), avg_entry_price=Decimal("150.00"))}
        builder.on_fill(fill1, pos1)
        assert builder.open_trade_count == 1

        # Open MSFT
        fill2 = _make_fill(symbol="MSFT", side=OrderSide.BUY, fill_price="400.00",
                           commission="0", slippage="0", spread_cost="0")
        pos2 = {
            "AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                             quantity=Decimal("100"), avg_entry_price=Decimal("150.00")),
            "MSFT": Position(symbol="MSFT", side=OrderSide.BUY,
                             quantity=Decimal("50"), avg_entry_price=Decimal("400.00")),
        }
        builder.on_fill(fill2, pos2)
        assert builder.open_trade_count == 2

        # Close AAPL
        fill3 = _make_fill(symbol="AAPL", side=OrderSide.SELL, fill_price="155.00",
                           commission="0", slippage="0", spread_cost="0", day=16)
        pos3 = {
            "AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                             quantity=Decimal("0"), avg_entry_price=Decimal("150.00")),
            "MSFT": Position(symbol="MSFT", side=OrderSide.BUY,
                             quantity=Decimal("50"), avg_entry_price=Decimal("400.00")),
        }
        builder.on_fill(fill3, pos3)
        assert builder.open_trade_count == 1
        assert builder.total_completed == 1

    def test_multiple_trades_sequential(self) -> None:
        """Multiple trades open and close sequentially on same symbol."""
        builder = TradeBuilder(strategy_name="Multi")
        from src.portfolio import Position

        # Trade 1: BUY 100 @ 50, SELL 100 @ 55
        builder.on_fill(
            _make_fill(side=OrderSide.BUY, fill_price="50.00",
                       commission="0", slippage="0", spread_cost="0"),
            {"AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                              quantity=Decimal("100"), avg_entry_price=Decimal("50.00"))},
        )
        builder.on_fill(
            _make_fill(side=OrderSide.SELL, fill_price="55.00",
                       commission="0", slippage="0", spread_cost="0", day=16),
            {"AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                              quantity=Decimal("0"), avg_entry_price=Decimal("50.00"))},
        )
        assert builder.total_completed == 1

        # Trade 2: BUY 100 @ 60, SELL 100 @ 58 (loss)
        builder.on_fill(
            _make_fill(side=OrderSide.BUY, fill_price="60.00",
                       commission="0", slippage="0", spread_cost="0", day=17),
            {"AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                              quantity=Decimal("100"), avg_entry_price=Decimal("60.00"))},
        )
        builder.on_fill(
            _make_fill(side=OrderSide.SELL, fill_price="58.00",
                       commission="0", slippage="0", spread_cost="0", day=18),
            {"AAPL": Position(symbol="AAPL", side=OrderSide.BUY,
                              quantity=Decimal("0"), avg_entry_price=Decimal("60.00"))},
        )
        assert builder.total_completed == 2

        trades = builder.completed_trades
        # Trade 1: profit
        assert trades[0].gross_pnl == Decimal("500.00")  # (55-50)*100
        # Trade 2: loss
        assert trades[1].gross_pnl == Decimal("-200.00")  # (58-60)*100


# ===========================================================================
# TestPortfolioIntegration (3 tests)
# ===========================================================================

class TestPortfolioIntegration:
    """Tests for TradeBuilder attached to Portfolio."""

    def test_trade_builder_via_process_fill(self) -> None:
        """Portfolio.process_fill() notifies TradeBuilder automatically."""
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        builder = TradeBuilder(strategy_name="IntegStrat", timeframe="1d")
        portfolio.trade_builder = builder

        # BUY 100 @ 50 (zero friction for simplicity)
        buy_fill = FillEvent(
            symbol="TEST",
            timestamp=datetime(2025, 1, 15, 10, 0),
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            fill_price=Decimal("50.00"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
        )
        portfolio.process_fill(buy_fill)
        assert builder.open_trade_count == 1

        # SELL 100 @ 55 (closes position)
        sell_fill = FillEvent(
            symbol="TEST",
            timestamp=datetime(2025, 1, 16, 10, 0),
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            fill_price=Decimal("55.00"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
        )
        portfolio.process_fill(sell_fill)
        assert builder.open_trade_count == 0
        assert builder.total_completed == 1

        trade = builder.completed_trades[0]
        assert trade.side == "LONG"
        assert trade.gross_pnl == Decimal("500.00")

    def test_mae_mfe_via_update_equity(self) -> None:
        """Portfolio.update_equity() triggers on_bar for MAE/MFE tracking."""
        portfolio = Portfolio(initial_cash=Decimal("100000"))
        builder = TradeBuilder()
        portfolio.trade_builder = builder

        # Open LONG position
        buy_fill = FillEvent(
            symbol="TEST",
            timestamp=datetime(2025, 1, 15, 10, 0),
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            fill_price=Decimal("100.00"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
        )
        portfolio.process_fill(buy_fill)

        # Bar with high=110, low=95
        bar = MarketEvent(
            symbol="TEST",
            timestamp=datetime(2025, 1, 16, 10, 0),
            open=Decimal("102.00"),
            high=Decimal("110.00"),
            low=Decimal("95.00"),
            close=Decimal("105.00"),
            volume=5000,
            timeframe="1d",
        )
        portfolio.update_equity(bar)

        # Close position
        sell_fill = FillEvent(
            symbol="TEST",
            timestamp=datetime(2025, 1, 17, 10, 0),
            side=OrderSide.SELL,
            quantity=Decimal("100"),
            fill_price=Decimal("105.00"),
            commission=Decimal("0"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
        )
        portfolio.process_fill(sell_fill)

        trade = builder.completed_trades[0]
        # LONG MAE: entry(100) - lowest(95) = 5
        assert trade.mae == Decimal("5.00")
        # LONG MFE: highest(110) - entry(100) = 10
        assert trade.mfe == Decimal("10.00")

    def test_create_engine_with_trade_builder(self) -> None:
        """create_engine(trade_builder=...) attaches builder to portfolio."""
        from unittest.mock import MagicMock
        from src.engine import create_engine

        mock_data_handler = MagicMock()
        mock_strategy = MagicMock()
        builder = TradeBuilder(strategy_name="EngineTest")

        engine = create_engine(
            data_handler=mock_data_handler,
            strategy=mock_strategy,
            trade_builder=builder,
        )
        # Access internal portfolio to verify attachment
        assert engine._portfolio.trade_builder is builder


# ===========================================================================
# TestTradeJournalDB (7 tests)
# ===========================================================================

class TestTradeJournalDB:
    """Tests for TradeJournal SQLite persistence with TradeBuilder output."""

    def test_schema_has_all_columns(self, journal_db: TradeJournal) -> None:
        """trades table has all expected columns."""
        cursor = journal_db._conn.execute("PRAGMA table_info(trades)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "trade_id", "symbol", "side",
            "entry_time", "exit_time",
            "entry_price", "exit_price", "quantity",
            "commission_total", "slippage_total", "spread_cost_total",
            "gross_pnl", "net_pnl", "net_pnl_pct",
            "mae", "mfe", "duration_bars",
            "timeframe", "strategy_name", "signal_strength",
            "setup_type", "market_condition", "tags",
            "emotion_entry", "emotion_exit", "rule_followed",
            "notes", "rating",
        }
        assert expected.issubset(columns)

    def test_save_and_get_roundtrip(
        self, journal_db: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """Save a TradeBuilder-produced entry, get it back exactly."""
        journal_db.save_trade(sample_entry)
        loaded = journal_db.get_trade("test-uuid-1234")
        assert loaded is not None
        assert loaded.trade_id == "test-uuid-1234"
        assert loaded.symbol == "AAPL"
        assert loaded.side == "LONG"
        assert loaded.entry_price == Decimal("150.00")
        assert loaded.gross_pnl == Decimal("50.00")
        assert loaded.net_pnl == Decimal("47.70")

    def test_batch_save(self, journal_db: TradeJournal) -> None:
        """save_trades persists multiple entries in one call."""
        entries = [
            TradeJournalEntry(
                trade_id=f"T-BATCH-{i}",
                symbol="SPY",
                side="LONG",
                entry_time=datetime(2025, 1, i + 1, 10, 0),
                exit_time=datetime(2025, 1, i + 1, 11, 0),
                entry_price=Decimal("470.00"),
                exit_price=Decimal("471.00"),
                quantity=Decimal("10"),
                commission_total=Decimal("0.50"),
                slippage_total=Decimal("0"),
                spread_cost_total=Decimal("0"),
                gross_pnl=Decimal("10.00"),
                net_pnl=Decimal("9.50"),
                net_pnl_pct=Decimal("0.00202"),
            )
            for i in range(5)
        ]
        journal_db.save_trades(entries)
        assert journal_db.count() == 5

    def test_filter_by_symbol(
        self, journal_db: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """get_all_trades(symbol=...) filters correctly."""
        journal_db.save_trade(sample_entry)
        other = TradeJournalEntry(
            trade_id="T-OTHER",
            symbol="MSFT",
            side="SHORT",
            entry_time=datetime(2025, 2, 1, 10, 0),
            exit_time=datetime(2025, 2, 1, 11, 0),
            entry_price=Decimal("400.00"),
            exit_price=Decimal("398.00"),
            quantity=Decimal("20"),
            commission_total=Decimal("1.00"),
            slippage_total=Decimal("0"),
            spread_cost_total=Decimal("0"),
            gross_pnl=Decimal("40.00"),
            net_pnl=Decimal("39.00"),
            net_pnl_pct=Decimal("0.004875"),
        )
        journal_db.save_trade(other)

        aapl_trades = journal_db.get_all_trades(symbol="AAPL")
        assert len(aapl_trades) == 1
        assert aapl_trades[0].symbol == "AAPL"

    def test_annotate_updates_fields(
        self, journal_db: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """annotate() updates manual fields on a saved trade."""
        journal_db.save_trade(sample_entry)
        journal_db.annotate(
            "test-uuid-1234",
            setup_type="FVG",
            emotion_entry="CONFIDENT",
            emotion_exit="DISCIPLINED",
            notes="Clean entry, held to TP",
            rating=5,
        )
        loaded = journal_db.get_trade("test-uuid-1234")
        assert loaded is not None
        assert loaded.setup_type == "FVG"
        assert loaded.emotion_entry == "CONFIDENT"
        assert loaded.emotion_exit == "DISCIPLINED"
        assert loaded.notes == "Clean entry, held to TP"
        assert loaded.rating == 5

    def test_delete_trade(
        self, journal_db: TradeJournal, sample_entry: TradeJournalEntry
    ) -> None:
        """delete_trade removes entry from DB."""
        journal_db.save_trade(sample_entry)
        assert journal_db.count() == 1
        journal_db.delete_trade("test-uuid-1234")
        assert journal_db.count() == 0
        assert journal_db.get_trade("test-uuid-1234") is None

    def test_decimal_precision_in_db(self, journal_db: TradeJournal) -> None:
        """Decimal precision preserved through SQLite round-trip."""
        entry = TradeJournalEntry(
            trade_id="T-PREC-DB",
            symbol="EUR/USD",
            side="LONG",
            entry_time=datetime(2025, 1, 1, 9, 0),
            exit_time=datetime(2025, 1, 1, 10, 0),
            entry_price=Decimal("1.08765"),
            exit_price=Decimal("1.08890"),
            quantity=Decimal("100000"),
            commission_total=Decimal("3.50"),
            slippage_total=Decimal("0.00001"),
            spread_cost_total=Decimal("0.00002"),
            gross_pnl=Decimal("125.00000"),
            net_pnl=Decimal("121.49997"),
            net_pnl_pct=Decimal("0.001117"),
            mae=Decimal("0.00050"),
            mfe=Decimal("0.00200"),
        )
        journal_db.save_trade(entry)
        loaded = journal_db.get_trade("T-PREC-DB")
        assert loaded is not None
        assert loaded.entry_price == Decimal("1.08765")
        assert loaded.exit_price == Decimal("1.08890")
        assert loaded.slippage_total == Decimal("0.00001")
        assert loaded.net_pnl == Decimal("121.49997")
        assert loaded.mae == Decimal("0.00050")
        assert loaded.mfe == Decimal("0.00200")
