"""
data_handler.py — Sequential bar-by-bar data ingestion for apex-backtest.

Uses yield-generator pattern: one MarketEvent per next() call.
Structurally prevents look-ahead bias — no future data accessible.

All float prices are converted to Decimal via string constructor at ingestion.
Zero-volume bars are silently skipped.

Supports: CSV files, yfinance (US stocks), Alpha Vantage (Forex).
Caches fetched data as Parquet for offline re-runs.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Generator, Optional

import pandas as pd
import yfinance as yf

from src.events import MarketEvent


# ---------------------------------------------------------------------------
# Timeframe mapping for yfinance interval parameter
# ---------------------------------------------------------------------------

_YF_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "1h",  # yfinance has no 4h — fetch 1h and resample later
    "1d": "1d",
    "1wk": "1wk",
    "1mo": "1mo",
}


class DataHandler:
    """Sequential data ingestion via yield-generator.

    Feeds MarketEvents into the event pipeline one bar at a time.
    The generator pattern structurally prevents look-ahead bias:
    calling next() advances exactly one bar forward.

    All float prices are converted to Decimal(str(value)) at yield time.
    Bars with volume == 0 are silently skipped (DATA-08).
    """

    def __init__(
        self,
        symbol: str,
        timeframe: str = "1d",
        csv_path: Optional[str | Path] = None,
        source: str = "csv",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        cache_dir: str | Path = "data",
        force_refresh: bool = False,
    ) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._csv_path = Path(csv_path) if csv_path else None
        self._source = source
        self._start_date = start_date
        self._end_date = end_date
        self._cache_dir = Path(cache_dir)
        self._force_refresh = force_refresh
        self._df: Optional[pd.DataFrame] = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    @property
    def _cache_path(self) -> Path:
        """Parquet cache file path: {cache_dir}/{symbol}_{timeframe}.parquet"""
        return self._cache_dir / f"{self._symbol}_{self._timeframe}.parquet"

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_csv(self) -> pd.DataFrame:
        """Load CSV file into DataFrame, sorted by Date ascending."""
        if self._csv_path is None:
            raise ValueError(
                "No data source configured — provide csv_path or use source='yfinance'"
            )
        if not self._csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._csv_path}")

        df = pd.read_csv(self._csv_path, parse_dates=["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df

    def _fetch_yfinance(self) -> pd.DataFrame:
        """Fetch OHLCV data from Yahoo Finance."""
        interval = _YF_INTERVAL_MAP.get(self._timeframe, "1d")
        df = yf.download(
            tickers=self._symbol,
            start=self._start_date,
            end=self._end_date,
            interval=interval,
            progress=False,
            auto_adjust=False,
        )
        if df.empty:
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

        # yfinance returns DatetimeIndex — move to column
        df = df.reset_index()
        # Handle MultiIndex columns from newer yfinance versions
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] if col[1] == "" else col[0] for col in df.columns]
        # Normalize date column name
        date_col = "Date" if "Date" in df.columns else "Datetime"
        if date_col != "Date":
            df = df.rename(columns={date_col: "Date"})

        # Keep standard columns
        keep_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        if "Adj Close" in df.columns:
            keep_cols.append("Adj Close")
        df = df[[c for c in keep_cols if c in df.columns]]
        df = df.sort_values("Date").reset_index(drop=True)
        return df

    def _load_from_cache(self) -> Optional[pd.DataFrame]:
        """Load from Parquet cache if it exists."""
        if self._cache_path.exists() and not self._force_refresh:
            df = pd.read_parquet(self._cache_path)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
            return df
        return None

    def _save_to_cache(self, df: pd.DataFrame) -> None:
        """Save DataFrame to Parquet cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self._cache_path, index=False)

    def _load_data(self) -> pd.DataFrame:
        """Load data from configured source with Parquet caching."""
        if self._df is not None:
            return self._df

        if self._source == "csv":
            df = self._load_csv()
        elif self._source == "yfinance":
            # Check cache first
            cached = self._load_from_cache()
            if cached is not None:
                df = cached
            else:
                df = self._fetch_yfinance()
                if not df.empty:
                    self._save_to_cache(df)
        else:
            raise ValueError(f"Unknown source: {self._source!r}")

        # Apply date range filter (for CSV source or cached data)
        if self._start_date and "Date" in df.columns and not df.empty:
            df = df[df["Date"] >= pd.Timestamp(self._start_date)]
        if self._end_date and "Date" in df.columns and not df.empty:
            df = df[df["Date"] <= pd.Timestamp(self._end_date)]

        df = df.reset_index(drop=True)
        self._df = df
        return self._df

    # ------------------------------------------------------------------
    # Bar streaming
    # ------------------------------------------------------------------

    def stream_bars(self) -> Generator[MarketEvent, None, None]:
        """Yield MarketEvents one at a time, chronologically.

        - Converts all prices to Decimal via string constructor (DATA-02)
        - Skips bars with volume == 0 (DATA-08)
        - Yields in Date-ascending order (DATA-01)
        """
        df = self._load_data()

        for _, row in df.iterrows():
            volume = int(row["Volume"])

            # DATA-08: reject null-volume bars
            if volume == 0:
                continue

            yield MarketEvent(
                symbol=self._symbol,
                timestamp=pd.Timestamp(row["Date"]).to_pydatetime(),
                open=Decimal(str(row["Open"])),
                high=Decimal(str(row["High"])),
                low=Decimal(str(row["Low"])),
                close=Decimal(str(row["Close"])),
                volume=volume,
                timeframe=self._timeframe,
            )
