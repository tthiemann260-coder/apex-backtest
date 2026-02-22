# PLAN-17A: Multi-Symbol Bar Merge + MultiAssetEngine

## Context
Phase 17 enables backtesting across multiple symbols simultaneously. This plan implements heap-based chronological bar merging and a new MultiAssetEngine that routes bars to per-symbol strategies with a shared Portfolio.

**Requirements:** MULTI-01, MULTI-02 | **~220 LOC** | **No dependencies beyond Phase 16**

## Architecture Decisions
- **New file:** `src/multi_asset.py` (contains merge + engine — cohesive module)
- **Heap merge:** `heapq.merge` with `(timestamp, counter, symbol_name, bar)` tuples — counter prevents comparison of MarketEvent objects on timestamp ties
- **Per-symbol strategies:** `dict[str, BaseStrategy]` — one strategy instance per symbol
- **Per-symbol ExecutionHandlers:** `dict[str, ExecutionHandler]` — **CRITICAL: isolates pending orders per symbol so AAPL orders never fill against EURUSD bars**
- **Shared state:** Single Portfolio (tracks all positions across symbols)
- **Multi-price equity:** After processing ALL bars at same timestamp, call `portfolio.compute_equity(self._last_prices)` with ALL last known prices and append to equity log manually — do NOT use `portfolio.update_equity(bar)` which only has one symbol's price
- **BacktestEngine untouched:** MultiAssetEngine is a NEW class, not a modification

## New File

### `src/multi_asset.py` (~220 LOC)

#### `merge_bars(handlers: dict[str, DataHandler]) -> Generator[MarketEvent, None, None]`
Heap-based chronological merge of N DataHandler generators.

```python
def merge_bars(handlers: dict[str, DataHandler]):
    """Merge N DataHandler generators into a single chronological stream.

    Uses heapq with (timestamp, counter, symbol) as sort key for deterministic
    ordering when timestamps are identical. Counter prevents comparison of
    MarketEvent objects (not comparable).
    """
    import heapq

    counter = 0  # Tie-breaker to avoid comparing MarketEvent objects
    iterators = {}
    heap = []
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
        ts, symbol, _cnt, bar = heapq.heappop(heap)
        yield bar
        it = iterators.get(symbol)
        if it is not None:
            try:
                next_bar = next(it)
                heapq.heappush(heap, (next_bar.timestamp, symbol, counter, next_bar))
                counter += 1
            except StopIteration:
                del iterators[symbol]
```

**Key detail — sort tuple:** `(timestamp, symbol, counter, bar)` — secondary sort by symbol name (alphabetical) for deterministic ordering at same timestamp, counter as final tie-breaker prevents MarketEvent comparison.

#### `class MultiAssetEngine`
```python
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
    risk_manager : Optional[RiskManager]
        Optional risk manager.
    """
```

**__init__ setup:**
```python
def __init__(self, handlers, strategies, portfolio, execution_handlers,
             risk_manager=None):
    self._handlers = handlers
    self._strategies = strategies
    self._portfolio = portfolio
    self._executions = execution_handlers  # dict[str, ExecutionHandler]
    self._risk_manager = risk_manager
    self._last_prices: dict[str, Decimal] = {}
    self._event_log: list = []
```

**run() pipeline per bar:**
1. Pop bar from merged stream
2. Track last known price: `self._last_prices[bar.symbol] = bar.close`
3. Process pending orders ONLY for THIS symbol's ExecutionHandler: `self._executions[bar.symbol].process_bar(bar)`
4. Process fills through shared Portfolio
5. Check margin with ALL current prices: `self._portfolio.check_margin(self._last_prices)`
6. Route bar to matching strategy → get signal
7. Convert signal to order (with risk gate) → submit to symbol's ExecutionHandler
8. Collect timestamps; after all bars at same timestamp processed: append equity snapshot

**Equity tracking — multi-price approach:**
```python
# After processing a bar, check if next bar has different timestamp
# If yes (or end of stream), snapshot equity with ALL prices
equity = self._portfolio.compute_equity(self._last_prices)
self._portfolio._equity_log.append({
    "timestamp": current_ts,
    "equity": equity,
    "cash": self._portfolio.cash,
    "prices": dict(self._last_prices),  # All last known prices
})
```

**Signal-to-order (shared with BacktestEngine pattern):**
```python
def _signal_to_order(self, signal, bar):
    """Convert signal to order — same logic as BacktestEngine."""
    # Risk gate (LONG/SHORT only)
    if self._risk_manager is not None and signal.signal_type != SignalType.EXIT:
        can, reason = self._risk_manager.can_trade(self._portfolio, bar)
        if not can:
            return None
    # LONG → BUY, SHORT → SELL, EXIT → close position
    # ... (identical pattern to engine.py _signal_to_order)
```

#### `create_multi_asset_engine(handlers, strategies, ...) -> MultiAssetEngine`
Factory function analogous to `create_engine()`.

```python
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
    portfolio = Portfolio(initial_cash=initial_cash, margin_requirement=margin_requirement)
    execution_handlers = {}
    for symbol in handlers:
        execution_handlers[symbol] = ExecutionHandler(
            slippage_pct=slippage_pct,
            commission_per_trade=commission_per_trade,
            commission_per_share=commission_per_share,
            spread_pct=spread_pct,
        )
    return MultiAssetEngine(
        handlers=handlers, strategies=strategies,
        portfolio=portfolio, execution_handlers=execution_handlers,
        risk_manager=risk_manager,
    )
```

## Verification
1. merge_bars with 2 symbols yields chronologically correct stream
2. Deterministic ordering when timestamps match (secondary sort by symbol name)
3. Empty generator handled gracefully
4. heapq counter prevents MarketEvent comparison errors
5. MultiAssetEngine processes bars for multiple symbols
6. Per-symbol ExecutionHandlers: AAPL orders NEVER fill against EURUSD bars
7. Shared Portfolio tracks positions across all symbols
8. Equity snapshots use ALL symbols' last known prices
9. All existing 508 tests still pass (no modifications to existing files)
