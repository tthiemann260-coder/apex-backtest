# PLAN-16C: Drawdown-Based Scaling

## Context
PLAN-16A/B provide RiskManager + Kelly + Heat. This plan adds automatic position size reduction during drawdowns.

**Requirements:** RISK-05 | **~50 LOC** | **Dependency: PLAN-16A**

## New Module (added to `src/risk_manager.py`)

### DrawdownScaler class (~50 LOC)

```python
class DrawdownScaler:
    """Reduces position size linearly during drawdowns.

    Parameters
    ----------
    max_drawdown_pct : Decimal
        Drawdown threshold where scaling begins (default 0.05 = 5%).
    full_stop_pct : Decimal
        Drawdown where position size hits min_scale (default 0.20 = 20%).
    min_scale : Decimal
        Minimum scaling factor (default 0.25 = 25% of normal size).
    """
```

**Methods:**

#### `compute_scale(equity_log: list[dict]) -> Decimal`
1. Find peak equity from `equity_log`
2. `current_dd = (peak - current) / peak`
3. If `current_dd <= max_drawdown_pct` → return `Decimal('1')` (no scaling)
4. If `current_dd >= full_stop_pct` → return `min_scale`
5. Linear interpolation between thresholds:
   ```
   progress = (current_dd - max_drawdown_pct) / (full_stop_pct - max_drawdown_pct)
   scale = 1 - progress * (1 - min_scale)
   ```

## Modified: `src/risk_manager.py`

### RiskManager additions (~10 LOC)
- Constructor: accept `dd_scaler: Optional[DrawdownScaler]`
- `compute_quantity()`: after computing raw quantity, multiply by `dd_scaler.compute_scale(equity_log)`

```python
# Step 6: Drawdown scaling
if self._dd_scaler is not None:
    scale = self._dd_scaler.compute_scale(portfolio.equity_log)
    quantity = quantity * scale
```

---

## Verification
1. No drawdown → scale = 1.0 (full size)
2. Drawdown at max_drawdown_pct boundary → scale = 1.0
3. Drawdown at full_stop_pct → scale = min_scale
4. Drawdown between thresholds → linear interpolation
5. Empty equity_log → scale = 1.0
