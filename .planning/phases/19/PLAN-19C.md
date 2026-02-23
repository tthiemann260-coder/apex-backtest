# PLAN-19C: TradeBuilder Integration + Tests

**Requirements:** JOURNAL-05, TEST-25 (partial — 25 tests)
**LOC:** ~500 (200 TradeBuilder + 300 Tests)
**Dependencies:** PLAN-19A + PLAN-19B
**Wave:** 3

## Neue Dateien

### 1. `src/journal/trade_builder.py` (~200 LOC)

#### TradeBuilder Klasse

**Konzept:** Observer-Pattern — wird vom Portfolio aufgerufen, baut aus Fill-Paaren (Open+Close) automatisch TradeJournalEntry-Objekte.

**__init__(strategy_name: str = "", timeframe: str = "")**
```python
self._strategy_name = strategy_name
self._timeframe = timeframe
self._open_trades: dict[str, dict] = {}   # symbol → {entry_fill, entry_bar_count, side}
self._completed: list[TradeJournalEntry] = []
self._bar_count: int = 0
self._price_highs: dict[str, Decimal] = {}   # symbol → running high for MFE
self._price_lows: dict[str, Decimal] = {}    # symbol → running low for MAE
```

**on_fill(fill: FillEvent, positions: dict[str, Position]) -> None**
- Hauptmethode — wird von Portfolio.process_fill() aufgerufen
- Logik:
  1. Pruefe ob `fill.symbol` in `_open_trades` ist
  2. **Wenn ja (Position wird geschlossen):**
     - Pop entry aus `_open_trades`
     - Berechne gross_pnl, net_pnl, net_pnl_pct, duration_bars
     - commission_total = entry_commission + fill.commission
     - slippage_total = entry_slippage + fill.slippage
     - spread_cost_total = entry_spread + fill.spread_cost
     - Erstelle TradeJournalEntry mit uuid.uuid4()
     - MAE/MFE aus _price_highs/_price_lows holen
     - Append zu self._completed
     - Cleanup _price_highs/_price_lows fuer Symbol
  3. **Wenn nein (neue Position geoeffnet):**
     - Speichere entry_fill state in `_open_trades[symbol]`
     - Initialisiere _price_highs[symbol] = fill.fill_price
     - Initialisiere _price_lows[symbol] = fill.fill_price

**Erkennungslogik (Opening vs Closing):**
```python
# Nach dem Fill: pruefe positions dict
pos = positions.get(fill.symbol)
was_open = fill.symbol in self._open_trades

if was_open and (pos is None or pos.quantity == Decimal("0")):
    # Position wurde komplett geschlossen → Trade abschliessen
    ...
elif was_open:
    # Position noch offen (partial close NICHT unterstuetzt in v1)
    # Ignorieren — Trade bleibt offen
    ...
else:
    # Neue Position geoeffnet
    ...
```

**on_bar(bar: MarketEvent, positions: dict[str, Position]) -> None**
- Wird pro Bar aufgerufen (nach Portfolio.update_equity)
- Tracked MAE/MFE fuer offene Positionen:
```python
self._bar_count += 1
symbol = bar.symbol
if symbol not in self._open_trades:
    return

entry_data = self._open_trades[symbol]
if entry_data["side"] == "LONG":
    # MFE = max favorable = highest high
    self._price_highs[symbol] = max(
        self._price_highs.get(symbol, bar.high), bar.high
    )
    # MAE = max adverse = lowest low
    self._price_lows[symbol] = min(
        self._price_lows.get(symbol, bar.low), bar.low
    )
else:  # SHORT
    # MFE = lowest low (favorable direction)
    self._price_lows[symbol] = min(
        self._price_lows.get(symbol, bar.low), bar.low
    )
    # MAE = highest high (adverse direction)
    self._price_highs[symbol] = max(
        self._price_highs.get(symbol, bar.high), bar.high
    )
```

**MAE/MFE Berechnung bei Close:**
```python
# LONG:
mae = entry_price - price_low   # negative excursion (positive = adverse distance)
mfe = price_high - entry_price  # positive excursion

# SHORT:
mae = price_high - entry_price  # adverse for shorts = price went up
mfe = entry_price - price_low   # favorable for shorts = price went down
```

**Properties:**
- `completed_trades -> list[TradeJournalEntry]` (copy)
- `open_trade_count -> int`
- `total_completed -> int`

### 2. Modifikation: `src/portfolio.py` (+15 LOC)

**Aenderungen in `__init__`:**
```python
self._trade_builder: Optional[TradeBuilder] = None
```

**Neues Property:**
```python
@property
def trade_builder(self) -> Optional[TradeBuilder]:
    return self._trade_builder

@trade_builder.setter
def trade_builder(self, builder: TradeBuilder) -> None:
    self._trade_builder = builder
```

**Aenderung in `process_fill()` — am Ende hinzufuegen:**
```python
def process_fill(self, fill: FillEvent) -> None:
    # ... existing code ...
    self._fill_log.append(fill)
    # ... existing processing ...

    # Notify trade builder (if attached)
    if self._trade_builder is not None:
        self._trade_builder.on_fill(fill, self._positions)
```

**Aenderung in `update_equity()` — am Ende hinzufuegen:**
```python
def update_equity(self, bar: MarketEvent) -> None:
    # ... existing code ...

    # Notify trade builder for MAE/MFE tracking
    if self._trade_builder is not None:
        self._trade_builder.on_bar(bar, self._positions)
```

### 3. Modifikation: `src/engine.py` (+10 LOC)

**Aenderung in `create_engine()`:**
```python
def create_engine(
    data_handler, strategy,
    ...,
    trade_builder=None,   # NEW parameter
) -> BacktestEngine:
    portfolio = Portfolio(...)
    if trade_builder is not None:
        portfolio.trade_builder = trade_builder
    ...
```

### 4. Modifikation: `.gitignore` (+1 LOC)
```
data/journal.db
```

### 5. `tests/test_journal.py` (~300 LOC, 25 Tests)

| Test-Klasse | Tests | Prueft |
|---|---|---|
| **TestTradeJournalEntry** | 4 | Konstruktion mit allen Feldern, Defaults, entry_to_dict/entry_from_dict Round-Trip, Decimal-Praezision |
| **TestEmotionEnums** | 3 | EntryEmotion Werte, ExitEmotion Werte, str(Enum) Serialisierung |
| **TestSetupTagEnums** | 2 | SetupType Werte, MarketCondition Werte |
| **TestTradeJournal (SQLite)** | 7 | Schema-Erstellung, save_trade + get_trade Round-Trip, save_trades Batch, get_all_trades mit Filter, annotate() Felder-Update, delete_trade, Decimal-Praezision in DB |
| **TestTradeBuilder** | 6 | Open+Close LONG Trade, Open+Close SHORT Trade, MAE/MFE LONG korrekt, MAE/MFE SHORT korrekt, open_trade_count, Multiple Trades Sequential |
| **TestPortfolioIntegration** | 3 | TradeBuilder via Portfolio.process_fill, MAE/MFE via update_equity, Engine-Kompatibilitaet mit create_engine(trade_builder=...) |
| **Total** | **25** | |

**Helpers:** `_make_fill()`, `_make_bar()` (analog bestehende Test-Patterns)

**Fixtures:**
```python
@pytest.fixture
def journal_db(tmp_path):
    """Temporary SQLite journal for tests."""
    db_path = str(tmp_path / "test_journal.db")
    journal = TradeJournal(db_path=db_path)
    yield journal
    journal.close()

@pytest.fixture
def sample_entry():
    """Sample TradeJournalEntry with all fields."""
    return TradeJournalEntry(
        trade_id="test-uuid-1234",
        symbol="AAPL",
        side="LONG",
        entry_time=datetime(2025, 1, 15, 10, 30),
        exit_time=datetime(2025, 1, 15, 14, 45),
        entry_price=Decimal("150.00"),
        exit_price=Decimal("155.00"),
        quantity=Decimal("10"),
        commission_total=Decimal("2.00"),
        slippage_total=Decimal("0.10"),
        spread_cost_total=Decimal("0.20"),
        gross_pnl=Decimal("50.00"),
        net_pnl=Decimal("47.70"),
        net_pnl_pct=Decimal("0.0318"),
        mae=Decimal("3.50"),
        mfe=Decimal("7.00"),
        duration_bars=34,
        timeframe="15min",
        strategy_name="ReversalStrategy",
        signal_strength=Decimal("0.70"),
    )
```

## Ausfuehrungsreihenfolge innerhalb PLAN-19C

1. Schreibe `src/journal/trade_builder.py` (TradeBuilder Klasse)
2. Modifiziere `src/portfolio.py` (+15 LOC: trade_builder Property + Hooks)
3. Modifiziere `src/engine.py` (+10 LOC: trade_builder Parameter in create_engine)
4. Modifiziere `.gitignore` (+1 LOC: data/journal.db)
5. Schreibe `tests/test_journal.py` (25 Tests)
6. `pytest tests/test_journal.py -v` — alle 25 gruen
7. `pytest tests/ -v` — alle 573+ Tests gruen (548 + 25)

## WICHTIG: Side-Feld Konvertierung

FillEvent.side ist `OrderSide.BUY/SELL` (Enum), aber TradeJournalEntry.side ist `"LONG"/"SHORT"` (String). In on_fill() beim Oeffnen MUSS konvertiert werden:
```python
side_str = "LONG" if fill.side == OrderSide.BUY else "SHORT"
self._open_trades[symbol] = {"entry_fill": fill, "side": side_str, ...}
```

## Risiken & Mitigationen

- **Portfolio.process_fill() Aenderung:** Minimal — nur 2 Zeilen am Ende jeder Methode. Bestehende Tests bleiben gruen weil trade_builder=None standardmaessig.
- **MAE/MFE Genauigkeit:** Tracking pro Bar (nicht pro Tick), was fuer Backtesting ausreichend ist. In echten Maerkten waere Tick-Granularitaet besser.
- **Partial Close:** Nicht unterstuetzt in v1 — Trade wird erst bei vollstaendigem Close erfasst. OK fuer Single-Symbol Backtesting.
