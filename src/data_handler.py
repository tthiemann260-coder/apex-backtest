"""
data_handler.py — Sequential bar-by-bar data ingestion for apex-backtest.

Uses yield-generator pattern: one MarketEvent per next() call.
Structurally prevents look-ahead bias — no future data accessible.

All float prices are converted to Decimal via string constructor at ingestion.
Zero-volume bars are silently skipped.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Generator, Optional

import pandas as pd

from src.events import MarketEvent


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
    ) -> None:
        self._symbol = symbol
        self._timeframe = timeframe
        self._csv_path = Path(csv_path) if csv_path else None
        self._df: Optional[pd.DataFrame] = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def _load_csv(self) -> pd.DataFrame:
        """Load CSV file into DataFrame, sorted by Date ascending."""
        if self._csv_path is None:
            raise ValueError(
                "No data source configured — provide csv_path or use fetch()"
            )
        if not self._csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self._csv_path}")

        df = pd.read_csv(self._csv_path, parse_dates=["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df

    def _load_data(self) -> pd.DataFrame:
        """Load data from configured source. Currently supports CSV only."""
        if self._df is not None:
            return self._df
        self._df = self._load_csv()
        return self._df

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
