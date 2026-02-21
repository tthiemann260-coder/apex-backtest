# apex-backtest

## What This Is

Eine professionelle, ereignisgesteuerte Backtesting-Engine in Python fuer die systematische Auswertung von Daytrading- und Swingtrading-Strategien (Reversal, Breakout, FVG) auf Forex- und US-Aktienmaerkten. Ergaenzt durch ein interaktives Dash-Dashboard zur Visualisierung von KPIs und Handelslogiken. Gebaut fuer den persoenlichen Gebrauch mit Fokus auf 100% Korrektheit und Null-Kosten-Betrieb.

## Core Value

Die Engine muss mathematisch korrekte Backtesting-Ergebnisse liefern — kein Look-Ahead Bias, kein Survivorship Bias, cent-genaue PnL-Berechnungen durch decimal.Decimal und realistische Marktfriktionen.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Event-Driven Architecture mit zentraler Event-Queue
- [ ] DataHandler mit Yield-Generator (sequentielle Kerzenfreigabe)
- [ ] decimal.Decimal fuer alle Finanzberechnungen
- [ ] Realistische Execution (Slippage + Kommissionen)
- [ ] Portfolio mit Edge-Case-Handling (Null-Volumen, Margin, Gaps)
- [ ] Point-in-Time Daten (Raw vs. Adjusted Preise)
- [ ] Kostenlose Marktdaten-API-Anbindung (Yahoo Finance, Alpha Vantage)
- [ ] Multi-Timeframe Support (1min bis Daily)
- [ ] Forex + US-Aktien Support
- [ ] Strategie-Framework (Reversal, Breakout, FVG als Beispiele)
- [ ] pytest TDD mit Causality-Checks und PnL-Verifikation
- [ ] Dash-Dashboard mit Sharpe, Sortino, Max DD, Calmar, Exposure Time
- [ ] Candlestick-Chart mit Buy/Sell-Markern
- [ ] Drawdown-Wasserfall-Diagramm
- [ ] Parameter-Sweep Heatmap

### Out of Scope

- Live-Trading / Broker-Anbindung — reines Backtesting-Tool, kein Live-System
- Kostenpflichtige Datenquellen — nur kostenlose APIs
- Multi-User / Auth — rein persoenliche Nutzung
- Mobile App — lokales Desktop-Dashboard reicht
- Machine-Learning Strategien — Fokus auf regelbasierte Strategien

## Context

- Zielmärkte: Forex (EUR/USD, GBP/USD, etc.) und US-Aktien (NYSE, NASDAQ)
- Zeitrahmen: 1min, 5min, 15min, 1h, 4h, Daily — Multi-Timeframe-Analyse
- Strategietypen: Reversal (Mean Reversion), Breakout (Momentum), Fair Value Gaps (ICT/SMC)
- Datenquellen: Yahoo Finance (yfinance), Alpha Vantage Free Tier
- Betrieb: Lokaler Rechner, Windows 11, Python 3.12+
- Dashboard: Browser-basiert via Dash/Plotly, localhost

## Constraints

- **Tech Stack**: Python 3.12+, Dash/Plotly, pytest — keine externen kostenpflichtigen Dienste
- **Precision**: decimal.Decimal fuer alle Finanzmath — kein float
- **Architecture**: Streng ereignisgesteuert — kein vektorisierter Trading-Code
- **Cost**: Null Kosten — nur kostenlose APIs und Open-Source-Libraries
- **Isolation**: Komplett getrennt vom LYNX-Projekt — keine gemeinsamen Abhaengigkeiten

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Event-Driven statt vektorisiert | Verhindert Look-Ahead Bias durch sequentielle Verarbeitung | — Pending |
| decimal.Decimal statt float | Verhindert kumulative IEEE-754 Rundungsfehler | — Pending |
| Dash statt Streamlit | Enterprise-Skalierung fuer komplexe Callbacks, Plotly-native | — Pending |
| Yahoo Finance + Alpha Vantage | Kostenlos, zuverlaessig, breite Marktabdeckung | — Pending |
| pytest + TDD | Mathematischer Beweis der Korrektheit durch Tests | — Pending |

---
*Last updated: 2026-02-21 after initialization*
