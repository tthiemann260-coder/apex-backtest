# Roadmap: apex-backtest

## v1.0 — Event-Driven Backtesting Engine (SHIPPED 2026-02-22)

8 phases, 54 requirements, 250 tests, 91% coverage. [Full archive](milestones/v1.0-ROADMAP.md)

---

## v2.0 — Advanced Analytics, SMC & Optimization

**Created:** 2026-02-22
**Phases:** 5 (continuing from Phase 9)
**Requirements:** 30 mapped

---

### Phase 9: Advanced Analytics

**Goal:** Erweitere das Dashboard um Monthly Returns Heatmap, Rolling Sharpe/Drawdown, Trade-Breakdown (Hour/Weekday/Session), MAE/MFE-Analyse und Commission Sensitivity Sweep.
**Dependencies:** v1.0 complete (equity_log, fill_log, metrics, dashboard)
**Requirements:** ADV-01, ADV-02, ADV-03, ADV-04, ADV-05, ADV-06, ADV-07, ADV-08, ADV-09

#### Success Criteria
1. Monthly Returns Heatmap zeigt Year x Month Grid mit RdYlGn Farbskala, zmid=0, korrekte monatliche Renditen.
2. Rolling Sharpe + Rolling Drawdown als Zeitreihen-Charts mit konfigurierbarem Fenster (20/60/90/252).
3. Trade-Breakdown zeigt 6 Bar-Charts (Count + PnL je Stunde/Wochentag/Session) mit Gruen/Rot-Kodierung.
4. MAE/MFE Scatter-Plots zeigen Wins (gruen) und Losses (rot) mit korrekter Excursion-Berechnung.
5. Commission Sweep zeigt 4 Metriken (Sharpe/PnL/WinRate/MaxDD) ueber 5 Friction-Level.

---

### Phase 10: Smart Money Concepts

**Goal:** Implementiere Order Block Detection, Break of Structure (BOS/CHOCH), FVG Mitigation Tracking als erweitertes Strategie-Framework und eine kombinierte SMC-Strategie.
**Dependencies:** Phase 9 (Analytics fuer SMC-Performance-Analyse)
**Requirements:** SMC-01, SMC-02, SMC-03, SMC-04, TEST-10

#### Success Criteria
1. Order Blocks werden mit ATR-basiertem Displacement-Filter erkannt; kein Lookahead Bias (Confirmation nach N Bars).
2. Fractal-basierte Swing High/Low Erkennung mit konfigurierbarer `strength`; BOS und CHOCH Events korrekt klassifiziert.
3. FVG Tracker verwaltet aktive Gaps mit State Machine (OPEN->TOUCHED->MITIGATED/INVERTED); Memory-Limit und Expiry.
4. SMC-Strategie kombiniert OB+BOS+FVG fuer Entry/Exit und generiert korrekte SignalEvents.
5. Mindestens 30 Unit-Tests fuer SMC-Module mit synthetischen Daten.

---

### Phase 11: Optimization Engine

**Goal:** Baue Rolling Walk-Forward Validation, Parameter Sensitivity Analysis, Monte Carlo Trade Shuffling und einen zusammenfassenden Robustness Report.
**Dependencies:** Phase 9 (Metrics), Phase 10 (SMC als Strategie zum Validieren)
**Requirements:** OPT-01, OPT-02, OPT-03, OPT-04, TEST-11

#### Success Criteria
1. Walk-Forward Loop rollt mit konfigurierbarem Train/Test-Split (default 80/20); kein Indicator-State-Leakage zwischen Fenstern.
2. Parameter Sensitivity erzeugt Stabilitaets-Heatmap bei ±10/20/30% Perturbation; Sharpe-Degradation messbar.
3. Monte Carlo shuffelt 1000 Trade-Sequenzen; p5/p95 Equity und Max Drawdown berechnet.
4. Robustness Report fasst WFO Efficiency Ratio, MC Percentile und Parameter-Stabilitaet zusammen.
5. OOS Sharpe (mean across WFO windows) wird als primaere Validierungs-Metrik reported.

---

### Phase 12: Portfolio Enhancement

**Goal:** Ermoegliche Multi-Strategy-Portfolios mit gewichteter Allokation, Per-Strategy Attribution, Benchmark-Vergleich (Buy-and-Hold) und Alpha/Beta/Information Ratio.
**Dependencies:** Phase 9 (Analytics), v1.0 Portfolio
**Requirements:** PORT-10, PORT-11, PORT-12, PORT-13, TEST-12

#### Success Criteria
1. PortfolioRouter aggregiert Signale mehrerer Strategien mit konfigurierbaren Gewichten; Gesamt-Exposure begrenzt.
2. Per-Strategy Attribution trackt PnL, Sharpe und Win Rate getrennt; Dashboard zeigt Strategie-Vergleich.
3. Buy-and-Hold Benchmark-Equity wird neben Strategie-Equity geplottet.
4. Alpha, Beta und Information Ratio relativ zum Benchmark korrekt berechnet (via empyrical-reloaded).
5. Portfolio-Balance Invariante gilt auch bei mehreren gleichzeitigen Strategien.

---

### Phase 13: Report Export

**Goal:** Generiere professionelle HTML- und PDF-Reports aus Backtest-Ergebnissen mit konfigurierbarem Jinja2-Template.
**Dependencies:** Phase 9 (Charts), Phase 11 (Robustness), Phase 12 (Benchmark)
**Requirements:** RPT-01, RPT-02, RPT-03, TEST-13, TEST-14

#### Success Criteria
1. `generate_report(result, metrics, format='html')` erzeugt interaktiven HTML-Report mit allen Charts und KPIs.
2. `generate_report(result, metrics, format='pdf')` erzeugt statischen PDF-Report mit eingebetteten PNG-Charts.
3. Jinja2-Template ist konfigurierbar (Titel, Branding, welche Sektionen enthalten).
4. HTML/PDF-Reports enthalten: Equity Curve, Drawdown, Monthly Heatmap, KPIs, Trade-Liste, Robustness Summary.
5. pytest --cov=src tests/ >= 90% Coverage ueber die gesamte Codebase inkl. neuer Module.

---

## Dependency Graph

```
v1.0 (shipped)
    |
    Phase 9 (Advanced Analytics) ---- keine v1.0-Aenderungen noetig
    |         |
    |         Phase 10 (SMC)
    |         |
    |         Phase 11 (Optimization) - braucht Strategien zum Validieren
    |
    Phase 12 (Portfolio Enhancement) -- parallel zu 10/11 moeglich
    |
    Phase 13 (Report Export) ---------- braucht 9 + 11 + 12
```

## Requirements Coverage Summary

| Phase | Requirements | Count |
|-------|-------------|-------|
| 9 | ADV-01..09 | 9 |
| 10 | SMC-01..04, TEST-10 | 5 |
| 11 | OPT-01..04, TEST-11 | 5 |
| 12 | PORT-10..13, TEST-12 | 5 |
| 13 | RPT-01..03, TEST-13, TEST-14 | 5 |
| **Total** | | **29 + 1 distributed** |

## Critical Pitfalls (from Research)

- **Decimal->float:** Nur an der Visualisierungsgrenze konvertieren (Plotly/pandas). Nie rolling() auf Decimal.
- **SMC Lookahead:** OB Confirmation braucht N Bars — Signal erst bei Arrival der Confirmation-Bars emittieren.
- **Walk-Forward Leakage:** Alle Indicator-State pro Fenster zuruecksetzen. Warm-up innerhalb des Training-Windows.
- **WeasyPrint Windows:** GTK3-Abhaengigkeit — WSL2 oder pdfkit als Fallback.
- **Multi-Strategy Exposure:** Einzelnes shared Portfolio verhindert unmöglichen Leverage.
- **FVG Memory:** Stale Gaps nach N Bars expiren. GC-Pass auf active dict.

---
*Roadmap created: 2026-02-22*
*30 v2 requirements mapped across 5 phases.*
