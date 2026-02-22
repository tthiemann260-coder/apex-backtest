# PLAN-17C: Unit Tests

## Context
PLAN-17A/B provide all multi-asset modules. This plan adds comprehensive unit tests.

**Requirements:** TEST-23 | **~450 LOC** | **Dependency: PLAN-17A + 17B**

## New File

### `tests/test_multi_asset.py` (~450 LOC, 28 Tests)

| Test-Klasse | Tests | Prueft |
|---|---|---|
| TestMergeBars | 7 | Two symbols chronological, deterministic same-timestamp ordering, single symbol passthrough, empty generator skipped, three symbols, different bar counts, heapq counter prevents MarketEvent comparison |
| TestMultiAssetEngine | 9 | Two-symbol backtest runs, shared portfolio tracks both positions, per-symbol strategy routing, equity log has correct timestamps, equity uses all symbol prices, risk gate applies across symbols, EXIT closes correct symbol, per-symbol execution isolation (AAPL order never fills against EURUSD bar), create_multi_asset_engine factory |
| TestRollingCorrelation | 6 | Perfectly correlated = 1.0, inverse correlated = -1.0, window too short returns empty, unequal lengths handled, real-ish decorrelated series, flat series returns 0 (division-by-zero guard) |
| TestPerAssetLimits | 4 | Per-asset position limit blocks, per-asset max_pct caps, unspecified symbol uses global, per-asset + global interaction |
| TestPerSymbolEquity | 2 | Groups equity by symbol correctly, empty log returns empty |
| **Total** | **28** | |

**Helpers:**
- `_make_bar(close, symbol, idx)` — MarketEvent factory with symbol parameter
- `_make_data_handler_mock(symbol, bars)` — Mock DataHandler that yields given bars
- `_MockPerSymbolStrategy(symbol, signal_bar)` — Signals LONG on specific bar index
- `_make_fill(side, quantity, fill_price, symbol, day)` — FillEvent with symbol

**Key test patterns:**

#### TestMergeBars — Chronological + Deterministic
```python
def test_two_symbols_chronological(self):
    """Bars from 2 symbols are merged chronologically."""
    # AAPL: 10:00, 11:00, 12:00
    # EURUSD: 10:00, 10:30, 11:00
    # Expected: AAPL@10, EURUSD@10, EURUSD@10:30, AAPL@11, EURUSD@11, AAPL@12

def test_deterministic_same_timestamp(self):
    """Same timestamp -> secondary sort by symbol name (alphabetical)."""
    # AAPL@10:00, BTCUSD@10:00 -> AAPL first (A < B)

def test_heapq_counter_prevents_comparison(self):
    """Counter in heap tuple prevents MarketEvent comparison when ts+symbol match."""
    # Two bars from same symbol at same timestamp -> counter breaks tie
```

#### TestMultiAssetEngine — Full Pipeline + Isolation
```python
def test_two_symbol_backtest(self):
    """Run full backtest with 2 symbols, verify equity log populated."""
    # Create 2 mock DataHandlers + 2 strategies
    # Run MultiAssetEngine
    # Assert equity_log has entries, final_equity > 0

def test_per_symbol_strategy_routing(self):
    """Each symbol's bar only goes to its strategy."""
    # AAPL strategy should NOT receive EURUSD bars

def test_per_symbol_execution_isolation(self):
    """CRITICAL: AAPL pending order must NOT fill against EURUSD bar."""
    # Submit AAPL LIMIT order
    # Process EURUSD bar that would trigger it if not isolated
    # Assert order still pending in AAPL's ExecutionHandler
    # Process AAPL bar that triggers it
    # Assert fill happened with AAPL symbol

def test_equity_uses_all_symbol_prices(self):
    """Equity snapshot must include unrealized PnL from ALL symbols."""
    # Open positions in AAPL and EURUSD
    # Verify equity computation uses both last known prices
```

---

## Ausfuehrungsreihenfolge

1. **Wave 1:** PLAN-17A (merge_bars + MultiAssetEngine)
2. **Wave 2:** PLAN-17B (correlation + per-asset limits — depends on 17A)
3. **Wave 3:** PLAN-17C (tests — depends on all above)

## Neue Dateien (2)
- `src/multi_asset.py`
- `tests/test_multi_asset.py`

## Modifizierte Dateien (1)
- `src/risk_manager.py` (per-asset limits, ~30 LOC)

## Nicht modifiziert
- `src/engine.py`, `src/portfolio.py`, `src/execution.py`, `src/events.py`, `src/strategy/base.py`

## Verification
1. `pytest tests/test_multi_asset.py -v` — alle 28 Tests gruen
2. `pytest tests/ -v` — alle 536+ Tests gruen (508 + 28)
3. `pytest --cov=src tests/` — Coverage >= 90%
4. merge_bars yields bars in strict chronological order
5. heapq counter prevents MarketEvent comparison errors
6. MultiAssetEngine routes bars to correct per-symbol strategies
7. Per-symbol ExecutionHandlers: cross-symbol fill isolation verified
8. Shared Portfolio tracks positions across all symbols
9. Equity snapshots use ALL symbols' last known prices
10. Rolling correlation computes correctly for known test series
11. Division-by-zero guards work (flat series, zero equity)
12. Per-asset limits block/cap as configured
