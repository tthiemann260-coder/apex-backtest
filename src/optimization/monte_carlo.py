"""
monte_carlo.py — Monte Carlo Trade Shuffling (OPT-03).

Shuffles the PnL sequence of completed trades (NOT bar prices) to assess
whether the strategy's equity curve is statistically significant or just
a result of lucky trade ordering.

Key outputs:
- p5/p50/p95 of final equity across permutations
- p5/p50/p95 of max drawdown across permutations
- Original vs shuffled comparison

IMPORTANT: Only trade PnLs are shuffled, never bar prices. This preserves
market microstructure while testing the independence of trade outcomes.

Requirement: OPT-03
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class MCPermutation:
    """Single Monte Carlo permutation result."""
    final_equity: float
    max_drawdown_pct: float


@dataclass
class MCResult:
    """Aggregate Monte Carlo simulation results."""
    n_permutations: int = 0
    n_trades: int = 0
    original_final_equity: float = 0.0
    original_max_dd_pct: float = 0.0
    p5_equity: float = 0.0
    p50_equity: float = 0.0
    p95_equity: float = 0.0
    p5_max_dd: float = 0.0
    p50_max_dd: float = 0.0
    p95_max_dd: float = 0.0
    equity_percentile: float = 0.0  # Where original falls in distribution
    permutations: list[MCPermutation] = field(default_factory=list)


def _pair_fills_to_pnls(
    fill_log: list,
    initial_equity: Decimal,
) -> tuple[list[Decimal], Decimal]:
    """Extract per-trade PnLs from fill log.

    Returns (pnl_list, final_equity).
    """
    from src.events import OrderSide

    pnls: list[Decimal] = []
    open_fill = None

    for fill in fill_log:
        if open_fill is None:
            open_fill = fill
        else:
            # Pair: entry and exit
            if fill.side != open_fill.side:
                if open_fill.side == OrderSide.BUY:
                    pnl = (fill.fill_price - open_fill.fill_price) * open_fill.quantity
                else:
                    pnl = (open_fill.fill_price - fill.fill_price) * open_fill.quantity
                # Subtract friction
                pnl -= (open_fill.commission + open_fill.slippage + open_fill.spread_cost)
                pnl -= (fill.commission + fill.slippage + fill.spread_cost)
                pnls.append(pnl)
                open_fill = None
            else:
                open_fill = fill

    # Compute final equity from PnLs
    equity = initial_equity
    for pnl in pnls:
        equity += pnl

    return pnls, equity


def _simulate_equity_curve(
    pnls: list[float],
    initial_equity: float,
) -> tuple[float, float]:
    """Simulate equity curve from PnL sequence.

    Returns (final_equity, max_drawdown_pct).
    """
    equity = initial_equity
    peak = equity
    max_dd_pct = 0.0

    for pnl in pnls:
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            dd_pct = (peak - equity) / peak * 100.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    return equity, max_dd_pct


def run_monte_carlo(
    fill_log: list,
    initial_equity: Decimal = Decimal("10000"),
    n_permutations: int = 1000,
    seed: Optional[int] = None,
) -> MCResult:
    """Run Monte Carlo trade shuffling simulation.

    Parameters
    ----------
    fill_log : list[FillEvent]
        List of fill events from a backtest.
    initial_equity : Decimal
        Starting equity.
    n_permutations : int
        Number of random permutations. Default: 1000.
    seed : Optional[int]
        Random seed for reproducibility.

    Returns
    -------
    MCResult
        Percentile statistics and permutation details.
    """
    if seed is not None:
        random.seed(seed)

    # Extract trade PnLs
    pnls_decimal, original_equity = _pair_fills_to_pnls(fill_log, initial_equity)
    pnls_float = [float(p) for p in pnls_decimal]
    init_eq_float = float(initial_equity)

    n_trades = len(pnls_float)

    if n_trades < 2:
        orig_final = float(original_equity)
        return MCResult(
            n_permutations=0,
            n_trades=n_trades,
            original_final_equity=orig_final,
            original_max_dd_pct=0.0,
            p5_equity=orig_final,
            p50_equity=orig_final,
            p95_equity=orig_final,
        )

    # Original equity curve
    orig_final, orig_dd = _simulate_equity_curve(pnls_float, init_eq_float)

    # Run permutations
    permutations: list[MCPermutation] = []
    for _ in range(n_permutations):
        shuffled = list(pnls_float)
        random.shuffle(shuffled)
        final_eq, max_dd = _simulate_equity_curve(shuffled, init_eq_float)
        permutations.append(MCPermutation(
            final_equity=final_eq,
            max_drawdown_pct=max_dd,
        ))

    # Sort for percentile calculation
    equities = sorted(p.final_equity for p in permutations)
    drawdowns = sorted(p.max_drawdown_pct for p in permutations)

    def percentile(data: list[float], pct: float) -> float:
        idx = int(len(data) * pct / 100.0)
        idx = max(0, min(idx, len(data) - 1))
        return data[idx]

    # Where does original fall in the distribution?
    eq_rank = sum(1 for e in equities if e <= orig_final)
    equity_pctile = eq_rank / len(equities) * 100.0

    return MCResult(
        n_permutations=n_permutations,
        n_trades=n_trades,
        original_final_equity=orig_final,
        original_max_dd_pct=orig_dd,
        p5_equity=percentile(equities, 5),
        p50_equity=percentile(equities, 50),
        p95_equity=percentile(equities, 95),
        p5_max_dd=percentile(drawdowns, 5),
        p50_max_dd=percentile(drawdowns, 50),
        p95_max_dd=percentile(drawdowns, 95),
        equity_percentile=equity_pctile,
        permutations=permutations,
    )
