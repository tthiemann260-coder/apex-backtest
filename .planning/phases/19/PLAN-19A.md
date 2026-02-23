# PLAN-19A: Trading Journal Data Models

**Requirements:** JOURNAL-01, JOURNAL-02, JOURNAL-03
**LOC:** ~150
**Dependencies:** Keine
**Wave:** 1 (parallel ausfuehrbar)

## Neue Dateien

### 1. `src/journal/__init__.py` (~2 LOC)
```python
# Trading Journal package
```

### 2. `src/journal/models.py` (~150 LOC)

#### Enums

**EntryEmotion(str, Enum):** (JOURNAL-02)
```python
CALM = "CALM"
CONFIDENT = "CONFIDENT"
ANXIOUS = "ANXIOUS"
FOMO = "FOMO"
REVENGE = "REVENGE"
BORED = "BORED"
EXCITED = "EXCITED"
HESITANT = "HESITANT"
```

**ExitEmotion(str, Enum):** (JOURNAL-02)
```python
DISCIPLINED = "DISCIPLINED"
IMPATIENT = "IMPATIENT"
GREEDY = "GREEDY"
FEARFUL = "FEARFUL"
OVERRODE_SYSTEM = "OVERRODE_SYSTEM"
```

**SetupType(str, Enum):** (JOURNAL-03)
```python
FVG = "FVG"
ORDER_BLOCK = "ORDER_BLOCK"
BREAKOUT = "BREAKOUT"
REVERSAL = "REVERSAL"
KILL_ZONE = "KILL_ZONE"
LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
SMC_BOS = "SMC_BOS"
CUSTOM = "CUSTOM"
```

**MarketCondition(str, Enum):** (JOURNAL-03)
```python
TRENDING_UP = "TRENDING_UP"
TRENDING_DOWN = "TRENDING_DOWN"
RANGING = "RANGING"
HIGH_VOL = "HIGH_VOL"
LOW_VOL = "LOW_VOL"
PRE_NEWS = "PRE_NEWS"
POST_NEWS = "POST_NEWS"
```

#### TradeJournalEntry (JOURNAL-01)

**Dataclass (NOT frozen — manual fields are mutable):**
```python
@dataclass
class TradeJournalEntry:
    # --- Identity (auto-filled) ---
    trade_id: str                        # UUID4, str(uuid.uuid4())
    symbol: str
    side: str                            # "LONG" or "SHORT"

    # --- Execution (all Decimal, auto-filled from FillEvent pairs) ---
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    commission_total: Decimal            # sum of entry + exit commissions
    slippage_total: Decimal              # sum of entry + exit slippage
    spread_cost_total: Decimal           # sum of entry + exit spread
    gross_pnl: Decimal                   # before friction
    net_pnl: Decimal                     # after all friction
    net_pnl_pct: Decimal                 # net_pnl / (entry_price * quantity)

    # --- Excursion (auto-tracked during open position) ---
    mae: Decimal = Decimal("0")          # Maximum Adverse Excursion
    mfe: Decimal = Decimal("0")          # Maximum Favorable Excursion
    duration_bars: int = 0

    # --- Context (auto-filled from strategy/engine) ---
    timeframe: str = ""
    strategy_name: str = ""
    signal_strength: Decimal = Decimal("0")

    # --- Manual Annotation (user-filled post-trade) ---
    setup_type: str = ""                 # SetupType value or custom string
    market_condition: str = ""           # MarketCondition value
    tags: list[str] = field(default_factory=list)
    emotion_entry: str = ""              # EntryEmotion value
    emotion_exit: str = ""               # ExitEmotion value
    rule_followed: bool = True
    notes: str = ""
    rating: int = 0                      # 1-5 stars, 0 = unrated
```

**Entscheidung: NOT frozen** weil manuelle Felder nach Trade-Close annotiert werden (via Dashboard). Auto-Felder werden einmal gesetzt und aendern sich danach nicht.

#### Hilfsfunktionen

```python
def entry_to_dict(entry: TradeJournalEntry) -> dict:
    """Convert entry to JSON-serializable dict. Decimal → str, datetime → isoformat."""

def entry_from_dict(d: dict) -> TradeJournalEntry:
    """Reconstruct entry from dict. str → Decimal, isoformat → datetime."""
```

## Nicht modifiziert
- Keine bestehenden Dateien werden geaendert
- Rein additive Aenderung (neues Package)
