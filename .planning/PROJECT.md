# apex-backtest

## What This Is

Eine professionelle, ereignisgesteuerte Backtesting-Engine in Python fuer die systematische Auswertung von Daytrading- und Swingtrading-Strategien (Reversal, Breakout, FVG) auf Forex- und US-Aktienmaerkten. Ergaenzt durch ein interaktives Dash-Dashboard zur Visualisierung von KPIs und Handelslogiken. Gebaut fuer den persoenlichen Gebrauch mit Fokus auf 100% Korrektheit und Null-Kosten-Betrieb.

## Core Value

Die Engine muss mathematisch korrekte Backtesting-Ergebnisse liefern — kein Look-Ahead Bias, kein Survivorship Bias, cent-genaue PnL-Berechnungen durch decimal.Decimal und realistische Marktfriktionen.

## Current State

**Version:** v1.0 (shipped 2026-02-22)
**Status:** Fully operational
**Tests:** 250 passing, 91% coverage
**Launch:** `python -m src.dashboard` from project root

### Shipped Features
- Event-driven architecture (4 event types, FIFO queue)
- DataHandler (yield-generator, Decimal, Parquet cache, yfinance, gap-fill)
- 3 strategies (Reversal, Breakout, FVG) with pandas-ta
- Realistic execution (market/limit/stop, slippage, commission, spread)
- Portfolio (Decimal, FIFO PnL, margin monitoring, forced liquidation)
- Metrics (Sharpe, Sortino, MDD, Calmar, CAGR, win rate, exposure)
- Dash dashboard (candlestick, equity, drawdown, KPIs, sweep heatmap)

## Next Milestone Goals (v2.0 — TBD)

Potential directions:
- Advanced Analytics (Monthly Returns Heatmap, Rolling Sharpe, MAE/MFE)
- Smart Money Concepts (Order Blocks, BOS, FVG Mitigation Tracking)
- Optimization (Grid Search Sweep, Walk-Forward Validation, Robustness Report)
- Commission Sensitivity Analysis

## Constraints

- **Tech Stack**: Python 3.12+, Dash/Plotly, pytest — keine externen kostenpflichtigen Dienste
- **Precision**: decimal.Decimal fuer alle Finanzmath — kein float
- **Architecture**: Streng ereignisgesteuert — kein vektorisierter Trading-Code
- **Cost**: Null Kosten — nur kostenlose APIs und Open-Source-Libraries
- **Isolation**: Komplett getrennt vom LYNX-Projekt

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Event-Driven statt vektorisiert | Verhindert Look-Ahead Bias | Validated v1.0 |
| decimal.Decimal statt float | Verhindert Rundungsfehler | Validated v1.0 |
| Dash statt Streamlit | Enterprise Callbacks, Plotly-native | Validated v1.0 |
| Yahoo Finance + Alpha Vantage | Kostenlos, zuverlaessig | Validated v1.0 |
| pytest + TDD | Beweis der Korrektheit | Validated v1.0 |

## Out of Scope

- Live-Trading / Broker-Anbindung
- Kostenpflichtige Datenquellen
- Multi-User / Auth
- Mobile App
- ML/AI-Strategien (regelbasiert only)

---
*Last updated: 2026-02-22 — v1.0 shipped*
