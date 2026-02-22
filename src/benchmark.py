"""
benchmark.py — Benchmark Comparison + Alpha/Beta/IR (PORT-12, PORT-13).

Computes buy-and-hold benchmark equity curve and relative performance
metrics (Alpha, Beta, Information Ratio).

Design:
- Benchmark is a simple buy-and-hold on the same instrument
- Alpha = strategy_return - beta * benchmark_return
- Beta = covariance(strategy, benchmark) / variance(benchmark)
- Information Ratio = active_return / tracking_error
- All returns computed from equity log sequences

Requirement: PORT-12, PORT-13
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from src.events import MarketEvent


@dataclass(frozen=True)
class BenchmarkMetrics:
    """Benchmark comparison metrics."""
    # Benchmark performance
    benchmark_return_pct: float
    benchmark_final_equity: float

    # Relative metrics
    alpha: float
    beta: float
    information_ratio: float
    correlation: float

    # Strategy (for reference)
    strategy_return_pct: float


@dataclass
class BenchmarkResult:
    """Complete benchmark comparison data."""
    benchmark_equity: list[dict] = field(default_factory=list)
    metrics: Optional[BenchmarkMetrics] = None


def compute_benchmark_equity(
    bars: list[MarketEvent],
    initial_equity: Decimal = Decimal("10000"),
) -> list[dict]:
    """Compute buy-and-hold equity curve.

    Invests 100% at the first bar's close and holds throughout.
    Returns list of {timestamp, equity} dicts.
    """
    if not bars:
        return []

    entry_price = bars[0].close
    if entry_price <= Decimal("0"):
        return []

    shares = initial_equity / entry_price
    equity_log: list[dict] = []

    for bar in bars:
        equity = shares * bar.close
        equity_log.append({
            "timestamp": bar.timestamp,
            "equity": equity,
        })

    return equity_log


def compute_benchmark_metrics(
    strategy_equity_log: list[dict],
    benchmark_equity_log: list[dict],
    initial_equity: Decimal = Decimal("10000"),
) -> BenchmarkMetrics:
    """Compute Alpha, Beta, Information Ratio from equity curves.

    Parameters
    ----------
    strategy_equity_log : list[dict]
        Strategy equity log (from BacktestResult).
    benchmark_equity_log : list[dict]
        Buy-and-hold equity log (from compute_benchmark_equity).
    initial_equity : Decimal
        Starting equity.

    Returns
    -------
    BenchmarkMetrics
        Alpha, Beta, IR, correlation, returns.
    """
    init_eq = float(initial_equity)

    # Extract equity series
    strat_equities = [float(e["equity"]) for e in strategy_equity_log]
    bench_equities = [float(e["equity"]) for e in benchmark_equity_log]

    # Align lengths
    n = min(len(strat_equities), len(bench_equities))
    if n < 2:
        strat_ret = 0.0
        bench_ret = 0.0
        if strat_equities:
            strat_ret = (strat_equities[-1] / init_eq - 1) * 100
        if bench_equities:
            bench_ret = (bench_equities[-1] / init_eq - 1) * 100
        return BenchmarkMetrics(
            benchmark_return_pct=bench_ret,
            benchmark_final_equity=bench_equities[-1] if bench_equities else init_eq,
            alpha=0.0,
            beta=0.0,
            information_ratio=0.0,
            correlation=0.0,
            strategy_return_pct=strat_ret,
        )

    strat_equities = strat_equities[:n]
    bench_equities = bench_equities[:n]

    # Compute bar-to-bar returns
    strat_returns = [
        (strat_equities[i] / strat_equities[i - 1] - 1)
        for i in range(1, n)
        if strat_equities[i - 1] != 0
    ]
    bench_returns = [
        (bench_equities[i] / bench_equities[i - 1] - 1)
        for i in range(1, n)
        if bench_equities[i - 1] != 0
    ]

    # Align return lengths
    m = min(len(strat_returns), len(bench_returns))
    if m < 2:
        strat_total = (strat_equities[-1] / init_eq - 1) * 100
        bench_total = (bench_equities[-1] / init_eq - 1) * 100
        return BenchmarkMetrics(
            benchmark_return_pct=bench_total,
            benchmark_final_equity=bench_equities[-1],
            alpha=0.0,
            beta=0.0,
            information_ratio=0.0,
            correlation=0.0,
            strategy_return_pct=strat_total,
        )

    strat_returns = strat_returns[:m]
    bench_returns = bench_returns[:m]

    # Statistics
    mean_s = sum(strat_returns) / m
    mean_b = sum(bench_returns) / m

    var_b = sum((r - mean_b) ** 2 for r in bench_returns) / m
    cov_sb = sum(
        (strat_returns[i] - mean_s) * (bench_returns[i] - mean_b)
        for i in range(m)
    ) / m
    var_s = sum((r - mean_s) ** 2 for r in strat_returns) / m

    # Beta
    beta = cov_sb / var_b if abs(var_b) > 1e-20 else 0.0

    # Alpha (annualized daily)
    alpha = (mean_s - beta * mean_b) * 252

    # Correlation
    std_s = var_s ** 0.5 if var_s > 0 else 0.0
    std_b = var_b ** 0.5 if var_b > 0 else 0.0
    correlation = cov_sb / (std_s * std_b) if (std_s * std_b) > 1e-20 else 0.0

    # Active returns and tracking error
    active_returns = [strat_returns[i] - bench_returns[i] for i in range(m)]
    mean_active = sum(active_returns) / m
    tracking_var = sum((r - mean_active) ** 2 for r in active_returns) / m
    tracking_error = tracking_var ** 0.5

    # Information Ratio (annualized)
    information_ratio = (
        (mean_active * (252 ** 0.5)) / tracking_error
        if tracking_error > 1e-20
        else 0.0
    )

    # Total returns
    strat_total_ret = (strat_equities[-1] / init_eq - 1) * 100
    bench_total_ret = (bench_equities[-1] / init_eq - 1) * 100

    return BenchmarkMetrics(
        benchmark_return_pct=bench_total_ret,
        benchmark_final_equity=bench_equities[-1],
        alpha=alpha,
        beta=beta,
        information_ratio=information_ratio,
        correlation=correlation,
        strategy_return_pct=strat_total_ret,
    )
