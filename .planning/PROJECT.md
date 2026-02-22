# apex-backtest

## What This Is

Eine professionelle, ereignisgesteuerte Backtesting-Engine in Python fuer die systematische Auswertung von Daytrading- und Swingtrading-Strategien (Reversal, Breakout, FVG) auf Forex- und US-Aktienmaerkten. Ergaenzt durch ein interaktives Dash-Dashboard zur Visualisierung von KPIs und Handelslogiken. Gebaut fuer den persoenlichen Gebrauch mit Fokus auf 100% Korrektheit und Null-Kosten-Betrieb.

## Core Value

Die Engine muss mathematisch korrekte Backtesting-Ergebnisse liefern — kein Look-Ahead Bias, kein Survivorship Bias, cent-genaue PnL-Berechnungen durch decimal.Decimal und realistische Marktfriktionen.

## Current State

**Version:** v2.0 (shipped 2026-02-22)
**Tests:** 427 passing, 90% coverage
**Launch:** `python -m src.dashboard` from project root

### v2.0 Shipped Features (on top of v1.0)
- Advanced Analytics: Monthly heatmap, rolling Sharpe/DD, trade breakdown, MAE/MFE, commission sweep
- Smart Money Concepts: Order blocks, BOS/CHOCH, FVG state machine, combined SMC strategy
- Optimization Engine: Walk-forward validation, parameter sensitivity, Monte Carlo shuffling, robustness report
- Portfolio Enhancement: Multi-strategy routing, attribution, buy-and-hold benchmark, Alpha/Beta/IR
- Report Export: Interactive HTML and static PDF reports with Jinja2 templates

<details>
<summary>v1.0 Features (shipped 2026-02-22)</summary>

- Event-driven architecture (4 event types, FIFO queue)
- DataHandler (yield-generator, Decimal, Parquet cache, yfinance, gap-fill)
- 3 strategies (Reversal, Breakout, FVG) with pandas-ta
- Realistic execution (market/limit/stop, slippage, commission, spread)
- Portfolio (Decimal, FIFO PnL, margin monitoring, forced liquidation)
- Metrics (Sharpe, Sortino, MDD, Calmar, CAGR, win rate, exposure)
- Dash dashboard (candlestick, equity, drawdown, KPIs, sweep heatmap)
</details>

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

## v3.0 Milestone — ICT/Liquidity, Regime Detection, Risk Management & Multi-Asset

### Active Requirements (26 total)
- **ICT/Liquidity (5):** Liquidity Sweeps, Inducement, Kill Zones, Premium/Discount, ICT Strategy
- **Regime Detection (4):** ATR Volatility, ADX Trend, Combined Classifier, Regime-Gated Strategy
- **Risk Management (5):** RiskManager, Fixed Fractional, Kelly Criterion, Portfolio Heat, DD Scaling
- **Multi-Asset (4):** Bar Merge, Multi-Asset Engine, Cross-Asset Correlation, Per-Asset Limits
- **Dashboard (3):** Regime Overlay, Risk Dashboard, Multi-Asset View
- **Testing (5):** ICT Tests, Regime Tests, Risk Tests, Multi-Asset Tests, Coverage >= 90%

### Planned for v3.1
- Strategy Builder (visueller UI-Konfigurator)
- Trading Journal (Notizen, Emotionen, Lernpunkte)
- Dashboard UX Improvements

---
*Last updated: 2026-02-22 — v3.0 milestone started*
