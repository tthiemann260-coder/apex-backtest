"""
data_handler.py — Sequential bar-by-bar data ingestion for apex-backtest.

Uses yield-generator pattern: one MarketEvent per next() call.
Structurally prevents look-ahead bias — no future data accessible.

All float prices are converted to Decimal via string constructor at ingestion.
Zero-volume bars are silently skipped (unless they are synthetic gap-fill bars).

Supports: CSV files, yfinance (US stocks), Alpha Vantage (Forex).
Caches fetched data as Parquet for offline re-runs.
Gap handling, adjusted prices, multi-symbol alignment.
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

# Synthetic volume for forward-filled bars (not rejected by null-volume filter)
_FILL_VOLUME: int = 1


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
        fill_gaps: bool = False,
        use_adjusted: bool = False,
    ) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._csv_path = Path(csv_path) if csv_path else None
        self._source = source
        self._start_date = start_date
        self._end_date = end_date
        self._cache_dir = Path(cache_dir)
        self._force_refresh = force_refresh
        self._fill_gaps = fill_gaps
        self._use_adjusted = use_adjusted
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

    # ------------------------------------------------------------------
    # Data transformations
    # ------------------------------------------------------------------

    def _apply_adjusted_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Replace OHLC with split/dividend-adjusted values (DATA-07).

        Adjustment ratio = Adj Close / Close, applied to O, H, L, C.
        """
        if "Adj Close" not in df.columns:
            return df
        if df.empty:
            return df

        df = df.copy()
        ratio = df["Adj Close"] / df["Close"]
        df["Open"] = df["Open"] * ratio
        df["High"] = df["High"] * ratio
        df["Low"] = df["Low"] * ratio
        df["Close"] = df["Adj Close"]
        df = df.drop(columns=["Adj Close"])
        return df

    def _forward_fill_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill date gaps with synthetic bars using last known close (DATA-06).

        Forward-filled bars have:
        - OHLC all set to last known Close
        - Volume set to _FILL_VOLUME (1) — not rejected by null-volume filter
        """
        if df.empty:
            return df

        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date")

        # Create complete daily date range (all calendar days between min and max)
        full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
        df = df.reindex(full_range)

        # Forward-fill prices (OHLC get last known Close for filled bars)
        # First, mark which rows are gap-fills
        is_fill = df["Volume"].isna()

        # Forward-fill Close first, then use it for OHLC of gap bars
        df["Close"] = df["Close"].ffill()
        df.loc[is_fill, "Open"] = df.loc[is_fill, "Close"]
        df.loc[is_fill, "High"] = df.loc[is_fill, "Close"]
        df.loc[is_fill, "Low"] = df.loc[is_fill, "Close"]
        df.loc[is_fill, "Volume"] = _FILL_VOLUME

        # Forward-fill remaining OHLC for real bars that might have NaN
        df[["Open", "High", "Low"]] = df[["Open", "High", "Low"]].ffill()

        df = df.reset_index().rename(columns={"index": "Date"})
        return df

    # ------------------------------------------------------------------
    # Data pipeline
    # ------------------------------------------------------------------

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

        # Apply adjusted prices if requested (DATA-07)
        if self._use_adjusted:
            df = self._apply_adjusted_prices(df)

        # Apply gap filling if requested (DATA-06)
        if self._fill_gaps:
            df = self._forward_fill_gaps(df)

        # Apply date range filter
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

            # DATA-08: reject null-volume bars (real zero-volume, not gap-fill)
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

    # ------------------------------------------------------------------
    # Multi-symbol alignment (DATA-09)
    # ------------------------------------------------------------------

    @staticmethod
    def align_multi_symbol(
        handlers: list[DataHandler],
    ) -> dict[str, Generator[MarketEvent, None, None]]:
        """Align multiple DataHandlers to a common date index.

        Loads all DataFrames, finds the union of all dates, forward-fills
        missing dates per symbol, and returns a dict of generators.

        Each generator yields bars with matching timestamps across symbols.
        """
        # Load all DataFrames
        dfs: dict[str, pd.DataFrame] = {}
        for h in handlers:
            df = h._load_data()
            df = df.copy()
            df["Date"] = pd.to_datetime(df["Date"])
            dfs[h.symbol] = df

        # Build union of all dates
        all_dates: set[pd.Timestamp] = set()
        for df in dfs.values():
            all_dates.update(df["Date"].tolist())
        sorted_dates = sorted(all_dates)

        if not sorted_dates:
            return {h.symbol: iter([]) for h in handlers}

        # Align each symbol to the full date index
        aligned_dfs: dict[str, pd.DataFrame] = {}
        for symbol, df in dfs.items():
            df = df.set_index("Date")
            full_idx = pd.DatetimeIndex(sorted_dates)
            df = df.reindex(full_idx)

            # Forward-fill gaps
            is_fill = df["Volume"].isna()
            df["Close"] = df["Close"].ffill()
            df.loc[is_fill, "Open"] = df.loc[is_fill, "Close"]
            df.loc[is_fill, "High"] = df.loc[is_fill, "Close"]
            df.loc[is_fill, "Low"] = df.loc[is_fill, "Close"]
            df.loc[is_fill, "Volume"] = _FILL_VOLUME
            df[["Open", "High", "Low"]] = df[["Open", "High", "Low"]].ffill()

            # Drop rows that are still NaN (dates before this symbol's first bar)
            df = df.dropna(subset=["Close"])

            df = df.reset_index().rename(columns={"index": "Date"})
            aligned_dfs[symbol] = df

        def _make_generator(
            sym: str, df: pd.DataFrame, tf: str,
        ) -> Generator[MarketEvent, None, None]:
            for _, row in df.iterrows():
                volume = int(row["Volume"])
                if volume == 0:
                    continue
                yield MarketEvent(
                    symbol=sym,
                    timestamp=pd.Timestamp(row["Date"]).to_pydatetime(),
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=volume,
                    timeframe=tf,
                )

        result: dict[str, Generator[MarketEvent, None, None]] = {}
        for h in handlers:
            if h.symbol in aligned_dfs:
                result[h.symbol] = _make_generator(
                    h.symbol, aligned_dfs[h.symbol], h.timeframe,
                )
        return result
