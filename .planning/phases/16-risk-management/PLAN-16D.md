# PLAN-16D: Unit Tests + Dashboard Integration

## Context
PLAN-16A/B/C provide all risk management modules. This plan adds comprehensive unit tests and dashboard sweep params.

**Requirements:** TEST-22 | **~400 LOC** | **Dependency: PLAN-16A + 16B + 16C**

## New File

### `tests/test_risk_manager.py` (~400 LOC, 25+ Tests)

| Test-Klasse | Tests | Prueft |
|---|---|---|
| TestRiskManagerCore | 6 | compute_quantity basic, ATR-based sizing, fallback when no ATR, max_position_pct cap, zero price, can_trade max_concurrent |
| TestKellyCriterion | 6 | warmup returns None, 100% wins capped, 50/50 ratio returns 0, half-kelly scaling, update from fill_log, rolling lookback |
| TestPortfolioHeatMonitor | 5 | compute_heat with positions, can_add_risk allows, can_add_risk blocks, empty portfolio = 0 heat, heat with multiple positions |
| TestDrawdownScaler | 5 | no drawdown = 1.0, at threshold = 1.0, at full_stop = min_scale, linear interpolation, empty equity_log = 1.0 |
| TestEngineIntegration | 3 | engine with RiskManager sizes differently than 10%, engine without RiskManager = legacy, backward compatibility all existing tests |
| **Total** | **25** | |

**Helpers:**
- `_make_bar(close, high, low, open_, idx)` — MarketEvent factory
- `_make_fill(side, quantity, fill_price, day)` — FillEvent factory
- `_make_portfolio(initial_cash, fills)` — Portfolio pre-loaded with fills
- `_MockATRStrategy(current_atr)` — Mock strategy exposing current_atr

## Modified: `src/dashboard/callbacks.py` (~5 LOC)

### SWEEP_PARAMS update
```python
# Add risk params to strategies that support it
# (sweep doesn't use RiskManager directly — it's an engine-level concern)
```

No sweep param changes needed — RiskManager is engine-level, not strategy-level. The existing sweep system creates fresh engines per iteration via `create_engine()`, which will use default (no RiskManager) unless explicitly configured.

---

## Ausfuehrungsreihenfolge

1. **Wave 1:** PLAN-16A (RiskManager Core + Engine integration)
2. **Wave 2:** PLAN-16B + PLAN-16C (parallel — Kelly/Heat + DrawdownScaler, both depend only on 16A)
3. **Wave 3:** PLAN-16D (Tests, depends on all above)

## Neue Dateien (2)
- `src/risk_manager.py`
- `tests/test_risk_manager.py`

## Modifizierte Dateien (1)
- `src/engine.py` (add RiskManager parameter, delegate sizing)

## Nicht modifiziert
- `src/portfolio.py`, `src/execution.py`, `src/events.py`, `src/strategy/base.py`, alle Strategy-Module

## Verification
1. `pytest tests/test_risk_manager.py -v` — alle 25 Tests gruen
2. `pytest tests/ -v` — alle 507+ Tests gruen (482 + 25)
3. `pytest --cov=src tests/` — Coverage >= 90%
4. RiskManager sizing < legacy 10% for ATR-scaled trades
5. Kelly Criterion warmup falls back correctly
6. Portfolio Heat blocks when limit exceeded
7. Drawdown Scaler reduces size linearly during drawdowns
8. Engine without RiskManager = 100% backward compatible
