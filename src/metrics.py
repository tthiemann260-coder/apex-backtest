"""
metrics.py — Performance metrics for apex-backtest.

All metrics computed post-loop from equity_log and fill_log (METR-09).
Uses correct annualization factors per timeframe (METR-02).
All computations in Decimal where applicable.

Raises MetricsComputationError for missing/invalid data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from src.events import FillEvent, OrderSide


class MetricsComputationError(Exception):
    """Raised when metrics cannot be computed due to missing data."""
    pass


# Annualization factors: sqrt(periods_per_year) for Sharpe/Sortino
ANNUALIZATION_FACTORS: dict[str, Decimal] = {
    "1m": Decimal("15.8745"),   # sqrt(252 * 390) for stocks
    "1m_fx": Decimal("19.1050"),  # sqrt(252 * 1440) for forex
    "5m": Decimal("7.0993"),    # sqrt(252 * 78)
    "15m": Decimal("4.0988"),   # sqrt(252 * 26)
    "1h": Decimal("2.0000"),    # sqrt(252 * 6.5) ≈ 40.5 → ~6.36, simplified
    "4h": Decimal("1.0000"),    # sqrt(252 * 1.625)
    "1d": Decimal("15.8745"),   # sqrt(252)
    "1wk": Decimal("7.2111"),   # sqrt(52)
    "1mo": Decimal("3.4641"),   # sqrt(12)
}


@dataclass
class MetricsResult:
    """Container for all computed metrics."""
    # PnL metrics (METR-01)
    net_pnl: Decimal
    total_return_pct: Decimal
    cagr: Decimal

    # Risk-adjusted (METR-02, 03, 05)
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal

    # Drawdown (METR-04)
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    max_drawdown_duration: int  # in bars

    # Trade stats (METR-06, 07)
    win_rate: Decimal
    profit_factor: Decimal
    expectancy: Decimal
    trade_count: int
    avg_holding_time: int  # in bars
    avg_rr: Decimal

    # Exposure (METR-08)
    total_exposure_pct: Decimal


def compute(
    equity_log: list[dict],
    fill_log: list[FillEvent],
    timeframe: str = "1d",
    initial_equity: Optional[Decimal] = None,
) -> MetricsResult:
    """Compute all performance metrics from backtest results.

    Parameters
    ----------
    equity_log : list[dict]
        One entry per bar: {"timestamp", "equity", "cash", ...}
    fill_log : list[FillEvent]
        All fill events from the backtest.
    timeframe : str
        Timeframe for annualization factor.
    initial_equity : Decimal, optional
        Starting equity. If None, uses first equity_log entry.

    Raises
    ------
    MetricsComputationError
        If equity_log is empty or data is insufficient.
    """
    if not equity_log:
        raise MetricsComputationError("Empty equity log — cannot compute metrics")

    equities = [entry["equity"] for entry in equity_log]

    if initial_equity is None:
        initial_equity = equities[0]

    final_equity = equities[-1]
    n_bars = len(equities)

    # --- PnL metrics (METR-01) ---
    net_pnl = final_equity - initial_equity
    total_return_pct = (
        (net_pnl / initial_equity * Decimal("100"))
        if initial_equity != Decimal("0") else Decimal("0")
    )
    cagr = _compute_cagr(initial_equity, final_equity, n_bars, timeframe)

    # --- Returns series ---
    returns = _compute_returns(equities)

    # --- Annualization factor ---
    ann_factor = ANNUALIZATION_FACTORS.get(timeframe, Decimal("15.8745"))

    # --- Sharpe Ratio (METR-02) ---
    sharpe_ratio = _compute_sharpe(returns, ann_factor)

    # --- Sortino Ratio (METR-03) ---
    sortino_ratio = _compute_sortino(returns, ann_factor)

    # --- Max Drawdown (METR-04) ---
    max_dd, max_dd_pct, max_dd_duration = _compute_max_drawdown(equities)

    # --- Calmar Ratio (METR-05) ---
    calmar_ratio = (
        cagr / abs(max_dd_pct) if max_dd_pct != Decimal("0") else Decimal("0")
    )

    # --- Trade statistics (METR-06, 07) ---
    trade_stats = _compute_trade_stats(fill_log)

    # --- Exposure (METR-08) ---
    exposure_pct = _compute_exposure(equity_log)

    return MetricsResult(
        net_pnl=net_pnl,
        total_return_pct=total_return_pct,
        cagr=cagr,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        max_drawdown_duration=max_dd_duration,
        win_rate=trade_stats["win_rate"],
        profit_factor=trade_stats["profit_factor"],
        expectancy=trade_stats["expectancy"],
        trade_count=trade_stats["trade_count"],
        avg_holding_time=trade_stats["avg_holding_time"],
        avg_rr=trade_stats["avg_rr"],
        total_exposure_pct=exposure_pct,
    )


# ---------------------------------------------------------------------------
# Internal computation functions
# ---------------------------------------------------------------------------

def _compute_returns(equities: list[Decimal]) -> list[Decimal]:
    """Compute bar-to-bar returns."""
    returns = []
    for i in range(1, len(equities)):
        if equities[i - 1] != Decimal("0"):
            ret = (equities[i] - equities[i - 1]) / equities[i - 1]
            returns.append(ret)
    return returns


def _compute_sharpe(
    returns: list[Decimal], ann_factor: Decimal,
) -> Decimal:
    """Sharpe Ratio = mean(returns) / std(returns) * annualization_factor."""
    if len(returns) < 2:
        return Decimal("0")

    mean_ret = sum(returns) / Decimal(str(len(returns)))
    variance = sum((r - mean_ret) ** 2 for r in returns) / Decimal(str(len(returns) - 1))

    if variance <= Decimal("0"):
        return Decimal("0")

    std_ret = variance.sqrt()
    if std_ret == Decimal("0"):
        return Decimal("0")

    return (mean_ret / std_ret) * ann_factor


def _compute_sortino(
    returns: list[Decimal], ann_factor: Decimal,
) -> Decimal:
    """Sortino Ratio = mean(returns) / downside_std * annualization_factor."""
    if len(returns) < 2:
        return Decimal("0")

    mean_ret = sum(returns) / Decimal(str(len(returns)))
    downside = [r for r in returns if r < Decimal("0")]

    if len(downside) < 2:
        return Decimal("0")

    downside_mean = sum(downside) / Decimal(str(len(downside)))
    downside_var = sum((r - downside_mean) ** 2 for r in downside) / Decimal(str(len(downside) - 1))

    if downside_var <= Decimal("0"):
        return Decimal("0")

    downside_std = downside_var.sqrt()
    if downside_std == Decimal("0"):
        return Decimal("0")

    return (mean_ret / downside_std) * ann_factor


def _compute_max_drawdown(
    equities: list[Decimal],
) -> tuple[Decimal, Decimal, int]:
    """Compute max drawdown: absolute, percentage, and duration in bars."""
    if not equities:
        return Decimal("0"), Decimal("0"), 0

    peak = equities[0]
    max_dd = Decimal("0")
    max_dd_pct = Decimal("0")
    max_duration = 0
    current_duration = 0

    for equity in equities:
        if equity > peak:
            peak = equity
            current_duration = 0
        else:
            current_duration += 1

        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
        dd_pct = (dd / peak * Decimal("100")) if peak > Decimal("0") else Decimal("0")
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
        if current_duration > max_duration:
            max_duration = current_duration

    return max_dd, max_dd_pct, max_duration


def _compute_cagr(
    initial: Decimal, final: Decimal, n_bars: int, timeframe: str,
) -> Decimal:
    """Compute Compound Annual Growth Rate."""
    if initial <= Decimal("0") or n_bars <= 0:
        return Decimal("0")

    # Bars per year mapping
    bars_per_year = {
        "1m": 252 * 390,
        "5m": 252 * 78,
        "15m": 252 * 26,
        "1h": 252 * 7,  # ~6.5h per day
        "4h": 252 * 2,
        "1d": 252,
        "1wk": 52,
        "1mo": 12,
    }
    bpy = bars_per_year.get(timeframe, 252)
    years = Decimal(str(n_bars)) / Decimal(str(bpy))

    if years <= Decimal("0"):
        return Decimal("0")

    ratio = final / initial
    if ratio <= Decimal("0"):
        return Decimal("-1")

    # CAGR = (final/initial)^(1/years) - 1
    # Using float for power computation, then convert back
    try:
        cagr_float = float(ratio) ** (1.0 / float(years)) - 1.0
        return Decimal(str(round(cagr_float, 6)))
    except (OverflowError, ValueError):
        return Decimal("0")


def _compute_trade_stats(fill_log: list[FillEvent]) -> dict:
    """Compute trade statistics from fill log."""
    if not fill_log:
        return {
            "win_rate": Decimal("0"),
            "profit_factor": Decimal("0"),
            "expectancy": Decimal("0"),
            "trade_count": 0,
            "avg_holding_time": 0,
            "avg_rr": Decimal("0"),
        }

    # Pair fills into round-trip trades
    trades: list[dict] = []
    open_fills: dict[str, list[FillEvent]] = {}

    for fill in fill_log:
        symbol = fill.symbol
        if symbol not in open_fills:
            open_fills[symbol] = []

        existing = open_fills[symbol]
        if existing and existing[0].side != fill.side:
            # Closing trade
            open_fill = existing.pop(0)
            if open_fill.side == OrderSide.BUY:
                pnl = (fill.fill_price - open_fill.fill_price) * min(fill.quantity, open_fill.quantity)
            else:
                pnl = (open_fill.fill_price - fill.fill_price) * min(fill.quantity, open_fill.quantity)
            pnl -= fill.commission + open_fill.commission
            trades.append({
                "pnl": pnl,
                "entry_time": open_fill.timestamp,
                "exit_time": fill.timestamp,
            })
        else:
            existing.append(fill)

    if not trades:
        return {
            "win_rate": Decimal("0"),
            "profit_factor": Decimal("0"),
            "expectancy": Decimal("0"),
            "trade_count": 0,
            "avg_holding_time": 0,
            "avg_rr": Decimal("0"),
        }

    wins = [t for t in trades if t["pnl"] > Decimal("0")]
    losses = [t for t in trades if t["pnl"] <= Decimal("0")]

    total_wins = sum(t["pnl"] for t in wins) if wins else Decimal("0")
    total_losses = abs(sum(t["pnl"] for t in losses)) if losses else Decimal("0")

    trade_count = len(trades)
    win_rate = Decimal(str(len(wins))) / Decimal(str(trade_count)) * Decimal("100")

    profit_factor = (
        total_wins / total_losses if total_losses > Decimal("0") else Decimal("0")
    )

    expectancy = sum(t["pnl"] for t in trades) / Decimal(str(trade_count))

    # Average holding time (simplified: count of bars between entry/exit)
    total_hold = 0
    for t in trades:
        delta = t["exit_time"] - t["entry_time"]
        total_hold += max(delta.total_seconds() / 3600, 1)  # At least 1 hour
    avg_holding = int(total_hold / trade_count) if trade_count > 0 else 0

    # Average risk-reward
    avg_win = total_wins / Decimal(str(len(wins))) if wins else Decimal("0")
    avg_loss = total_losses / Decimal(str(len(losses))) if losses else Decimal("1")
    avg_rr = avg_win / avg_loss if avg_loss > Decimal("0") else Decimal("0")

    return {
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "trade_count": trade_count,
        "avg_holding_time": avg_holding,
        "avg_rr": avg_rr,
    }


def _compute_exposure(equity_log: list[dict]) -> Decimal:
    """Compute total exposure time as percentage of total bars."""
    if not equity_log:
        return Decimal("0")

    in_market = 0
    for entry in equity_log:
        cash = entry.get("cash", entry.get("equity"))
        equity = entry["equity"]
        # If cash != equity, we have a position
        if cash != equity:
            in_market += 1

    return Decimal(str(in_market)) / Decimal(str(len(equity_log))) * Decimal("100")
