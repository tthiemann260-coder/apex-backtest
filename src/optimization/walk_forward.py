"""
walk_forward.py — Rolling Walk-Forward Validation (OPT-01).

Splits historical data into rolling train/test windows, runs a backtest
on each window, and measures out-of-sample (OOS) performance.

Key design:
- Fresh strategy + engine per window (no state leakage)
- Warmup period inside training window (first N bars ignored for signals)
- Efficiency ratio = OOS_Sharpe / IS_Sharpe per window

Requirement: OPT-01
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.data_handler import DataHandler
from src.engine import create_engine, BacktestResult
from src.events import MarketEvent
from src.metrics import compute as compute_metrics, MetricsResult


@dataclass(frozen=True)
class WFOWindow:
    """Results for a single walk-forward window."""
    window_idx: int
    train_bars: int
    test_bars: int
    is_sharpe: float
    oos_sharpe: float
    is_return: float
    oos_return: float
    efficiency: float  # OOS Sharpe / IS Sharpe (capped)


@dataclass
class WFOResult:
    """Aggregate walk-forward validation results."""
    windows: list[WFOWindow] = field(default_factory=list)
    mean_oos_sharpe: float = 0.0
    mean_efficiency: float = 0.0
    total_oos_bars: int = 0


class _BarSliceHandler:
    """Lightweight bar feeder that streams pre-loaded MarketEvents.

    This avoids re-loading CSV/API data for each walk-forward window.
    Compatible with BacktestEngine which expects .stream_bars() generator.
    """

    def __init__(self, bars: list[MarketEvent], symbol: str, timeframe: str) -> None:
        self._bars = bars
        self._symbol = symbol
        self._timeframe = timeframe

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def timeframe(self) -> str:
        return self._timeframe

    def stream_bars(self):
        for bar in self._bars:
            yield bar


def _load_all_bars(
    symbol: str,
    timeframe: str,
    csv_path: Optional[str] = None,
    source: str = "csv",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[MarketEvent]:
    """Load all bars into memory for slicing."""
    dh = DataHandler(
        symbol=symbol,
        timeframe=timeframe,
        csv_path=csv_path,
        source=source,
        start_date=start_date,
        end_date=end_date,
    )
    return list(dh.stream_bars())


def _import_strategy_class(strategy_name: str):
    """Dynamically import a strategy class."""
    from src.dashboard.callbacks import STRATEGY_MAP
    module_path, class_name = STRATEGY_MAP[strategy_name]
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _run_on_slice(
    bars: list[MarketEvent],
    strategy_cls,
    symbol: str,
    timeframe: str,
    params: Optional[dict] = None,
    initial_cash: Decimal = Decimal("10000"),
) -> tuple[BacktestResult, MetricsResult]:
    """Run a backtest on a bar slice with a fresh strategy + engine."""
    strategy = strategy_cls(symbol=symbol, timeframe=timeframe, params=params)
    handler = _BarSliceHandler(bars, symbol, timeframe)
    engine = create_engine(
        data_handler=handler,
        strategy=strategy,
        initial_cash=initial_cash,
    )
    result = engine.run()
    metrics = compute_metrics(
        equity_log=result.equity_log,
        fill_log=result.fill_log,
        timeframe=timeframe,
    )
    return result, metrics


def run_walk_forward(
    symbol: str,
    strategy_name: str,
    timeframe: str = "1d",
    train_bars: int = 252,
    test_bars: int = 63,
    step_bars: Optional[int] = None,
    params: Optional[dict] = None,
    csv_path: Optional[str] = None,
    source: str = "csv",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    initial_cash: Decimal = Decimal("10000"),
) -> WFOResult:
    """Run rolling walk-forward optimization.

    Parameters
    ----------
    symbol : str
        Instrument symbol.
    strategy_name : str
        Strategy name (key in STRATEGY_MAP).
    timeframe : str
        Bar timeframe.
    train_bars : int
        Number of bars in each training window. Default: 252 (1 year daily).
    test_bars : int
        Number of bars in each test window. Default: 63 (~3 months daily).
    step_bars : Optional[int]
        Step size for sliding window. Default: test_bars.
    params : Optional[dict]
        Strategy parameters.
    csv_path, source, start_date, end_date : str
        DataHandler parameters.
    initial_cash : Decimal
        Initial portfolio cash.

    Returns
    -------
    WFOResult
        Aggregate walk-forward results with per-window details.
    """
    if step_bars is None:
        step_bars = test_bars

    all_bars = _load_all_bars(
        symbol, timeframe, csv_path, source, start_date, end_date,
    )

    strategy_cls = _import_strategy_class(strategy_name)

    windows: list[WFOWindow] = []
    window_start = 0
    window_idx = 0

    while window_start + train_bars + test_bars <= len(all_bars):
        train_slice = all_bars[window_start: window_start + train_bars]
        test_start = window_start + train_bars
        test_slice = all_bars[test_start: test_start + test_bars]

        # Run IS (in-sample) on training window
        _, is_metrics = _run_on_slice(
            train_slice, strategy_cls, symbol, timeframe, params, initial_cash,
        )

        # Run OOS (out-of-sample) on test window
        _, oos_metrics = _run_on_slice(
            test_slice, strategy_cls, symbol, timeframe, params, initial_cash,
        )

        is_sharpe = float(is_metrics.sharpe_ratio)
        oos_sharpe = float(oos_metrics.sharpe_ratio)
        is_ret = float(is_metrics.total_return_pct)
        oos_ret = float(oos_metrics.total_return_pct)

        # Efficiency: OOS / IS (handle division by zero)
        if abs(is_sharpe) > 1e-10:
            efficiency = oos_sharpe / is_sharpe
        else:
            efficiency = 0.0

        # Cap extreme values
        efficiency = max(-5.0, min(5.0, efficiency))

        windows.append(WFOWindow(
            window_idx=window_idx,
            train_bars=len(train_slice),
            test_bars=len(test_slice),
            is_sharpe=is_sharpe,
            oos_sharpe=oos_sharpe,
            is_return=is_ret,
            oos_return=oos_ret,
            efficiency=efficiency,
        ))

        window_start += step_bars
        window_idx += 1

    # Aggregate
    if windows:
        mean_oos = sum(w.oos_sharpe for w in windows) / len(windows)
        mean_eff = sum(w.efficiency for w in windows) / len(windows)
        total_oos = sum(w.test_bars for w in windows)
    else:
        mean_oos = 0.0
        mean_eff = 0.0
        total_oos = 0

    return WFOResult(
        windows=windows,
        mean_oos_sharpe=mean_oos,
        mean_efficiency=mean_eff,
        total_oos_bars=total_oos,
    )
