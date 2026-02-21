# Requirements: apex-backtest

**Defined:** 2026-02-21
**Core Value:** Mathematisch korrekte Backtesting-Ergebnisse — kein Look-Ahead Bias, cent-genaue PnL, realistische Marktfriktionen.

## v1 Requirements

### Event Architecture

- [ ] **EDA-01**: Engine verarbeitet Events streng sequentiell ueber eine zentrale collections.deque (FIFO)
- [ ] **EDA-02**: Vier Event-Typen existieren als frozen dataclasses: MarketEvent, SignalEvent, OrderEvent, FillEvent
- [ ] **EDA-03**: Backtest-Orchestrator dispatcht Events an die jeweils zustaendige Komponente ohne eigene Trading-Logik
- [ ] **EDA-04**: Jede Sweep-Iteration bekommt frisch instanziierte Komponenten (kein State-Sharing)

### Data Management

- [ ] **DATA-01**: DataHandler gibt Bars sequentiell per yield-Generator frei (eine Kerze pro Tick)
- [ ] **DATA-02**: Alle Preise werden am Eingangspunkt von float zu decimal.Decimal konvertiert (String-Konstruktor)
- [ ] **DATA-03**: OHLCV-Daten von yfinance (US-Aktien) und Alpha Vantage (Forex) abrufbar
- [ ] **DATA-04**: Lokales Parquet-Caching nach erstem API-Fetch (kein Re-Download bei jedem Run)
- [ ] **DATA-05**: Multi-Symbol-Support mit Datumsbereichsfilterung
- [ ] **DATA-06**: Gap-Handling durch Forward-Fill (Wochenenden, Feiertage, Missing Dates)
- [ ] **DATA-07**: Unterscheidung zwischen Raw und Adjusted Preisen (Split/Dividenden-Bereinigung)
- [ ] **DATA-08**: Ablehnung von Null-Volumen-Kerzen fuer Order-Execution
- [ ] **DATA-09**: Multi-Timeframe Bar-Alignment (1min bis Daily) in Lockstep

### Strategy Framework

- [ ] **STRAT-01**: Abstrakte BaseStrategy-Klasse mit calculate_signals(event) Hook
- [ ] **STRAT-02**: Signale: LONG, SHORT, EXIT pro Bar
- [ ] **STRAT-03**: Indikator-Zugriff ueber pandas-ta (SMA, EMA, ATR, RSI, Bollinger)
- [ ] **STRAT-04**: Reversal-Strategie (Mean Reversion) als Beispielimplementierung
- [ ] **STRAT-05**: Breakout-Strategie (Momentum) als Beispielimplementierung
- [ ] **STRAT-06**: FVG-Strategie (Fair Value Gap / ICT 3-Candle Pattern) als Beispielimplementierung
- [ ] **STRAT-07**: Parameter-Injektion bei Instanziierung (konfigurierbar)
- [ ] **STRAT-08**: Strategie sieht ausschliesslich historische Daten via DataHandler (kein Zukunftszugriff)

### Execution Simulation

- [ ] **EXEC-01**: Market-Orders werden zum Open der naechsten Bar gefuellt (NICHT Same-Bar Close)
- [ ] **EXEC-02**: Limit-Orders pruefen intra-Bar High/Low Range
- [ ] **EXEC-03**: Stop-Loss und Take-Profit mit intra-Bar Pruefung
- [ ] **EXEC-04**: Kommissions-Modell: Flat pro Trade + pro Share/Pip
- [ ] **EXEC-05**: Spread-Simulation: Bid/Ask bei Entry und Exit angewandt
- [ ] **EXEC-06**: Slippage-Modell: Prozentbasiert + Gap-Through-Fill am Open
- [ ] **EXEC-07**: Alle Berechnungen in decimal.Decimal (Fuellpreis, Kosten, Slippage)

### Portfolio Management

- [ ] **PORT-01**: Cash + Positions Tracking komplett in decimal.Decimal
- [ ] **PORT-02**: Prozentbasierte Positionsgroesse (Risk % vom aktuellen Equity)
- [ ] **PORT-03**: Long und Short Support
- [ ] **PORT-04**: Mark-to-Market Equity-Log nach jedem Bar
- [ ] **PORT-05**: Margin-Ueberwachung mit simulierter Zwangsliquidation bei Unterdeckung
- [ ] **PORT-06**: Strikte Ablehnung von Orders bei Null-Volumen oder unzureichendem Kapital
- [ ] **PORT-07**: FIFO-Methode fuer Multi-Position PnL-Attribution

### Performance Metrics

- [ ] **METR-01**: Net PnL, Total Return %, CAGR
- [ ] **METR-02**: Sharpe Ratio mit korrektem Annualisierungsfaktor pro Timeframe
- [ ] **METR-03**: Sortino Ratio
- [ ] **METR-04**: Maximum Drawdown (absolut + prozentual) + Drawdown-Dauer
- [ ] **METR-05**: Calmar Ratio
- [ ] **METR-06**: Win Rate, Profit Factor, Expectancy
- [ ] **METR-07**: Trade Count, Average Holding Time, Average R:R
- [ ] **METR-08**: Total Exposure Time (Prozent der Zeit im Markt)
- [ ] **METR-09**: Alle Metriken post-loop aus Equity-Log + Fill-Log berechnet

### Dashboard

- [ ] **DASH-01**: Dash/Plotly localhost Web-App
- [ ] **DASH-02**: Candlestick-Chart mit Buy/Sell Entry/Exit Markern
- [ ] **DASH-03**: Equity-Curve Chart
- [ ] **DASH-04**: Drawdown-Wasserfall-Diagramm
- [ ] **DASH-05**: KPI-Panel (Sharpe, Sortino, MDD, Calmar, Win%, PnL, Exposure)
- [ ] **DASH-06**: Interaktive Timeframe- und Strategie-Selektion
- [ ] **DASH-07**: Parameter-Sweep Heatmap

### Testing & QA

- [ ] **TEST-01**: pytest TDD-Struktur mit Causality-Tests (kein Zukunftszugriff)
- [ ] **TEST-02**: PnL-Verifikation mit exakter Decimal-Gleichheit (kein pytest.approx)
- [ ] **TEST-03**: Same-Bar-Fill Prevention Test (Fill-Timestamp = naechster Bar Open)
- [ ] **TEST-04**: Gap-Through Stop Test (Fill am Open, nicht am Stop-Preis)
- [ ] **TEST-05**: Null-Volumen Rejection Test
- [ ] **TEST-06**: Portfolio-Balance Invariante nach jedem Trade
- [ ] **TEST-07**: Mindestens 90% Test-Coverage

## v2 Requirements

### Advanced Analytics

- **ADV-01**: Monthly Returns Heatmap (Saisonalitaet)
- **ADV-02**: Rolling Sharpe / Rolling Drawdown Visualisierung
- **ADV-03**: Trade-Breakdown nach Session/Stunde/Wochentag
- **ADV-04**: MAE/MFE Analyse (Max Adverse/Favorable Excursion)
- **ADV-05**: Commission Sensitivity Sweep (0x, 0.5x, 1x, 2x Friction)

### Smart Money Concepts

- **SMC-01**: Order Block Detection
- **SMC-02**: Break of Structure (BOS) Detection
- **SMC-03**: FVG Mitigation Tracking (offene vs. geschlossene Gaps)

### Optimization

- **OPT-01**: Grid Search Parameter Sweep
- **OPT-02**: Walk-Forward Validation (Out-of-Sample)
- **OPT-03**: Robustness Report (Parameter-Sensitivitaet)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live-Trading / Broker-Anbindung | Reines Backtesting-Tool, kein Live-System |
| Kostenpflichtige Datenquellen | Null-Kosten-Betrieb, nur kostenlose APIs |
| Tick/Level-2 Simulation | Kostenlose APIs liefern keine Tick-Daten |
| ML/AI-Strategien | Erfordert separaten Research-Track, Fokus auf regelbasiert |
| Cloud/Multi-User/SaaS | Persoenliche Nutzung, localhost Dash |
| Options/Futures/Crypto-Derivate | Separate Margin-Regeln und Expiry-Logik |
| Mobile App | Desktop-Dashboard reicht |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EDA-01 | Phase 1 | Pending |
| EDA-02 | Phase 1 | Pending |
| EDA-03 | Phase 6 | Pending |
| EDA-04 | Phase 6 | Pending |
| DATA-01 | Phase 2 | Pending |
| DATA-02 | Phase 2 | Pending |
| DATA-03 | Phase 2 | Pending |
| DATA-04 | Phase 2 | Pending |
| DATA-05 | Phase 2 | Pending |
| DATA-06 | Phase 2 | Pending |
| DATA-07 | Phase 2 | Pending |
| DATA-08 | Phase 2 | Pending |
| DATA-09 | Phase 2 | Pending |
| STRAT-01 | Phase 3 | Pending |
| STRAT-02 | Phase 3 | Pending |
| STRAT-03 | Phase 3 | Pending |
| STRAT-04 | Phase 3 | Pending |
| STRAT-05 | Phase 3 | Pending |
| STRAT-06 | Phase 3 | Pending |
| STRAT-07 | Phase 3 | Pending |
| STRAT-08 | Phase 3 | Pending |
| EXEC-01 | Phase 4 | Pending |
| EXEC-02 | Phase 4 | Pending |
| EXEC-03 | Phase 4 | Pending |
| EXEC-04 | Phase 4 | Pending |
| EXEC-05 | Phase 4 | Pending |
| EXEC-06 | Phase 4 | Pending |
| EXEC-07 | Phase 4 | Pending |
| PORT-01 | Phase 5 | Pending |
| PORT-02 | Phase 5 | Pending |
| PORT-03 | Phase 5 | Pending |
| PORT-04 | Phase 5 | Pending |
| PORT-05 | Phase 5 | Pending |
| PORT-06 | Phase 5 | Pending |
| PORT-07 | Phase 5 | Pending |
| METR-01 | Phase 7 | Pending |
| METR-02 | Phase 7 | Pending |
| METR-03 | Phase 7 | Pending |
| METR-04 | Phase 7 | Pending |
| METR-05 | Phase 7 | Pending |
| METR-06 | Phase 7 | Pending |
| METR-07 | Phase 7 | Pending |
| METR-08 | Phase 7 | Pending |
| METR-09 | Phase 7 | Pending |
| DASH-01 | Phase 8 | Pending |
| DASH-02 | Phase 8 | Pending |
| DASH-03 | Phase 8 | Pending |
| DASH-04 | Phase 8 | Pending |
| DASH-05 | Phase 8 | Pending |
| DASH-06 | Phase 8 | Pending |
| DASH-07 | Phase 8 | Pending |
| TEST-01 | Phase 1 | Pending |
| TEST-02 | Phase 5 | Pending |
| TEST-03 | Phase 4 | Pending |
| TEST-04 | Phase 4 | Pending |
| TEST-05 | Phase 2 | Pending |
| TEST-06 | Phase 5 | Pending |
| TEST-07 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 54 total
- Mapped to phases: 54
- Unmapped: 0

---
*Requirements defined: 2026-02-21*
*Last updated: 2026-02-21 after initial definition*
