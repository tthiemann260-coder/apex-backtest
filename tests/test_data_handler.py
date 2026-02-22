"""
test_data_handler.py — Tests for apex-backtest DataHandler.

Covers: yield-generator pattern, Decimal conversion, null-volume rejection,
CSV loading, API fetch (mocked), Parquet caching, multi-symbol support.
Run: pytest tests/test_data_handler.py -v
"""

import pytest
import csv
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd

from src.data_handler import DataHandler
from src.events import MarketEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_test_csv(rows: list[dict], filepath: Path) -> Path:
    """Write CSV with columns: Date,Open,High,Low,Close,Volume."""
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writeheader()
        writer.writerows(rows)
    return filepath


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    """5-bar CSV with realistic OHLCV data."""
    rows = [
        {"Date": "2024-01-15", "Open": "181.50", "High": "183.20", "Low": "180.90", "Close": "182.75", "Volume": "1500000"},
        {"Date": "2024-01-16", "Open": "182.80", "High": "184.10", "Low": "182.00", "Close": "183.50", "Volume": "1200000"},
        {"Date": "2024-01-17", "Open": "183.60", "High": "185.00", "Low": "183.10", "Close": "184.25", "Volume": "1350000"},
        {"Date": "2024-01-18", "Open": "184.30", "High": "186.50", "Low": "184.00", "Close": "186.00", "Volume": "1800000"},
        {"Date": "2024-01-19", "Open": "186.10", "High": "187.30", "Low": "185.50", "Close": "186.80", "Volume": "1100000"},
    ]
    return create_test_csv(rows, tmp_path / "test_5bars.csv")


@pytest.fixture
def csv_with_zero_volume(tmp_path: Path) -> Path:
    """5-bar CSV where bar 3 has volume=0."""
    rows = [
        {"Date": "2024-01-15", "Open": "181.50", "High": "183.20", "Low": "180.90", "Close": "182.75", "Volume": "1500000"},
        {"Date": "2024-01-16", "Open": "182.80", "High": "184.10", "Low": "182.00", "Close": "183.50", "Volume": "1200000"},
        {"Date": "2024-01-17", "Open": "183.60", "High": "185.00", "Low": "183.10", "Close": "184.25", "Volume": "0"},
        {"Date": "2024-01-18", "Open": "184.30", "High": "186.50", "Low": "184.00", "Close": "186.00", "Volume": "1800000"},
        {"Date": "2024-01-19", "Open": "186.10", "High": "187.30", "Low": "185.50", "Close": "186.80", "Volume": "1100000"},
    ]
    return create_test_csv(rows, tmp_path / "test_zero_vol.csv")


@pytest.fixture
def all_zero_volume_csv(tmp_path: Path) -> Path:
    """3-bar CSV where ALL bars have volume=0."""
    rows = [
        {"Date": "2024-01-15", "Open": "100.00", "High": "101.00", "Low": "99.00", "Close": "100.50", "Volume": "0"},
        {"Date": "2024-01-16", "Open": "100.50", "High": "102.00", "Low": "100.00", "Close": "101.00", "Volume": "0"},
        {"Date": "2024-01-17", "Open": "101.00", "High": "103.00", "Low": "100.50", "Close": "102.00", "Volume": "0"},
    ]
    return create_test_csv(rows, tmp_path / "test_all_zero.csv")


@pytest.fixture
def empty_csv(tmp_path: Path) -> Path:
    """CSV with only header row."""
    filepath = tmp_path / "test_empty.csv"
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Open", "High", "Low", "Close", "Volume"])
    return filepath


# ---------------------------------------------------------------------------
# TestDataHandlerGenerator — yield-generator behavior
# ---------------------------------------------------------------------------

class TestDataHandlerGenerator:

    def test_stream_bars_returns_generator(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        gen = handler.stream_bars()
        import types
        assert isinstance(gen, types.GeneratorType)

    def test_stream_bars_yields_market_events(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert isinstance(event, MarketEvent)

    def test_stream_bars_yields_one_at_a_time(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        gen = handler.stream_bars()
        first = next(gen)
        assert isinstance(first, MarketEvent)
        second = next(gen)
        assert isinstance(second, MarketEvent)
        assert first.timestamp != second.timestamp

    def test_stream_bars_chronological_order(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        events = list(handler.stream_bars())
        for i in range(1, len(events)):
            assert events[i].timestamp >= events[i - 1].timestamp

    def test_stream_bars_correct_count(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        events = list(handler.stream_bars())
        assert len(events) == 5

    def test_stream_bars_exhausts_cleanly(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        gen = handler.stream_bars()
        events = list(gen)
        assert len(events) == 5
        with pytest.raises(StopIteration):
            next(gen)


# ---------------------------------------------------------------------------
# TestDecimalConversion — DATA-02
# ---------------------------------------------------------------------------

class TestDecimalConversion:

    def test_open_is_decimal(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert isinstance(event.open, Decimal)

    def test_high_is_decimal(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert isinstance(event.high, Decimal)

    def test_low_is_decimal(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert isinstance(event.low, Decimal)

    def test_close_is_decimal(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert isinstance(event.close, Decimal)

    def test_decimal_precision_preserved(self, sample_csv: Path) -> None:
        """CSV value '181.50' must become exactly Decimal('181.50'), not a float approximation."""
        handler = DataHandler("AAPL", csv_path=sample_csv)
        event = next(handler.stream_bars())
        assert event.open == Decimal("181.50")
        assert event.open != Decimal("181.500000000000014")


# ---------------------------------------------------------------------------
# TestNullVolumeRejection — DATA-08, TEST-05
# ---------------------------------------------------------------------------

class TestNullVolumeRejection:

    def test_zero_volume_bars_skipped(self, csv_with_zero_volume: Path) -> None:
        """5-bar CSV with 1 zero-volume bar yields exactly 4 events."""
        handler = DataHandler("AAPL", csv_path=csv_with_zero_volume)
        events = list(handler.stream_bars())
        assert len(events) == 4

    def test_zero_volume_never_emitted(self, csv_with_zero_volume: Path) -> None:
        handler = DataHandler("AAPL", csv_path=csv_with_zero_volume)
        for event in handler.stream_bars():
            assert event.volume > 0

    def test_all_zero_volume_yields_nothing(self, all_zero_volume_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=all_zero_volume_csv)
        events = list(handler.stream_bars())
        assert len(events) == 0


# ---------------------------------------------------------------------------
# TestCSVLoading — CSV file support
# ---------------------------------------------------------------------------

class TestCSVLoading:

    def test_loads_csv_file(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        events = list(handler.stream_bars())
        assert len(events) > 0

    def test_symbol_set_correctly(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=sample_csv)
        for event in handler.stream_bars():
            assert event.symbol == "AAPL"

    def test_timeframe_set_correctly(self, sample_csv: Path) -> None:
        handler = DataHandler("AAPL", timeframe="1d", csv_path=sample_csv)
        for event in handler.stream_bars():
            assert event.timeframe == "1d"

    def test_empty_csv_yields_nothing(self, empty_csv: Path) -> None:
        handler = DataHandler("AAPL", csv_path=empty_csv)
        events = list(handler.stream_bars())
        assert len(events) == 0

    def test_nonexistent_file_raises(self) -> None:
        handler = DataHandler("AAPL", csv_path="/nonexistent/path.csv")
        with pytest.raises(FileNotFoundError):
            list(handler.stream_bars())


# ---------------------------------------------------------------------------
# Helper: Create mock yfinance DataFrame
# ---------------------------------------------------------------------------

def _mock_yfinance_df() -> pd.DataFrame:
    """Create a DataFrame mimicking yfinance.download() output.

    yfinance returns a DataFrame with a DatetimeIndex named 'Date' (daily)
    or 'Datetime' (intraday).
    """
    dates = pd.date_range("2024-01-15", periods=5, freq="B", name="Date")
    return pd.DataFrame({
        "Open": [181.50, 182.80, 183.60, 184.30, 186.10],
        "High": [183.20, 184.10, 185.00, 186.50, 187.30],
        "Low": [180.90, 182.00, 183.10, 184.00, 185.50],
        "Close": [182.75, 183.50, 184.25, 186.00, 186.80],
        "Adj Close": [181.75, 182.50, 183.25, 185.00, 185.80],
        "Volume": [1500000, 1200000, 1350000, 1800000, 1100000],
    }, index=dates)


# ---------------------------------------------------------------------------
# TestYFinanceFetch — DATA-03 (mocked, no real API calls)
# ---------------------------------------------------------------------------

class TestYFinanceFetch:

    @patch("src.data_handler.yf")
    def test_fetch_yfinance_returns_data(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        events = list(handler.stream_bars())
        assert len(events) == 5
        mock_yf.download.assert_called_once()

    @patch("src.data_handler.yf")
    def test_fetch_yfinance_decimal_conversion(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        event = next(handler.stream_bars())
        assert isinstance(event.open, Decimal)
        assert isinstance(event.close, Decimal)

    @patch("src.data_handler.yf")
    def test_fetch_yfinance_with_date_range(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler(
            "AAPL", source="yfinance",
            start_date="2024-01-15", end_date="2024-01-19",
            cache_dir=tmp_path,
        )
        list(handler.stream_bars())
        call_kwargs = mock_yf.download.call_args
        assert call_kwargs[1]["start"] == "2024-01-15"
        assert call_kwargs[1]["end"] == "2024-01-19"

    @patch("src.data_handler.yf")
    def test_fetch_yfinance_symbol_set(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler("MSFT", source="yfinance", cache_dir=tmp_path)
        event = next(handler.stream_bars())
        assert event.symbol == "MSFT"


# ---------------------------------------------------------------------------
# TestParquetCaching — DATA-04
# ---------------------------------------------------------------------------

class TestParquetCaching:

    @patch("src.data_handler.yf")
    def test_parquet_cache_created_after_fetch(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        list(handler.stream_bars())
        parquet_files = list(tmp_path.glob("*.parquet"))
        assert len(parquet_files) == 1

    @patch("src.data_handler.yf")
    def test_parquet_cache_used_on_second_run(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        # First run — fetches and caches
        h1 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        list(h1.stream_bars())
        assert mock_yf.download.call_count == 1

        # Second run — reads from cache, NO API call
        h2 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        events = list(h2.stream_bars())
        assert mock_yf.download.call_count == 1  # still 1, not 2
        assert len(events) == 5

    @patch("src.data_handler.yf")
    def test_cache_path_includes_symbol_and_timeframe(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        handler = DataHandler("AAPL", timeframe="1d", source="yfinance", cache_dir=tmp_path)
        list(handler.stream_bars())
        parquet_files = list(tmp_path.glob("*.parquet"))
        assert any("AAPL" in f.name and "1d" in f.name for f in parquet_files)

    @patch("src.data_handler.yf")
    def test_force_refresh_re_fetches(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        # First run
        h1 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        list(h1.stream_bars())
        # Second run with force_refresh
        h2 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path, force_refresh=True)
        list(h2.stream_bars())
        assert mock_yf.download.call_count == 2

    @patch("src.data_handler.yf")
    def test_parquet_roundtrip_decimal_precision(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        # Fetch and cache
        h1 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        events_first = list(h1.stream_bars())
        # Read from cache
        h2 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        events_cached = list(h2.stream_bars())
        # Prices must be Decimal after roundtrip
        for e in events_cached:
            assert isinstance(e.open, Decimal)
            assert isinstance(e.close, Decimal)
        # Values must match
        for e1, e2 in zip(events_first, events_cached):
            assert e1.open == e2.open
            assert e1.close == e2.close


# ---------------------------------------------------------------------------
# TestMultiSymbol — DATA-05
# ---------------------------------------------------------------------------

class TestMultiSymbol:

    @patch("src.data_handler.yf")
    def test_multi_symbol_separate_handlers(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        h1 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        h2 = DataHandler("MSFT", source="yfinance", cache_dir=tmp_path)
        e1 = list(h1.stream_bars())
        e2 = list(h2.stream_bars())
        assert all(e.symbol == "AAPL" for e in e1)
        assert all(e.symbol == "MSFT" for e in e2)

    def test_date_range_filter_csv(self, sample_csv: Path) -> None:
        handler = DataHandler(
            "AAPL", csv_path=sample_csv,
            start_date="2024-01-16", end_date="2024-01-18",
        )
        events = list(handler.stream_bars())
        for e in events:
            assert e.timestamp >= datetime(2024, 1, 16)
            assert e.timestamp <= datetime(2024, 1, 18)

    @patch("src.data_handler.yf")
    def test_multi_symbol_independent_generators(self, mock_yf: MagicMock, tmp_path: Path) -> None:
        mock_yf.download.return_value = _mock_yfinance_df()
        h1 = DataHandler("AAPL", source="yfinance", cache_dir=tmp_path)
        h2 = DataHandler("GOOG", source="yfinance", cache_dir=tmp_path)
        gen1 = h1.stream_bars()
        gen2 = h2.stream_bars()
        e1 = next(gen1)
        e2 = next(gen2)
        assert e1.symbol == "AAPL"
        assert e2.symbol == "GOOG"
