# Requirements: apex-backtest v2.0

**Defined:** 2026-02-22
**Core Value:** Erweiterte Analyse, SMC-Strategien, Walk-Forward-Validierung und professionelle Reporting-Faehigkeiten.

## v2 Requirements

### Advanced Analytics

- [x] **ADV-01**: Monthly Returns Heatmap — Monatliche Renditen als Year x Month Heatmap (Plotly, RdYlGn, zmid=0)
- [x] **ADV-02**: Rolling Sharpe Ratio — Rollendes Fenster (konfigurierbar: 20/60/90/252 Bars), annualisiert, als Zeitreihen-Chart
- [x] **ADV-03**: Rolling Drawdown — Maximaler Drawdown im rollenden Fenster, als gefuellter Zeitreihen-Chart
- [x] **ADV-04**: Trade-Breakdown nach Stunde — Anzahl und PnL pro Stunde (0-23), als Bar-Chart
- [x] **ADV-05**: Trade-Breakdown nach Wochentag — Anzahl und PnL pro Wochentag, als Bar-Chart
- [x] **ADV-06**: Trade-Breakdown nach Session — Pre-Market/Morning/Lunch/Afternoon/After-Hours, als Bar-Chart
- [x] **ADV-07**: MAE Analyse — Max Adverse Excursion pro Trade als Scatter-Plot (MAE vs Final PnL)
- [x] **ADV-08**: MFE Analyse — Max Favorable Excursion pro Trade als Scatter-Plot (MFE vs Final PnL)
- [x] **ADV-09**: Commission Sensitivity Sweep — Backtest mit 0x/0.5x/1x/2x/3x Friction-Multiplikator, Metriken-Vergleich

### Smart Money Concepts

- [x] **SMC-01**: Order Block Detection — Erkennung bullisher/bearisher OBs mit ATR-basiertem Displacement-Filter
- [x] **SMC-02**: Break of Structure (BOS) — Fractal-basierte Swing-Erkennung + BOS/CHOCH Events
- [x] **SMC-03**: FVG Mitigation Tracking — State Machine (OPEN/TOUCHED/MITIGATED/INVERTED) mit konfigurierbarem Threshold
- [x] **SMC-04**: SMC Strategy — Konkrete Strategie die OB+BOS+FVG kombiniert fuer Entry/Exit Signale

### Optimization

- [x] **OPT-01**: Rolling Walk-Forward Validation — Festes Training-Window das vorwaerts rollt, OOS-Test pro Fenster
- [x] **OPT-02**: Parameter Sensitivity Analysis — Parameter-Perturbation (±10/20/30%), Stabilitaets-Heatmap
- [x] **OPT-03**: Monte Carlo Trade Shuffling — 1000 Permutationen der Trade-Sequenz, p5/p95 Equity/Drawdown
- [x] **OPT-04**: Robustness Report — Zusammenfassung: WFO Efficiency, MC Percentile, Parameter-Stabilitaet

### Portfolio Enhancement

- [ ] **PORT-10**: Multi-Strategy Portfolio — Mehrere Strategien gleichzeitig auf einem Portfolio mit gewichteter Allokation
- [ ] **PORT-11**: Strategy Attribution — Per-Strategy PnL, Sharpe, Win Rate Tracking und Reporting
- [ ] **PORT-12**: Benchmark Comparison — Buy-and-Hold Benchmark neben Strategie-Equity anzeigen
- [ ] **PORT-13**: Alpha/Beta/Information Ratio — Berechnung relativ zum Benchmark

### Report Export

- [ ] **RPT-01**: HTML Report — Interaktiver HTML-Report mit allen Charts und KPIs (Jinja2 Template)
- [ ] **RPT-02**: PDF Report — Statischer PDF-Report mit eingebetteten Chart-Bildern (WeasyPrint/pdfkit)
- [ ] **RPT-03**: Report Template — Konfigurierbares Jinja2-Template fuer Branding/Layout

### Testing & QA

- [x] **TEST-10**: SMC Unit Tests — Tests fuer OB/BOS/FVG-Detection mit synthetischen Daten
- [x] **TEST-11**: Walk-Forward Isolation — Kein Indicator-State-Leakage zwischen WFO-Fenstern
- [ ] **TEST-12**: Multi-Strategy Invariante — Portfolio-Balance korrekt bei mehreren gleichzeitigen Strategien
- [ ] **TEST-13**: Report Generation — HTML/PDF Report ohne Exception generierbar
- [ ] **TEST-14**: Coverage >= 90% — Gesamte Codebase inkl. neuer Module

## Out of Scope (v2)

| Feature | Reason |
|---------|--------|
| Live-Trading | Reines Backtesting-Tool |
| ML/AI Strategien | Regelbasiert only |
| Tick/Level-2 Daten | Kostenlose APIs |
| Cloud/Multi-User | Persoenliche Nutzung |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ADV-01..09 | Phase 9 | Complete |
| SMC-01..04 | Phase 10 | Pending |
| OPT-01..04 | Phase 11 | Pending |
| PORT-10..13 | Phase 12 | Pending |
| RPT-01..03 | Phase 13 | Pending |
| TEST-10..14 | Distributed | Pending |

**Coverage:**
- v2 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0

---
*Requirements defined: 2026-02-22*
