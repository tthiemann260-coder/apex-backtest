# Requirements: apex-backtest v4.0 — Strategy Builder, Trading Journal & Bayesian Optimization

**Milestone:** v4.0
**Total:** 28 requirements
**Phases:** 5 (19-23)

## Trading Journal — Foundation

- [ ] **JOURNAL-01**: TradeJournalEntry Dataclass — frozen dataclass mit trade_id (UUID), symbol, side, entry/exit price+time, quantity, commissions, slippage, gross/net PnL (Decimal), MAE, MFE, duration_bars, timeframe, strategy_name, signal_strength
- [ ] **JOURNAL-02**: Emotion Taxonomy — EntryEmotion (CALM, CONFIDENT, ANXIOUS, FOMO, REVENGE, BORED, EXCITED, HESITANT) und ExitEmotion (DISCIPLINED, IMPATIENT, GREEDY, FEARFUL, OVERRODE_SYSTEM) als str(Enum)
- [ ] **JOURNAL-03**: Tag & Setup System — setup_type Enum (FVG, ORDER_BLOCK, BREAKOUT, REVERSAL, KILL_ZONE, LIQUIDITY_SWEEP, SMC_BOS, CUSTOM), market_condition Enum, free-form tags list
- [ ] **JOURNAL-04**: SQLite Persistence — TradeJournal Klasse mit sqlite3 stdlib, Decimal-Adapter (str round-trip), Indexes auf symbol/strategy/emotion/exit_time, CRUD + annotate()
- [ ] **JOURNAL-05**: TradeBuilder Integration — Observer-Pattern in Portfolio, _open_trades dict, MAE/MFE Tracking via _price_highs/_price_lows, automatische TradeJournalEntry bei Position Close

## Trading Journal — Dashboard & Analytics

- [ ] **JOURNAL-06**: Journal Analytics Module — emotion_vs_pnl(), hourly_win_rate(), setup_performance(), streak_analysis(), rule_adherence_impact(), alle via SQL GROUP BY
- [ ] **JOURNAL-07**: Dashboard Journal Tab — DataTable (sortierbar/filterbar, Annotation Sidebar), PnL Calendar Heatmap, Emotion vs PnL Chart, MAE/MFE Scatter, Hour/Weekday Heatmap, Setup Performance Table

## Strategy Builder — Core Engine

- [ ] **BUILD-01**: Indicator Block System — INDICATOR_REGISTRY mit IndicatorDef Klasse, compute(closes, highs, lows, **params), output_keys, param_schema. Unterstuetzt: RSI, SMA, EMA, ATR, MACD, BBANDS, STOCH, ADX
- [ ] **BUILD-02**: Condition Engine — CompareCondition (left, operator, right) mit gt/lt/gte/lte/eq/crosses_above/crosses_below. LogicCondition (and/or/not, operands). Recursive Evaluation mit current/previous Dicts
- [ ] **BUILD-03**: Strategy Serialization — StrategyDefinition Pydantic v2 Model (version, meta, indicators[], entry/exit_long/short, warmup_bars, signal_strength). JSON Import/Export
- [ ] **BUILD-04**: Runtime Compiler — compile_strategy(StrategyDefinition) → type[BaseStrategy] via type() Metaclass (kein exec/eval). Closure captures compiled indicator_defs + condition objects. Vollstaendig EDA-kompatibel
- [ ] **BUILD-05**: Strategy Validator — validate_strategy() → ValidationResult (is_valid, errors[], warnings[], auto_warmup). Structural Check (refs existieren) + Semantic Check (exit vorhanden, warmup ausreichend)
- [ ] **BUILD-06**: Built-in Templates — 6 Strategien als JSON-Dicts: Golden Cross, RSI Mean Reversion, MACD Momentum, BB Squeeze Breakout, Stoch+RSI Combo, ADX Trend Filter

## Strategy Builder — Dashboard UI

- [ ] **BUILD-07**: Strategy Builder Tab — Neuer Dashboard-Tab mit Meta/Template-Bereich, dynamischen Indicator-Rows (ADD/REMOVE), 4 Condition-Sections (Entry/Exit Long/Short), dcc.Store fuer Form-State
- [ ] **BUILD-08**: Template Loading — Dropdown mit 6 Templates, Load-Button fuellt alle Form-Felder, Save-Button exportiert als JSON-Datei (dcc.Download)
- [ ] **BUILD-09**: Live Validation & Run — Echtzeit-Validierung bei jeder Aenderung, Fehler/Warnungen als farbige ListGroup, "Validate & Run Backtest" Button kompiliert + fuehrt aus

## Bayesian Optimization

- [ ] **OPT-04**: Optuna Integration — OptunaOptimizer Klasse wrapping Engine._run als Objective, TPESampler (multivariate=True, seed), suggest_int/float/categorical fuer Strategy-Parameter
- [ ] **OPT-05**: Multi-Objective Support — NSGA-II Sampler fuer Sharpe + Max Drawdown Pareto-Optimierung, best_trials (Pareto-Front), min_trades Filter
- [ ] **OPT-06**: Walk-Forward Optimization — WFOOrchestrator mit N rolling Windows (IS/OOS Split), frischer Optuna Study pro Window, OOS-Validation, Efficiency Ratio Berechnung
- [ ] **OPT-07**: Pruning & Performance — MedianPruner mit intermediate Sharpe Reporting (quartalsweise), TrialPruned Exception, JournalFileBackend fuer Persistenz
- [ ] **OPT-08**: Dashboard Optimization Tab — Neuer Tab mit Optimization History, Parameter Importance (FANOVA), Parallel Coordinate, Contour Plot, WFO Efficiency Report. Alle via optuna.visualization (native Plotly)

## Testing & QA

- [ ] **TEST-25**: Journal Unit Tests — TradeJournalEntry, Emotion Enums, SQLite CRUD, TradeBuilder Integration, Analytics Queries (~25 tests)
- [ ] **TEST-26**: Strategy Builder Unit Tests — IndicatorRegistry, Conditions, Compiler, Validator, Templates, JSON Round-Trip (~30 tests)
- [ ] **TEST-27**: Optimization Unit Tests — Objective Wrapping, Search Spaces, WFO Windows, Pruning, Multi-Objective (~20 tests)
- [ ] **TEST-28**: Integration Tests — Builder→Engine Pipeline, Journal→Analytics→Dashboard Pipeline, Optuna→WFO→Dashboard Pipeline (~15 tests)
- [ ] **TEST-29**: Coverage >= 85% (target 87%, gap akzeptabel fuer Dash Callback Wrappers)

## Dependencies (neue Pakete)

| Package | Version | Purpose | Cost |
|---------|---------|---------|------|
| optuna | 4.x | Bayesian Optimization | Free |
| pydantic | 2.x | Strategy Schema Validation | Free |
| scikit-learn | 1.x | FANOVA Parameter Importance | Free (bereits vorhanden) |

---
*Created: 2026-02-23*
