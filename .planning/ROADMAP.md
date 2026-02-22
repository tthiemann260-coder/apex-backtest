# Roadmap: apex-backtest

## v1.0 — Event-Driven Backtesting Engine (SHIPPED 2026-02-22)

8 phases, 54 requirements, 250 tests, 91% coverage. [Full archive](milestones/v1.0-ROADMAP.md)

---

## v2.0 — Advanced Analytics, SMC & Optimization (SHIPPED 2026-02-22)

5 phases, 30 requirements, 427 tests, 90% coverage. [Full archive](milestones/v2.0-ROADMAP.md)

---

## v3.0 — ICT/Liquidity, Regime Detection, Risk Management & Multi-Asset

**Created:** 2026-02-22
**Phases:** 5 (continuing from Phase 14)
**Requirements:** 26 mapped

---

### Phase 14: ICT / Liquidity Concepts

**Goal:** Erweitere das SMC-Framework um Liquidity Sweeps, Inducement Detection, Kill Zones, Premium/Discount Zones und eine kombinierte ICT Enhanced Strategy.
**Dependencies:** v2.0 complete (SMC package: SwingDetector, StructureTracker, FVGTracker, OrderBlockDetector)
**Requirements:** ICT-01, ICT-02, ICT-03, ICT-04, ICT-05, TEST-20

#### Success Criteria
1. LiquiditySweepDetector erkennt bullische/bearische Sweeps mit ATR-Depth-Filter; Confirmation via Close zurueck im Range.
2. InducementDetector identifiziert IDM-Punkte (niedrigere Fractal-Strength) zwischen BOS und OB-Zone.
3. KillZoneFilter klassifiziert Bars nach Session (London/NY Open/Close) mit DST-korrekter Timezone-Behandlung.
4. PremiumDiscountZone berechnet Equilibrium und OTE-Zonen korrekt; Entry-Filter blockiert Longs in Premium.
5. ICTStrategy kombiniert alle 5 Komponenten zu einem konfidenzbasierten Entry-System; mindestens 25 Unit-Tests.

---

### Phase 15: Regime Detection

**Goal:** Implementiere regelbasierte Marktregime-Erkennung (ATR-Volatilitaet + ADX-Trendstaerke) und ein Decorator-Pattern fuer regime-gesteuerte Strategien.
**Dependencies:** Phase 14 (ICT als Teststrategie fuer Regime-Gating)
**Requirements:** REG-01, REG-02, REG-03, REG-04, TEST-21

#### Success Criteria
1. ATRRegimeClassifier klassifiziert LOW/NORMAL/HIGH Volatilitaet mit rollendem Lookback; Warmup-Guard bei kurzer Historie.
2. ADXClassifier berechnet ADX, +DI, -DI aus First Principles (kein externes Paket); Thresholds 20/25/40.
3. RegimeClassifier kombiniert ATR + ADX zu 6 RegimeTypes; MarketRegime frozen dataclass.
4. RegimeGatedStrategy wraps BaseStrategy und unterdrueckt Signale in nicht-zugelassenen Regimes; Engine unveraendert.
5. Mindestens 20 Unit-Tests mit synthetischen Daten fuer kontrollierte Regime-Transitionen.

---

### Phase 16: Advanced Risk Management

**Goal:** Ersetze das hardcoded 10% Position Sizing durch ein vollstaendiges Risk Management Modul mit Kelly Criterion, Portfolio Heat, Drawdown Scaling und Daily Risk Limits.
**Dependencies:** v2.0 Engine (Portfolio, ExecutionHandler), Phase 15 optional
**Requirements:** RISK-01, RISK-02, RISK-03, RISK-04, RISK-05, TEST-22

#### Success Criteria
1. RiskManager als zentraler Orchestrator: can_trade() Gate + compute_quantity() Sizing.
2. Fixed Fractional Sizing basierend auf ATR-Stop-Distance ersetzt 10% Naive-Sizing.
3. Kelly Criterion adaptiv aus Rolling-Trade-Historie (Half-Kelly Default), Fallback bei <20 Trades.
4. PortfolioHeatMonitor trackt offenes Risiko; blockiert neue Entries bei Heat > max_heat_pct.
5. Drawdown-Based Scaling reduziert Positionsgroesse linear bei Drawdown; min_scale = 25%.
6. Mindestens 20 Unit-Tests fuer alle Risk Constraints und Edge Cases.

---

### Phase 17: Multi-Asset Foundation

**Goal:** Ermoegliche Backtesting ueber mehrere Symbole gleichzeitig mit chronologischem Bar-Merge, shared Portfolio und Cross-Asset Korrelation.
**Dependencies:** Phase 16 (RiskManager fuer Multi-Asset Risk), v2.0 DataHandler
**Requirements:** MULTI-01, MULTI-02, MULTI-03, MULTI-04, TEST-23

#### Success Criteria
1. merge_bars() merged N DataHandler-Generatoren chronologisch korrekt via heapq; deterministische Reihenfolge bei gleichen Timestamps.
2. MultiAssetEngine dispatched Bars an per-Symbol Strategien; shared Portfolio trackt alle Positionen.
3. Rolling-Korrelation (60-90 Bar Fenster) zwischen Asset-Equity-Kurven berechnet.
4. Per-Asset Position Limits konfigurierbar und in RiskManager integriert.
5. Mindestens 20 Unit-Tests inkl. verschiedene Trading Hours, leere Generatoren, Korrelationsberechnung.

---

### Phase 18: Dashboard Integration (v3.0)

**Goal:** Integriere Regime Overlay, Risk Dashboard und Multi-Asset View in das bestehende Dash Dashboard.
**Dependencies:** Phase 15 (Regime), Phase 16 (Risk), Phase 17 (Multi-Asset)
**Requirements:** DASH-01, DASH-02, DASH-03, TEST-24

#### Success Criteria
1. Regime Overlay: Farbcodierter Hintergrund auf Candlestick-Chart zeigt aktuelle Regime-Klassifikation.
2. Risk Dashboard Tab: Portfolio Heat Gauge (Plotly Indicator), Position Sizing Breakdown, Daily Risk Usage Bar.
3. Multi-Asset View: Per-Symbol Equity Curves ueberlagert (Plotly, normalisiert auf 100%), Korrelations-Matrix Heatmap.
4. pytest --cov=src tests/ >= 90% Coverage ueber die gesamte Codebase inkl. v3.0 Module.

---

## Dependency Graph

```
v2.0 (shipped)
    |
    Phase 14 (ICT/Liquidity) -------- erweitert SMC package
    |
    Phase 15 (Regime Detection) ----- nutzt ICT als Teststrategie
    |
    Phase 16 (Risk Management) ------ parallel zu 15 moeglich
    |
    Phase 17 (Multi-Asset) ---------- braucht RiskManager
    |
    Phase 18 (Dashboard v3.0) ------- braucht 15 + 16 + 17
```

## Requirements Coverage Summary

| Phase | Requirements | Count |
|-------|-------------|-------|
| 14 | ICT-01..05, TEST-20 | 6 |
| 15 | REG-01..04, TEST-21 | 5 |
| 16 | RISK-01..05, TEST-22 | 6 |
| 17 | MULTI-01..04, TEST-23 | 5 |
| 18 | DASH-01..03, TEST-24 | 4 |
| **Total** | | **26** |

## Critical Pitfalls (from Research)

- **Kill Zone DST:** Nutze `zoneinfo.ZoneInfo("America/New_York")` — behandelt EDT/EST automatisch.
- **Kelly Warmup:** <20 Trades = instabil. Fallback auf Fixed Fractional.
- **ADX Lag:** ADX signalisiert Trend 2-5 Bars zu spaet. Nutze ADX-Richtung (rising/falling) zusaetzlich.
- **Regime Whipsaws:** Hysterese — Regime muss N Bars bestehen vor Switch.
- **Multi-Symbol Heap:** Deterministische Sortierung bei gleichen Timestamps durch Secondary Key (Symbol-Name).
- **Portfolio Heat Stops:** RiskManager muss Stop-Prices pro Position tracken (nicht in Portfolio gespeichert).

---
*Roadmap created: 2026-02-22*
*26 v3.0 requirements mapped across 5 phases.*
