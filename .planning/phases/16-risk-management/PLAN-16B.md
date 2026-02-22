# PLAN-16B: Kelly Criterion + Portfolio Heat Monitor

## Context
PLAN-16A provides the RiskManager core. This plan adds two advanced sizing modules: Kelly Criterion (adaptive sizing from trade history) and Portfolio Heat Monitor (total open risk tracking).

**Requirements:** RISK-03, RISK-04 | **~150 LOC** | **Dependency: PLAN-16A**

## New Modules (added to `src/risk_manager.py`)

### KellyCriterion class (~60 LOC)

```python
class KellyCriterion:
    """Adaptive position sizing from rolling trade history.

    Parameters
    ----------
    lookback : int
        Rolling window of trades for Kelly calculation (default 40).
    fraction : Decimal
        Kelly fraction — 0.5 = Half-Kelly (default, recommended).
    min_trades : int
        Minimum trades before Kelly activates (default 20).
    max_kelly_pct : Decimal
        Cap Kelly output at this pct of equity (default 0.05 = 5%).
    """
```

**Methods:**

#### `update(fill_log: list[FillEvent]) -> None`
Compute win_rate and win_loss_ratio from last `lookback` round-trip trades.
Round-trip = pair of fills (open + close) on same symbol.

#### `kelly_fraction() -> Optional[Decimal]`
1. If `len(trades) < min_trades` → return `None` (caller uses Fixed Fractional)
2. `kelly = win_rate - (1 - win_rate) / win_loss_ratio`
3. `adjusted = kelly * self._fraction` (Half-Kelly)
4. Cap at `max_kelly_pct`, floor at `Decimal('0')`
5. Return adjusted fraction

### PortfolioHeatMonitor class (~50 LOC)

```python
class PortfolioHeatMonitor:
    """Tracks total open risk across all positions.

    Parameters
    ----------
    max_heat_pct : Decimal
        Maximum portfolio heat as pct of equity (default 0.06 = 6%).
    atr_multiplier : Decimal
        Same multiplier used for stop distance calculation.
    """
```

**Methods:**

#### `compute_heat(portfolio, strategy, prices) -> Decimal`
For each open position:
1. Get ATR-based stop distance
2. `position_risk = quantity * stop_distance`
3. Sum all position risks
4. `heat_pct = total_risk / equity`

#### `can_add_risk(portfolio, strategy, prices, new_risk) -> bool`
`current_heat + new_risk / equity <= max_heat_pct`

## Modified: `src/risk_manager.py`

### RiskManager additions (~30 LOC)
- Constructor: accept `kelly: Optional[KellyCriterion]`, `heat_monitor: Optional[PortfolioHeatMonitor]`
- `compute_quantity()`: if Kelly active and has enough trades, use Kelly fraction instead of `risk_per_trade`
- `can_trade()`: if heat_monitor active, check `can_add_risk()` before allowing trade

### Integration in compute_quantity():
```python
# Step 2b: Kelly override
if self._kelly is not None:
    self._kelly.update(portfolio.fill_log)
    kelly_frac = self._kelly.kelly_fraction()
    if kelly_frac is not None:
        risk_per_trade = kelly_frac  # replaces fixed risk_per_trade
```

### Integration in can_trade():
```python
# Step 3: Portfolio heat check
if self._heat_monitor is not None:
    estimated_risk = stop_distance * estimated_quantity
    if not self._heat_monitor.can_add_risk(portfolio, strategy, prices, estimated_risk):
        return (False, "Portfolio heat limit exceeded")
```

---

## Verification
1. Kelly returns None with < min_trades → Fixed Fractional used
2. Kelly with 100% win rate → capped at max_kelly_pct
3. Kelly with 50/50 win rate 1:1 ratio → kelly = 0 → no position
4. Heat monitor blocks trade when total risk > max_heat_pct
5. Heat monitor allows trade when within limits
