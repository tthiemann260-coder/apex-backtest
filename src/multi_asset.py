"""
multi_asset.py — Multi-symbol backtest engine for apex-backtest.

Provides:
- merge_bars: Heap-based chronological merge of N DataHandler generators (MULTI-01)
- MultiAssetEngine: Per-symbol strategy routing with shared Portfolio (MULTI-02)
- compute_per_symbol_equity: Group equity log by symbol (MULTI-03)
- compute_rolling_correlation: Rolling Pearson correlation between asset pairs (MULTI-03)
- create_multi_asset_engine: Factory function for fresh instances

All arithmetic uses decimal.Decimal exclusively.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations
from typing import Generator, Optional

from src.data_handler import DataHandler
from src.events import (
    FillEvent, MarketEvent, OrderEvent, SignalEvent,
    SignalType, OrderType, OrderSide,
)
from src.execution import ExecutionHandler
from src.portfolio import Portfolio
from src.strategy.base import BaseStrategy


# ---------------------------------------------------------------------------
# Bar Merge (MULTI-01)
# ---------------------------------------------------------------------------

def merge_bars(
    handlers: dict[str, DataHandler],
) -> Generator[MarketEvent, None, None]:
    """Merge N DataHandler generators into a single chronological stream.

    Uses heapq with (timestamp, symbol, counter, bar) as sort key for
    deterministic ordering when timestamps are identical.  Secondary sort
    by symbol name (alphabetical); counter prevents comparison of
    MarketEvent objects (not comparable).
    """
    counter = 0
    iterators: dict[str, Generator] = {}
    heap: list[tuple] = []

    for symbol, dh in handlers.items():
        it = iter(dh.stream_bars())
        try:
            bar = next(it)
            heapq.heappush(heap, (bar.timestamp, symbol, counter, bar))
            counter += 1
            iterators[symbol] = it
        except StopIteration:
            pass  # Empty generator — skip

    while heap:
        _ts, _sym, _cnt, bar = heapq.heappop(heap)
        yield bar
        it = iterators.get(_sym)
        if it is not None:
            try:
                next_bar = next(it)
                heapq.heappush(heap, (next_bar.timestamp, _sym, counter, next_bar))
                counter += 1
            except StopIteration:
                del iterators[_sym]


# ---------------------------------------------------------------------------
# MultiAssetEngine (MULTI-02)
# ---------------------------------------------------------------------------

@dataclass
class MultiAssetResult:
    """Container for multi-asset backtest results."""
    equity_log: list[dict] = field(default_factory=list)
    fill_log: list[FillEvent] = field(default_factory=list)
    event_log: list = field(default_factory=list)
    final_equity: Decimal = Decimal("0")
    total_bars: int = 0


class MultiAssetEngine:
    """Multi-symbol backtest engine with shared Portfolio.

    Parameters
    ----------
    handlers : dict[str, DataHandler]
        DataHandler per symbol.
    strategies : dict[str, BaseStrategy]
        Strategy per symbol (keys must match handlers).
    portfolio : Portfolio
        Shared portfolio tracking all positions.
    execution_handlers : dict[str, ExecutionHandler]
        ExecutionHandler per symbol — isolates pending orders per symbol.
    risk_manager : Optional
        Optional risk manager.
    """

    def __init__(
        self,
        handlers: dict[str, DataHandler],
        strategies: dict[str, BaseStrategy],
        portfolio: Portfolio,
        execution_handlers: dict[str, ExecutionHandler],
        risk_manager=None,
    ) -> None:
        self._handlers = handlers
        self._strategies = strategies
        self._portfolio = portfolio
        self._executions = execution_handlers
        self._risk_manager = risk_manager
        self._last_prices: dict[str, Decimal] = {}
        self._event_log: list = []

    def run(self) -> MultiAssetResult:
        """Run the multi-asset backtest.

        Returns a MultiAssetResult with equity log, fill log, and event log.
        """
        total_bars = 0
        prev_ts = None

        for bar in merge_bars(self._handlers):
            total_bars += 1

            # Track last known price per symbol
            self._last_prices[bar.symbol] = bar.close

            # 1. Process pending orders for THIS symbol only
            execution = self._executions[bar.symbol]
            fills = execution.process_bar(bar)
            for fill in fills:
                self._event_log.append(fill)
                self._portfolio.process_fill(fill)

            # 2. Check margin with ALL current prices
            to_liquidate = self._portfolio.check_margin(self._last_prices)
            for symbol in to_liquidate:
                if symbol in self._last_prices:
                    liq_fill = self._portfolio.force_liquidate(
                        symbol, self._last_prices[symbol],
                    )
                    if liq_fill:
                        self._event_log.append(liq_fill)

            # 3. Route bar to matching strategy
            strategy = self._strategies.get(bar.symbol)
            if strategy is not None:
                signal = strategy.calculate_signals(bar)
                if signal is not None:
                    self._event_log.append(signal)
                    order = self._signal_to_order(signal, bar)
                    if order is not None:
                        self._event_log.append(order)
                        execution.submit_order(order)

            # 4. Snapshot equity when timestamp changes or at end
            if prev_ts is not None and bar.timestamp != prev_ts:
                self._snapshot_equity(prev_ts)
            prev_ts = bar.timestamp

        # Final equity snapshot
        if prev_ts is not None:
            self._snapshot_equity(prev_ts)

        # Build result
        final_equity = Decimal("0")
        if self._portfolio.equity_log:
            final_equity = self._portfolio.equity_log[-1]["equity"]

        return MultiAssetResult(
            equity_log=self._portfolio.equity_log,
            fill_log=self._portfolio.fill_log,
            event_log=self._event_log,
            final_equity=final_equity,
            total_bars=total_bars,
        )

    def _snapshot_equity(self, timestamp) -> None:
        """Append equity snapshot with ALL symbols' last known prices."""
        equity = self._portfolio.compute_equity(self._last_prices)
        self._portfolio._equity_log.append({
            "timestamp": timestamp,
            "equity": equity,
            "cash": self._portfolio.cash,
            "prices": dict(self._last_prices),
        })

    def _signal_to_order(
        self, signal: SignalEvent, bar: MarketEvent,
    ) -> Optional[OrderEvent]:
        """Convert a SignalEvent to an OrderEvent."""
        # Risk gate — applies to LONG and SHORT, not EXIT
        if self._risk_manager is not None and signal.signal_type != SignalType.EXIT:
            can, reason = self._risk_manager.can_trade(self._portfolio, bar)
            if not can:
                return None

        if signal.signal_type == SignalType.LONG:
            quantity = self._calculate_order_quantity(signal, bar)
            if quantity <= Decimal("0"):
                return None
            valid, _ = self._portfolio.validate_order(
                bar.symbol, OrderSide.BUY, quantity, bar.close, bar.volume,
            )
            if not valid:
                return None
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                quantity=quantity,
                price=None,
            )

        elif signal.signal_type == SignalType.SHORT:
            quantity = self._calculate_order_quantity(signal, bar)
            if quantity <= Decimal("0"):
                return None
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=OrderSide.SELL,
                quantity=quantity,
                price=None,
            )

        elif signal.signal_type == SignalType.EXIT:
            pos = self._portfolio.positions.get(signal.symbol)
            if pos is None or pos.quantity <= Decimal("0"):
                return None
            close_side = (
                OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY
            )
            return OrderEvent(
                symbol=signal.symbol,
                timestamp=signal.timestamp,
                order_type=OrderType.MARKET,
                side=close_side,
                quantity=pos.quantity,
                price=None,
            )

        return None

    def _calculate_order_quantity(
        self, signal: SignalEvent, bar: MarketEvent,
    ) -> Decimal:
        """Calculate order quantity based on risk settings."""
        if self._risk_manager is not None:
            # Pass per-symbol strategy for ATR access
            strategy = self._strategies.get(bar.symbol)
            return self._risk_manager.compute_quantity(
                self._portfolio, strategy, bar,
            )

        # Legacy fallback: 10% fixed fractional
        equity_log = self._portfolio.equity_log
        if equity_log:
            equity = equity_log[-1]["equity"]
        else:
            equity = self._portfolio.cash

        if bar.close <= Decimal("0"):
            return Decimal("0")
        quantity = (equity * Decimal("0.10")) / bar.close
        return Decimal(str(int(quantity)))


# ---------------------------------------------------------------------------
# Per-Symbol Equity Extraction (MULTI-03)
# ---------------------------------------------------------------------------

def compute_per_symbol_equity(
    equity_log: list[dict],
) -> dict[str, list[dict]]:
    """Extract per-symbol equity contribution from the shared equity_log.

    Groups equity entries by symbol presence in the prices dict.
    Returns {symbol: [{timestamp, equity}, ...]} for correlation input.
    """
    if not equity_log:
        return {}

    result: dict[str, list[dict]] = {}
    for entry in equity_log:
        ts = entry["timestamp"]
        prices = entry.get("prices", {})
        for symbol in prices:
            if symbol not in result:
                result[symbol] = []
            result[symbol].append({
                "timestamp": ts,
                "equity": entry["equity"],
            })
    return result


# ---------------------------------------------------------------------------
# Rolling Correlation (MULTI-03)
# ---------------------------------------------------------------------------

def compute_rolling_correlation(
    equity_curves: dict[str, list[Decimal]],
    timestamps: list,
    window: int = 60,
) -> list[dict]:
    """Compute rolling pairwise Pearson correlation between asset return series.

    Parameters
    ----------
    equity_curves : dict[str, list[Decimal]]
        Equity values per symbol (same length, aligned by index).
    timestamps : list
        Timestamp per index position.
    window : int
        Rolling window size (default 60).

    Returns
    -------
    list[dict]
        List of {timestamp, pair, correlation} dicts.
        Each pair is "SYMBOL_A/SYMBOL_B" (alphabetical order).
    """
    symbols = sorted(equity_curves.keys())
    if len(symbols) < 2:
        return []

    # Convert equity curves to return series
    returns: dict[str, list[Decimal]] = {}
    for sym in symbols:
        eq = equity_curves[sym]
        rets: list[Decimal] = []
        for i in range(1, len(eq)):
            if eq[i - 1] != Decimal("0"):
                rets.append((eq[i] - eq[i - 1]) / eq[i - 1])
            else:
                rets.append(Decimal("0"))
        returns[sym] = rets

    # Align timestamps (skip first — no return for first point)
    aligned_ts = timestamps[1:] if len(timestamps) > 1 else []

    results: list[dict] = []
    pairs = list(combinations(symbols, 2))

    for i in range(window - 1, len(aligned_ts)):
        ts = aligned_ts[i]
        for sym_a, sym_b in pairs:
            window_a = returns[sym_a][i - window + 1: i + 1]
            window_b = returns[sym_b][i - window + 1: i + 1]

            corr = _pearson_decimal(window_a, window_b)
            results.append({
                "timestamp": ts,
                "pair": f"{sym_a}/{sym_b}",
                "correlation": corr,
            })

    return results


def _pearson_decimal(x: list[Decimal], y: list[Decimal]) -> Decimal:
    """Compute Pearson correlation coefficient using Decimal arithmetic."""
    n = Decimal(str(len(x)))
    if n <= Decimal("1"):
        return Decimal("0")

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    if var_x == Decimal("0") or var_y == Decimal("0"):
        return Decimal("0")

    # sqrt via Decimal: use ** Decimal("0.5")
    denom = (var_x * var_y) ** Decimal("0.5")
    if denom == Decimal("0"):
        return Decimal("0")

    return cov / denom


# ---------------------------------------------------------------------------
# Factory (MULTI-02)
# ---------------------------------------------------------------------------

def create_multi_asset_engine(
    handlers: dict[str, DataHandler],
    strategies: dict[str, BaseStrategy],
    initial_cash: Decimal = Decimal("10000"),
    slippage_pct: Decimal = Decimal("0.0001"),
    commission_per_trade: Decimal = Decimal("1.00"),
    commission_per_share: Decimal = Decimal("0.005"),
    spread_pct: Decimal = Decimal("0.0002"),
    margin_requirement: Decimal = Decimal("0.25"),
    risk_manager=None,
) -> MultiAssetEngine:
    """Create MultiAssetEngine with fresh components per symbol."""
    portfolio = Portfolio(
        initial_cash=initial_cash,
        margin_requirement=margin_requirement,
    )
    execution_handlers: dict[str, ExecutionHandler] = {}
    for symbol in handlers:
        execution_handlers[symbol] = ExecutionHandler(
            slippage_pct=slippage_pct,
            commission_per_trade=commission_per_trade,
            commission_per_share=commission_per_share,
            spread_pct=spread_pct,
        )
    return MultiAssetEngine(
        handlers=handlers,
        strategies=strategies,
        portfolio=portfolio,
        execution_handlers=execution_handlers,
        risk_manager=risk_manager,
    )
