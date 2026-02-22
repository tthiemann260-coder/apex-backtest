# PLAN-16A: RiskManager Core + Fixed Fractional Sizing

## Context
Phase 16 replaces the hardcoded 10% position sizing in `engine.py:170-183` with a modular RiskManager. This first plan builds the core module with Fixed Fractional sizing (ATR-based stop distance) and the `can_trade()` / `compute_quantity()` interface.

**Requirements:** RISK-01, RISK-02 | **~150 LOC** | **No dependencies**

## Architecture Decision
- **New file:** `src/risk_manager.py` (top-level, not inside strategy/ — risk is cross-cutting)
- **Protocol-style:** RiskManager is injected into Engine via `create_engine()` — optional parameter with sensible default
- **ATR Stop Distance:** `stop_distance = ATR * atr_multiplier` (default 2.0) — strategy must expose `current_atr` property
- **Fallback:** If strategy has no `current_atr` or ATR=0, fall back to `price * fallback_risk_pct`

## New File

### `src/risk_manager.py` (~150 LOC)

```python
class RiskManager:
    """Central risk orchestrator for position sizing and trade gating.

    Parameters
    ----------
    risk_per_trade : Decimal
        Max risk per trade as fraction of equity (default 0.01 = 1%).
    atr_multiplier : Decimal
        ATR multiplier for stop distance (default 2.0).
    fallback_risk_pct : Decimal
        Fallback stop distance as pct of price if ATR unavailable (default 0.02 = 2%).
    max_position_pct : Decimal
        Max single position as pct of equity (default 0.20 = 20%).
    max_concurrent_positions : int
        Max number of open positions (default 5).
    """
```

**Methods:**

#### `can_trade(portfolio, bar) -> tuple[bool, str]`
1. Check `max_concurrent_positions`: count open positions with quantity > 0
2. Check `max_position_pct`: would-be position value < equity * max_position_pct
3. Return `(True, "OK")` or `(False, reason)`

#### `compute_quantity(portfolio, strategy, bar) -> Decimal`
1. Get equity from portfolio (equity_log[-1] or cash)
2. Get ATR from strategy (`getattr(strategy, 'current_atr', Decimal('0'))`)
3. Compute `stop_distance = atr * atr_multiplier` (or fallback)
4. `risk_amount = equity * risk_per_trade`
5. `raw_quantity = risk_amount / stop_distance`
6. Cap: `max_quantity = (equity * max_position_pct) / bar.close`
7. `quantity = min(raw_quantity, max_quantity)`
8. Round down to integer: `Decimal(str(int(quantity)))`

## Modified Files

### `src/engine.py` (~20 LOC changed)

#### `BacktestEngine.__init__` — add `risk_manager` parameter
```python
def __init__(self, data_handler, strategy, portfolio, execution_handler,
             risk_manager=None):
    ...
    self._risk_manager = risk_manager
```

#### `_signal_to_order()` — integrate risk gate
**IMPORTANT (Advisory #2):** Place `can_trade()` gate BEFORE signal type dispatch (before the `if signal.signal_type ==` block), not inside each branch. This gates both LONG and SHORT signals:
```python
def _signal_to_order(self, signal, bar):
    # Risk gate — applies to LONG and SHORT
    if self._risk_manager is not None and signal.signal_type != SignalType.EXIT:
        can, reason = self._risk_manager.can_trade(self._portfolio, bar)
        if not can:
            return None
    ... existing signal type dispatch ...
```

#### `_calculate_order_quantity()` — delegate to RiskManager
```python
def _calculate_order_quantity(self, bar):
    if self._risk_manager is not None:
        return self._risk_manager.compute_quantity(
            self._portfolio, self._strategy, bar,
        )
    # Legacy fallback: 10% fixed fractional
    ...existing code...
```

#### `create_engine()` — add risk_manager parameter
```python
def create_engine(data_handler, strategy, ..., risk_manager=None):
    ...
    return BacktestEngine(
        data_handler=data_handler,
        strategy=strategy,
        portfolio=portfolio,
        execution_handler=execution,
        risk_manager=risk_manager,
    )
```

### `src/dashboard/callbacks.py` (~5 LOC)
In `_run_backtest()`: if strategy supports risk management, create RiskManager and pass to `create_engine()`. Default: no RiskManager (backward compatible).

---

## Additional Fix (Advisory #4)

### `src/strategy/regime/gated_strategy.py` (+3 LOC)
Add `current_atr` property forwarding to inner strategy:
```python
@property
def current_atr(self) -> Decimal:
    return getattr(self._inner, 'current_atr', Decimal('0'))
```
Without this, RiskManager would fall back to `fallback_risk_pct` even when the inner ICTStrategy has a valid ATR.

---

## Verification
1. Without RiskManager: engine behaves exactly as before (10% fractional)
2. With RiskManager: quantity scales with ATR stop distance
3. `can_trade()` blocks when max concurrent positions reached
4. Fallback activates when strategy has no `current_atr`
5. All existing 482 tests still pass (backward compatible)
6. RegimeGatedStrategy forwards `current_atr` to RiskManager
