"""
analytics.py — Advanced analytics computation for apex-backtest Phase 9.

Pure post-processing functions that operate on equity_log and fill_log.
No engine modifications required.

All financial math in Decimal. Convert to float ONLY at visualization boundary.

Requirements covered:
- ADV-01: Monthly Returns Heatmap
- ADV-02: Rolling Sharpe Ratio
- ADV-03: Rolling Drawdown
- ADV-04: Trade Breakdown by Hour
- ADV-05: Trade Breakdown by Weekday
- ADV-06: Trade Breakdown by Session
- ADV-07: MAE Analysis
- ADV-08: MFE Analysis
- ADV-09: Commission Sensitivity Sweep
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.events import FillEvent, OrderSide


# ---------------------------------------------------------------------------
# Session definitions for trade breakdown (ADV-06)
# ---------------------------------------------------------------------------

SESSION_DEFINITIONS = {
    "Pre-Market": (4, 10),     # 04:00 - 09:29
    "Morning": (10, 12),       # 09:30 - 11:59 (approx)
    "Lunch": (12, 14),         # 12:00 - 13:59
    "Afternoon": (14, 16),     # 14:00 - 15:59
    "After-Hours": (16, 20),   # 16:00 - 19:59
}


def _get_session(hour: int) -> str:
    """Map an hour (0-23) to a trading session name."""
    for session_name, (start, end) in SESSION_DEFINITIONS.items():
        if start <= hour < end:
            return session_name
    return "Off-Hours"


# ---------------------------------------------------------------------------
# ADV-01: Monthly Returns
# ---------------------------------------------------------------------------

def compute_monthly_returns(
    equity_log: list[dict],
) -> dict[int, dict[int, Decimal]]:
    """Compute monthly returns from equity log.

    Returns dict[year][month] = return_pct.
    Monthly return = (last_equity_in_month / last_equity_in_prev_month - 1) * 100.
    """
    if not equity_log or len(equity_log) < 2:
        return {}

    # Group equity by (year, month) — keep last entry per month
    monthly_last: dict[tuple[int, int], Decimal] = {}
    for entry in equity_log:
        ts = entry["timestamp"]
        key = (ts.year, ts.month)
        monthly_last[key] = entry["equity"]

    sorted_keys = sorted(monthly_last.keys())
    if len(sorted_keys) < 2:
        return {}

    result: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for i in range(1, len(sorted_keys)):
        prev_key = sorted_keys[i - 1]
        curr_key = sorted_keys[i]
        prev_eq = monthly_last[prev_key]
        curr_eq = monthly_last[curr_key]

        if prev_eq > Decimal("0"):
            ret_pct = (curr_eq - prev_eq) / prev_eq * Decimal("100")
        else:
            ret_pct = Decimal("0")

        year, month = curr_key
        result[year][month] = ret_pct

    return dict(result)


# ---------------------------------------------------------------------------
# ADV-02: Rolling Sharpe Ratio
# ---------------------------------------------------------------------------

def compute_rolling_sharpe(
    equity_log: list[dict],
    window: int = 20,
    timeframe: str = "1d",
) -> list[dict]:
    """Compute rolling Sharpe ratio over a sliding window.

    Returns list of {timestamp, rolling_sharpe}.
    Sharpe = mean(returns) / std(returns) * annualization_factor.
    """
    from src.metrics import ANNUALIZATION_FACTORS

    if len(equity_log) < window + 1:
        return []

    equities = [e["equity"] for e in equity_log]
    timestamps = [e["timestamp"] for e in equity_log]

    # Compute bar-to-bar returns (float for rolling math)
    returns = []
    for i in range(1, len(equities)):
        prev = float(equities[i - 1])
        curr = float(equities[i])
        if prev != 0:
            returns.append(curr / prev - 1.0)
        else:
            returns.append(0.0)

    ann_factor = float(ANNUALIZATION_FACTORS.get(timeframe, Decimal("15.8745")))
    result = []

    for i in range(window - 1, len(returns)):
        window_returns = returns[i - window + 1: i + 1]
        n = len(window_returns)
        mean_r = sum(window_returns) / n
        variance = sum((r - mean_r) ** 2 for r in window_returns) / (n - 1) if n > 1 else 0
        std_r = variance ** 0.5

        if std_r > 0:
            sharpe = (mean_r / std_r) * ann_factor
        else:
            sharpe = 0.0

        result.append({
            "timestamp": timestamps[i + 1],  # +1 because returns are offset by 1
            "rolling_sharpe": sharpe,
        })

    return result


# ---------------------------------------------------------------------------
# ADV-03: Rolling Drawdown
# ---------------------------------------------------------------------------

def compute_rolling_drawdown(
    equity_log: list[dict],
    window: int = 20,
) -> list[dict]:
    """Compute rolling max drawdown over a sliding window.

    Returns list of {timestamp, rolling_drawdown_pct}.
    """
    if len(equity_log) < window:
        return []

    equities = [float(e["equity"]) for e in equity_log]
    timestamps = [e["timestamp"] for e in equity_log]

    result = []
    for i in range(window - 1, len(equities)):
        window_eq = equities[i - window + 1: i + 1]
        peak = window_eq[0]
        max_dd_pct = 0.0

        for eq in window_eq:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd_pct = (eq - peak) / peak * 100
                if dd_pct < max_dd_pct:
                    max_dd_pct = dd_pct

        result.append({
            "timestamp": timestamps[i],
            "rolling_drawdown_pct": max_dd_pct,
        })

    return result


# ---------------------------------------------------------------------------
# ADV-04/05/06: Trade Breakdown
# ---------------------------------------------------------------------------

def _pair_fills_to_trades(fill_log: list[FillEvent]) -> list[dict]:
    """Pair fills into round-trip trades.

    Returns list of {entry_fill, exit_fill, pnl, entry_time, exit_time}.
    """
    trades = []
    open_fills: dict[str, list[FillEvent]] = {}

    for fill in fill_log:
        symbol = fill.symbol
        if symbol not in open_fills:
            open_fills[symbol] = []

        existing = open_fills[symbol]
        if existing and existing[0].side != fill.side:
            open_fill = existing.pop(0)
            if open_fill.side == OrderSide.BUY:
                pnl = (fill.fill_price - open_fill.fill_price) * min(
                    fill.quantity, open_fill.quantity
                )
            else:
                pnl = (open_fill.fill_price - fill.fill_price) * min(
                    fill.quantity, open_fill.quantity
                )
            pnl -= fill.commission + open_fill.commission
            trades.append({
                "entry_fill": open_fill,
                "exit_fill": fill,
                "pnl": pnl,
                "entry_time": open_fill.timestamp,
                "exit_time": fill.timestamp,
            })
        else:
            existing.append(fill)

    return trades


def compute_trade_breakdown(
    fill_log: list[FillEvent],
) -> dict[str, list[dict]]:
    """Compute trade breakdown by hour, weekday, and session.

    Returns {
        "by_hour": [{hour, count, total_pnl, win_count, loss_count}, ...],
        "by_weekday": [{weekday, weekday_name, count, total_pnl, ...}, ...],
        "by_session": [{session, count, total_pnl, ...}, ...],
    }
    """
    trades = _pair_fills_to_trades(fill_log)

    if not trades:
        return {
            "by_hour": [],
            "by_weekday": [],
            "by_session": [],
        }

    # By hour (ADV-04)
    hour_stats: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "total_pnl": Decimal("0"), "wins": 0, "losses": 0}
    )
    for t in trades:
        h = t["entry_time"].hour
        hour_stats[h]["count"] += 1
        hour_stats[h]["total_pnl"] += t["pnl"]
        if t["pnl"] > Decimal("0"):
            hour_stats[h]["wins"] += 1
        else:
            hour_stats[h]["losses"] += 1

    by_hour = [
        {
            "hour": h,
            "count": s["count"],
            "total_pnl": s["total_pnl"],
            "win_count": s["wins"],
            "loss_count": s["losses"],
        }
        for h, s in sorted(hour_stats.items())
    ]

    # By weekday (ADV-05)
    weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_stats: dict[int, dict] = defaultdict(
        lambda: {"count": 0, "total_pnl": Decimal("0"), "wins": 0, "losses": 0}
    )
    for t in trades:
        wd = t["entry_time"].weekday()
        weekday_stats[wd]["count"] += 1
        weekday_stats[wd]["total_pnl"] += t["pnl"]
        if t["pnl"] > Decimal("0"):
            weekday_stats[wd]["wins"] += 1
        else:
            weekday_stats[wd]["losses"] += 1

    by_weekday = [
        {
            "weekday": wd,
            "weekday_name": weekday_names[wd],
            "count": s["count"],
            "total_pnl": s["total_pnl"],
            "win_count": s["wins"],
            "loss_count": s["losses"],
        }
        for wd, s in sorted(weekday_stats.items())
    ]

    # By session (ADV-06)
    session_stats: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "total_pnl": Decimal("0"), "wins": 0, "losses": 0}
    )
    for t in trades:
        session = _get_session(t["entry_time"].hour)
        session_stats[session]["count"] += 1
        session_stats[session]["total_pnl"] += t["pnl"]
        if t["pnl"] > Decimal("0"):
            session_stats[session]["wins"] += 1
        else:
            session_stats[session]["losses"] += 1

    session_order = [
        "Pre-Market", "Morning", "Lunch", "Afternoon", "After-Hours", "Off-Hours",
    ]
    by_session = [
        {
            "session": s,
            "count": session_stats[s]["count"],
            "total_pnl": session_stats[s]["total_pnl"],
            "win_count": session_stats[s]["wins"],
            "loss_count": session_stats[s]["losses"],
        }
        for s in session_order
        if s in session_stats
    ]

    return {
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "by_session": by_session,
    }


# ---------------------------------------------------------------------------
# ADV-07/08: MAE/MFE Analysis
# ---------------------------------------------------------------------------

def compute_mae_mfe(
    equity_log: list[dict],
    fill_log: list[FillEvent],
) -> list[dict]:
    """Compute Maximum Adverse/Favorable Excursion per trade.

    For each round-trip trade:
    - MAE = max adverse price move during the trade (worst point)
    - MFE = max favorable price move during the trade (best point)

    Returns list of {entry_time, exit_time, pnl, mae, mfe, side, is_win}.
    MAE/MFE are expressed as price deltas (positive = favorable/adverse).
    """
    trades = _pair_fills_to_trades(fill_log)

    if not trades or not equity_log:
        return []

    # Build timestamp→price lookup from equity_log
    price_series = []
    for entry in equity_log:
        price_series.append({
            "timestamp": entry["timestamp"],
            "price": entry.get("price", entry["equity"]),
        })

    result = []
    for trade in trades:
        entry_time = trade["entry_time"]
        exit_time = trade["exit_time"]
        entry_price = trade["entry_fill"].fill_price
        is_long = trade["entry_fill"].side == OrderSide.BUY

        # Find bars during this trade
        trade_prices = [
            p["price"] for p in price_series
            if entry_time <= p["timestamp"] <= exit_time
        ]

        if not trade_prices:
            continue

        if is_long:
            # Long: MAE = entry - min_price, MFE = max_price - entry
            min_price = min(trade_prices)
            max_price = max(trade_prices)
            mae = entry_price - min_price  # positive = adverse move down
            mfe = max_price - entry_price  # positive = favorable move up
        else:
            # Short: MAE = max_price - entry, MFE = entry - min_price
            min_price = min(trade_prices)
            max_price = max(trade_prices)
            mae = max_price - entry_price  # positive = adverse move up
            mfe = entry_price - min_price  # positive = favorable move down

        result.append({
            "entry_time": entry_time,
            "exit_time": exit_time,
            "pnl": trade["pnl"],
            "mae": mae,
            "mfe": mfe,
            "side": "LONG" if is_long else "SHORT",
            "is_win": trade["pnl"] > Decimal("0"),
        })

    return result


# ---------------------------------------------------------------------------
# ADV-09: Commission Sensitivity Sweep
# ---------------------------------------------------------------------------

def run_commission_sweep(
    symbol: str,
    strategy_name: str,
    timeframe: str,
    multipliers: Optional[list[float]] = None,
) -> list[dict]:
    """Run backtest with varying friction multipliers.

    Default multipliers: [0, 0.5, 1.0, 2.0, 3.0].
    Returns list of {multiplier, sharpe, net_pnl, win_rate, max_dd_pct}.
    """
    from src.data_handler import DataHandler
    from src.engine import create_engine
    from src.metrics import compute, MetricsComputationError

    if multipliers is None:
        multipliers = [0.0, 0.5, 1.0, 2.0, 3.0]

    # Import strategy
    import importlib

    strategy_map = {
        "reversal": ("src.strategy.reversal", "ReversalStrategy"),
        "breakout": ("src.strategy.breakout", "BreakoutStrategy"),
        "fvg": ("src.strategy.fvg", "FVGStrategy"),
    }

    if strategy_name not in strategy_map:
        return []

    module_path, class_name = strategy_map[strategy_name]
    module = importlib.import_module(module_path)
    strategy_cls = getattr(module, class_name)

    # Base friction values
    base_slippage = Decimal("0.0001")
    base_commission_trade = Decimal("1.00")
    base_commission_share = Decimal("0.005")
    base_spread = Decimal("0.0002")

    results = []
    for mult in multipliers:
        mult_d = Decimal(str(mult))

        try:
            dh = DataHandler(symbol=symbol, source="yfinance", timeframe=timeframe)
            strategy = strategy_cls(symbol=symbol, timeframe=timeframe)
            engine = create_engine(
                dh,
                strategy,
                slippage_pct=base_slippage * mult_d,
                commission_per_trade=base_commission_trade * mult_d,
                commission_per_share=base_commission_share * mult_d,
                spread_pct=base_spread * mult_d,
            )
            result = engine.run()

            if not result.equity_log:
                results.append({
                    "multiplier": mult,
                    "sharpe": 0.0,
                    "net_pnl": 0.0,
                    "win_rate": 0.0,
                    "max_dd_pct": 0.0,
                })
                continue

            metrics = compute(result.equity_log, result.fill_log, timeframe=timeframe)
            results.append({
                "multiplier": mult,
                "sharpe": float(metrics.sharpe_ratio),
                "net_pnl": float(metrics.net_pnl),
                "win_rate": float(metrics.win_rate),
                "max_dd_pct": float(metrics.max_drawdown_pct),
            })
        except (MetricsComputationError, Exception):
            results.append({
                "multiplier": mult,
                "sharpe": 0.0,
                "net_pnl": 0.0,
                "win_rate": 0.0,
                "max_dd_pct": 0.0,
            })

    return results
