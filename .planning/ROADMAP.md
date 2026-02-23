# Roadmap: apex-backtest

## v1.0 — Event-Driven Backtesting Engine (SHIPPED 2026-02-22)

8 phases, 54 requirements, 250 tests, 91% coverage. [Full archive](milestones/v1.0-ROADMAP.md)

---

## v2.0 — Advanced Analytics, SMC & Optimization (SHIPPED 2026-02-22)

5 phases, 30 requirements, 427 tests, 90% coverage. [Full archive](milestones/v2.0-ROADMAP.md)

---

## v3.0 — ICT/Liquidity, Regime Detection, Risk Management & Multi-Asset (SHIPPED 2026-02-23)

5 phases, 26 requirements, 548 tests, 87% coverage. [Full archive](milestones/v3.0-ROADMAP.md)

---

## v4.0 — Strategy Builder, Trading Journal & Bayesian Optimization

**Status:** In Progress
**Phases:** 5 (Phase 19-23)
**Requirements:** 28
**Start:** 2026-02-23

### Phase 19: Trading Journal — Foundation
**Goal:** Erstelle das Trading-Journal-Datenmodell mit automatischer Trade-Erfassung aus FillEvents, Emotion-Taxonomie, Tag-System und SQLite-Persistenz.
**Requirements:** JOURNAL-01, JOURNAL-02, JOURNAL-03, JOURNAL-04, JOURNAL-05
**Dependencies:** Keine (Hook in Portfolio.process_fill)

### Phase 20: Trading Journal — Dashboard & Analytics
**Goal:** Implementiere Journal-Analytics (Emotion vs PnL, Setup Performance, Streak Analysis) und den Dashboard Journal Tab mit 7 interaktiven Panels.
**Requirements:** JOURNAL-06, JOURNAL-07, TEST-25
**Dependencies:** Phase 19

### Phase 21: Strategy Builder — Core Engine
**Goal:** Baue das No-Code Strategy Builder System: Indicator-Registry, Condition-Engine, JSON-Serialisierung, Runtime-Compiler (type() statt eval) und 6 Built-in Templates.
**Requirements:** BUILD-01, BUILD-02, BUILD-03, BUILD-04, BUILD-05, BUILD-06
**Dependencies:** Keine (neues Package)

### Phase 22: Strategy Builder — Dashboard UI
**Goal:** Implementiere den visuellen Strategy-Konfigurator im Dashboard: dynamische Indicator/Condition-Rows, Template Loading/Saving, Live-Validierung und direktes Backtesting.
**Requirements:** BUILD-07, BUILD-08, BUILD-09, TEST-26
**Dependencies:** Phase 21

### Phase 23: Bayesian Optimization & Integration
**Goal:** Integriere Optuna fuer automatische Parameteroptimierung mit TPE Sampler, Multi-Objective Pareto, Walk-Forward Validation, Pruning und Dashboard-Visualisierungen.
**Requirements:** OPT-04, OPT-05, OPT-06, OPT-07, OPT-08, TEST-27, TEST-28, TEST-29
**Dependencies:** Phasen 19-22 (nutzt Journal + Builder als Test-Subjects)

### Dependency Graph

```
Phase 19 (Journal Foundation) ──────────────────┐
    |                                            |
Phase 20 (Journal Dashboard) ──────────────────┐ |
                                                | |
Phase 21 (Builder Core) ────────────────────┐  | |
    |                                        |  | |
Phase 22 (Builder Dashboard) ────────────┐  |  | |
                                          |  |  | |
                                          v  v  v v
                                    Phase 23 (Optuna + Integration)
```

Note: Phasen 19+21 sind parallel ausfuehrbar (keine gegenseitigen Abhaengigkeiten).

---
