# PLAN-17B: Cross-Asset Correlation + Per-Asset Position Limits

## Context
PLAN-17A provides the MultiAssetEngine. This plan adds rolling cross-asset correlation computation and per-asset position limits in RiskManager.

**Requirements:** MULTI-03, MULTI-04 | **~120 LOC** | **Dependency: PLAN-17A**

## New Functions (added to `src/multi_asset.py`)

### `compute_per_symbol_equity(equity_log) -> dict[str, list[dict]]` (~20 LOC)
Extract per-symbol equity contribution from the shared equity_log.
- Groups equity entries by symbol
- Returns `{symbol: [{timestamp, equity}, ...]}` for correlation input

### `compute_rolling_correlation(equity_curves, timestamps, window=60) -> list[dict]` (~50 LOC)
Rolling Pearson correlation between all pairs of asset equity curves.

```python
def compute_rolling_correlation(
    equity_curves: dict[str, list[Decimal]],
    timestamps: list[datetime],
    window: int = 60,
) -> list[dict]:
    """Compute rolling pairwise correlation between asset return series.

    Returns list of {timestamp, pair, correlation} dicts.
    Each pair is "SYMBOL_A/SYMBOL_B".
    """
```

**Algorithm:**
1. Convert equity curves to return series: `returns[i] = (eq[i] - eq[i-1]) / eq[i-1]`
   - **Guard:** if `eq[i-1] == 0`, skip that return (avoid division by zero)
2. For each window position:
   - Extract window of returns per symbol
   - Compute Pearson correlation: `cov(A,B) / (std(A) * std(B))`
   - **Guard:** if `std(A) == 0 or std(B) == 0`, correlation = `Decimal("0")` (flat series = uncorrelated)
   - All using Decimal arithmetic (no numpy)
3. Return correlation time series per pair

## Modified: `src/risk_manager.py` (~30 LOC)

### Per-Asset Position Limits (MULTI-04)

**RiskManager.__init__ addition:**
```python
per_asset_max_positions: dict[str, int] = None  # e.g., {"AAPL": 1, "EURUSD": 2}
per_asset_max_pct: dict[str, Decimal] = None    # e.g., {"AAPL": Decimal("0.15")}
```

**can_trade() extension:**
```python
# Per-asset position check
if self._per_asset_max_positions is not None:
    symbol = bar.symbol
    symbol_limit = self._per_asset_max_positions.get(symbol)
    if symbol_limit is not None:
        symbol_positions = sum(
            1 for s, pos in portfolio.positions.items()
            if s == symbol and pos.quantity > Decimal("0")
        )
        if symbol_positions >= symbol_limit:
            return False, f"Per-asset limit reached for {symbol}"
```

**compute_quantity() extension:**
```python
# Per-asset max pct cap
if self._per_asset_max_pct is not None:
    asset_limit = self._per_asset_max_pct.get(bar.symbol)
    if asset_limit is not None:
        asset_max_qty = (equity * asset_limit) / bar.close
        quantity = min(quantity, asset_max_qty)
```

## Verification
1. Per-symbol equity extraction groups correctly
2. Rolling correlation returns values in [-1, 1]
3. Perfectly correlated series -> correlation = 1.0
4. Division-by-zero: flat series returns correlation 0 (not crash)
5. Division-by-zero: zero equity returns skip that return
6. Per-asset position limit blocks excess positions for specific symbol
7. Per-asset max_pct caps position size per symbol
8. Unspecified symbols use global defaults
