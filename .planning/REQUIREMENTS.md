# Requirements: apex-backtest v3.0

**Defined:** 2026-02-22
**Core Value:** ICT/Liquidity-basierte Strategien, regelbasierte Regime-Erkennung, fortgeschrittenes Risikomanagement und Multi-Asset-Backtesting.

## v3.0 Requirements

### ICT / Liquidity Concepts

- [ ] **ICT-01**: Liquidity Sweep Detection — Erkennung bullisher/bearisher Sweeps über/unter Swing-Levels mit ATR-Depth-Filter und Confirmation (Close zurück im Range)
- [ ] **ICT-02**: Inducement Detection — Identifizierung von IDM-Swing-Points (niedrigere Fractal-Strength) zwischen BOS und Entry-Zone als Trap-Indikator
- [ ] **ICT-03**: Kill Zones — Session-basierte Zeitfenster (London Open 02:00-05:00 ET, NY Open 07:00-10:00 ET, NY Close 14:00-16:00 ET) als Entry-Filter mit DST-korrekter Timezone-Behandlung
- [ ] **ICT-04**: Premium/Discount Zones — Equilibrium-Berechnung (50% Range-Midpoint), OTE-Zonen (61.8%-79% Retracement), Entry nur in Discount (Long) / Premium (Short)
- [ ] **ICT-05**: ICT Enhanced Strategy — Kombinierte ICT-Strategie (Sweep + IDM + Kill Zone + Premium/Discount + OB + FVG Confluence) als Erweiterung der bestehenden SMCStrategy

### Regime Detection

- [ ] **REG-01**: ATR Volatility Regime — ATR-basierte Klassifikation (LOW/NORMAL/HIGH) mit rollierendem Lookback-Fenster und konfigurierbaren Schwellwerten
- [ ] **REG-02**: ADX Trend Strength — ADX-Berechnung aus First Principles (kein externes Paket), Klassifikation in No Trend/Weak/Moderate/Strong
- [ ] **REG-03**: Combined Regime Classifier — 2D-Regime-Matrix (Volatility x Trend), 6 RegimeTypes (STRONG_TREND, MODERATE_TREND, WEAK_TREND, RANGING_LOW, RANGING_NORMAL, CHOPPY)
- [ ] **REG-04**: Regime-Gated Strategy — Decorator-Pattern (RegimeGatedStrategy wraps BaseStrategy), Signal-Unterdrueckung in nicht-zugelassenen Regimes, Engine bleibt unveraendert

### Risk Management

- [ ] **RISK-01**: RiskManager Module — Zentraler Orchestrator fuer Position Sizing und Risk Constraints (max concurrent positions, daily risk limit, portfolio heat)
- [ ] **RISK-02**: Fixed Fractional Sizing — Risk X% of Equity per Trade basierend auf Stop-Distance (ATR-Proxy), ersetzt hardcoded 10% in BacktestEngine
- [ ] **RISK-03**: Kelly Criterion — Adaptive Position Sizing aus Trade-Historie (Rolling Lookback, Half-Kelly Default), Fallback auf Fixed Fractional bei <20 Trades
- [ ] **RISK-04**: Portfolio Heat Monitor — Tracking des gesamten offenen Risikos ueber alle Positionen, Blockierung neuer Entries bei Heat > max_heat_pct
- [ ] **RISK-05**: Drawdown-Based Scaling — Automatische Positionsgroessen-Reduktion waehrend Drawdowns mit konfigurierbarem max_drawdown und min_scale

### Multi-Asset Foundation

- [ ] **MULTI-01**: Multi-Symbol Data Merge — Heap-basierter chronologischer Merge mehrerer DataHandler-Generatoren in einen einzigen Bar-Stream
- [ ] **MULTI-02**: Multi-Asset Engine — BacktestEngine Erweiterung fuer Multi-Symbol-Verarbeitung mit per-Symbol Strategy-Routing und shared Portfolio
- [ ] **MULTI-03**: Cross-Asset Correlation — Rolling-Korrelationsberechnung zwischen Asset-Equity-Kurven fuer Risk-Awareness
- [ ] **MULTI-04**: Per-Asset Position Limits — Maximale Position pro Symbol konfigurierbar, integriert in RiskManager

### Dashboard Integration

- [ ] **DASH-01**: Regime Overlay — Regime-Klassifikation als farbcodierter Hintergrund auf dem Haupt-Candlestick-Chart
- [ ] **DASH-02**: Risk Dashboard Tab — Portfolio Heat Gauge, Position Sizing Breakdown, Daily Risk Usage, Max Concurrent Positions
- [ ] **DASH-03**: Multi-Asset View — Per-Symbol Equity Curves ueberlagert, Korrelations-Matrix Heatmap

### Testing & QA

- [ ] **TEST-20**: ICT Unit Tests — Tests fuer Sweep/IDM/KillZone/PremiumDiscount mit synthetischen Daten und bekannten Ergebnissen
- [ ] **TEST-21**: Regime Detection Tests — Tests fuer ATR-Regime, ADX-Klassifikation und Combined Classifier mit kontrollierter Volatilitaet/Trend
- [ ] **TEST-22**: Risk Management Tests — Kelly Warmup, Portfolio Heat Limits, Drawdown Scaling, Max Concurrent, Daily Risk Reset
- [ ] **TEST-23**: Multi-Asset Merge Tests — Chronologische Korrektheit, verschiedene Trading Hours, leere Generatoren
- [ ] **TEST-24**: Coverage >= 90% — Gesamte Codebase inkl. aller neuen Module

## Out of Scope (v3.0)

| Feature | Reason |
|---------|--------|
| Strategy Builder UI | Geplant fuer v3.1 |
| Trading Journal | Geplant fuer v3.1 |
| Live-Trading | Reines Backtesting-Tool |
| ML/AI Regime Detection | Regelbasiert only |
| Crypto-Maerkte | Fokus auf Stocks/Forex/Indizes |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ICT-01..05 | Phase 14 | Pending |
| REG-01..04 | Phase 15 | Pending |
| RISK-01..05 | Phase 16 | Pending |
| MULTI-01..04 | Phase 17 | Pending |
| DASH-01..03 | Phase 18 | Pending |
| TEST-20..24 | Distributed | Pending |

**Coverage:**
- v3.0 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0

---
*Requirements defined: 2026-02-22*
