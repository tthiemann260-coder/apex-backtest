# Pitfalls Research: apex-backtest

> **Purpose:** Prevent critical mistakes during design and implementation of the apex-backtest
> event-driven engine. Every pitfall here has destroyed real backtesting projects. Read before
> making architectural decisions.
>
> **Project:** Event-Driven Python Backtesting Engine — Forex + US Stocks — 1min to Daily
> **Stack:** Python 3.12+, decimal.Decimal, yfinance, Alpha Vantage, Dash/Plotly

---

## Critical Pitfalls (Project-Breaking)

These pitfalls produce results that look valid but are completely fictitious. They invalidate
every strategy result and cannot be patched after the fact — the architecture must prevent them
from day one.

---

### 1. Look-Ahead Bias

**Description:**
The strategy sees data from the future when making decisions in the past. This is the single
most common and most devastating backtesting error. It manifests in dozens of subtle ways beyond
the obvious `.shift(-1)` mistake. A strategy that uses tomorrow's open to generate today's signal
will show a Sharpe Ratio of 3.0+ for any trivial strategy — the results are completely fictional.

Common sources in Python:
- Using `df['close'].shift(-1)` to simulate "buying at next bar's open"
- Calculating indicators on the full dataset before slicing — e.g., computing a 200-day SMA on
  all data, then replaying bar by bar while reading from the pre-computed column
- Normalizing or scaling features (e.g., min-max) on the full dataset before the backtest loop
- Computing ATR, Bollinger Bands, or RSI on the full dataframe and storing results in a column,
  then reading those columns during replay — the indicator already knows future volatility
- Joining a news sentiment column to OHLCV data where the sentiment timestamp is slightly ahead
  of the bar's close time
- Using `df.resample()` to create higher-timeframe bars inside the replay loop — resampling
  aggregates data that hasn't "happened yet" at the current bar
- Signal generation that references `bar[i+1]` anywhere in the codebase

**Warning Signs:**
- Sharpe Ratio above 2.5 on the very first strategy you test — real edge is rare
- Equity curve that almost never has drawdowns
- Win rate above 70% on a trend-following strategy without obvious reason
- Strategy performs equally well on both rising and falling markets simultaneously
- Unit tests do not explicitly assert that future bars are inaccessible

**Prevention:**
- Enforce the yield-generator DataHandler: `yield` exactly one bar at a time, in strict
  chronological order. The strategy's `calculate_signals()` receives only the current bar and
  whatever historical window has been explicitly buffered.
- NEVER pre-compute indicators on the full DataFrame. Compute them incrementally inside the
  event loop using only bars seen so far. Use a rolling buffer (e.g., `collections.deque(maxlen=N)`).
- Write `test_causality.py` as the very first test file. Assert that after processing bar `t`,
  the DataHandler cannot yield bar `t+1` or later through any accessible interface.
- Audit every indicator calculation: RSI, SMA, EMA, ATR, Bollinger Bands — each must be
  recomputed incrementally from a historical buffer, not read from a pre-filled column.
- Code review checklist: grep for `.shift(`, `iloc[-`, `df[`, `resample(` inside any strategy
  or execution module.

**Phase Mapping:** Phase 1 (Core Architecture) — DataHandler design. Must be resolved before
any strategy code is written. The causality test must be the first test committed.

---

### 2. Survivorship Bias

**Description:**
The backtest only tests strategies on assets that survived to the present day. When you pull
a list of S&P 500 stocks from today and test a mean-reversion strategy on all of them
historically, you automatically exclude every stock that went bankrupt, was delisted, or was
acquired between 2010 and today. The stocks that survived are, by definition, the ones that
recovered from drawdowns — making mean-reversion look far better than it actually was.

For US stocks, the S&P 500 constituent list changes ~20-25 times per year. Testing on today's
constituents going back 10 years means testing only on "winners."

For Forex, this is less severe (major pairs persist) but still relevant for exotic pairs and
currency crises (e.g., TRY, ARS collapse).

**Warning Signs:**
- Running strategy on "all S&P 500 stocks" using a list pulled from Wikipedia or a static file
- yfinance returning clean, continuous data for every ticker in your list — it silently drops
  delisted tickers or returns partial data
- No mention of point-in-time constituent lists anywhere in the codebase
- Strategy performance is dramatically better on large-cap stocks than small-cap

**Prevention:**
- For personal use at single-asset or small-universe level: explicitly document which assets
  are tested and note survivorship limitation in results commentary.
- NEVER pull "all S&P 500 stocks" from a static list as a universe for multi-asset strategies.
- If multi-asset testing is added later: use point-in-time index constituent lists (available
  from Quandl WIKI, Sharadar, or manually maintained CSV files).
- Flag in the DataHandler: log a warning when a requested ticker returns less data than
  expected — this may indicate the ticker was delisted mid-period.
- For Forex: test only liquid major pairs (EUR/USD, GBP/USD, USD/JPY, etc.) and avoid exotic
  pairs with limited historical data.

**Phase Mapping:** Phase 1 (Data Layer) and Phase 3 (Strategy Implementation). Document the
limitation clearly before adding multi-asset support.

---

### 3. Ignoring the Bar Timestamp Convention (Open vs. Close Execution)

**Description:**
A OHLCV bar's timestamp represents different things depending on the data source and convention:
- Yahoo Finance daily bars: timestamp = bar open time, but the bar includes the full day's data
- 1-minute bars: timestamp = bar open time

The classic bug: a strategy generates a signal using the CLOSE price of bar at timestamp T,
then executes the trade at the OPEN of bar T (same bar). This means the strategy saw the bar's
close before deciding whether to enter at the open — impossible in reality. The correct behavior
is to execute at the OPEN of bar T+1.

This is a form of look-ahead bias but specific enough to warrant its own entry. It is
responsible for some of the best-looking backtests on daily timeframes.

**Warning Signs:**
- Fill event timestamp equals the signal event timestamp
- FillEvent uses the same bar's close price for execution
- Equity curves on daily data are unrealistically smooth
- No explicit "fill on next bar open" logic in ExecutionHandler

**Prevention:**
- Establish and document the bar timestamp convention for each data source before writing
  any execution code.
- Rule: signals generated from bar T are only executable at bar T+1's open.
- In the ExecutionHandler: when processing an OrderEvent generated at bar T, hold it until
  the next MarketEvent arrives (bar T+1), then fill at bar T+1's open price.
- Write a dedicated test: generate a signal at bar 5's close, assert the FillEvent timestamp
  equals bar 6's open time, assert the fill price equals bar 6's open price.
- For intraday (1min, 5min): the same rule applies — signal on bar close, fill on next bar open.

**Phase Mapping:** Phase 1 (ExecutionHandler design). The fill-on-next-bar rule must be
established in the architecture before any execution tests are written.

---

### 4. Treating the Event Queue as Thread-Safe When It Is Not

**Description:**
Python's `collections.deque` is thread-safe for `append()` and `popleft()` operations, but
the event loop itself is not transactionally safe if multiple producers push events
simultaneously. More critically: if any part of the codebase processes events out of order —
for example, batch-processing all FillEvents before any new MarketEvents — causal ordering
breaks and results become unreliable.

In a single-threaded event loop this is usually avoided naturally, but becomes a problem when:
- Adding parallelism for parameter sweeps and inadvertently sharing state
- Using async code alongside the synchronous event queue
- Strategy generates multiple signals in one bar and they are processed non-deterministically

**Warning Signs:**
- Parameter sweep uses multiprocessing without properly isolating each run's Portfolio state
- Strategy occasionally generates different results on repeated runs of identical data
- Any `threading` or `asyncio` import in strategy or portfolio modules
- Multiple strategies share a single Portfolio instance during parallel sweep

**Prevention:**
- Keep the main event loop strictly single-threaded and synchronous during a single backtest run.
- For parameter sweeps: use `multiprocessing.Pool` where each worker gets a fully isolated,
  freshly instantiated engine (DataHandler + Portfolio + Strategy + ExecutionHandler).
  NEVER share state between sweep workers.
- Never pass a Portfolio instance between threads.
- Document in code: "This class is NOT thread-safe. Each backtest run must use its own instance."
- Test: run identical data twice sequentially and assert byte-identical equity curve output.

**Phase Mapping:** Phase 2 (Engine Core) and Phase 5 (Parameter Sweep). Isolation must be
explicit in the sweep runner design.

---

### 5. Float Arithmetic Accumulation in Financial Calculations

**Description:**
Using Python `float` (IEEE 754 double precision) for trade P&L accumulates errors that compound
over thousands of trades. A single pip in Forex (EUR/USD = 0.00001) cannot be represented
exactly in binary floating point. After 10,000 trades, the cumulative rounding error can reach
tens of pips — enough to flip strategies from profitable to unprofitable or vice versa.

Classic example:
```python
# This produces 5.551115123125783e-17, not 0.0
sum(0.1 for _ in range(10)) - 1.0
```

For a Forex backtest running 50,000 trades over 5 years on 1-minute data, float errors
are not academic — they produce wrong final balances.

**Warning Signs:**
- `float` used anywhere in portfolio.py, execution.py, or metrics.py
- `Decimal(0.01)` instead of `Decimal('0.01')` — the float constructor defeats the purpose
- PnL unit tests pass with `pytest.approx()` instead of exact equality
- Balance after round-trip trade (buy then sell same size) does not exactly equal initial balance

**Prevention:**
- This project already mandates `decimal.Decimal` for all financial math — enforce it strictly.
- Use string constructor exclusively: `Decimal('1.23456')`, never `Decimal(1.23456)`.
- Add a linting rule or `grep` pre-commit hook to detect `float(` in financial modules.
- Unit test: open a position and close it at the same price, assert `portfolio.cash == initial_cash`
  with exact `Decimal` equality, not `approx()`.
- Quantize to the correct precision per market:
  - Forex: `Decimal('0.00001')` (5 decimal places)
  - US Stocks: `Decimal('0.01')` (2 decimal places, cents)
  - Position sizes: `Decimal('1')` for whole shares, `Decimal('0.01')` for fractional

**Phase Mapping:** Phase 1 (Foundation). The `Decimal` pattern must be established in `events.py`
and `portfolio.py` before any calculation code is written.

---

## Serious Pitfalls (Results-Corrupting)

These pitfalls produce results that are plausible but systematically optimistic. They survive
casual inspection but fail under rigorous testing.

---

### 1. Overfitting / Curve Fitting

**Description:**
Optimizing strategy parameters (e.g., SMA periods, RSI thresholds, ATR multipliers) on the
same data used to evaluate performance. The strategy learns the noise of the historical data
rather than a genuine market edge. With enough parameters and enough optimization iterations,
any strategy can achieve a perfect Sharpe Ratio on historical data — and fail completely on
new data.

The parameter sweep heatmap planned for this project is specifically at risk: running a sweep
over 100 parameter combinations and reporting the best-performing set is curve fitting if no
out-of-sample validation exists.

**Warning Signs:**
- Strategy has more than 5 tunable parameters
- Parameter sweep result shows a sharp isolated peak (one combination dramatically outperforms
  all neighbors) — this is noise, not edge
- No out-of-sample test period defined before running the sweep
- Strategy was modified multiple times based on backtest results from the same data

**Prevention:**
- Walk-Forward Analysis: split data into train/test windows (e.g., train on 2018-2022,
  test on 2023-2024). Never touch the test window until parameter selection is finalized.
- Anchored Walk-Forward: move the test window forward in 6-month increments, always training
  on all prior data. Average the out-of-sample results.
- When reading the parameter sweep heatmap: look for broad plateaus, not sharp peaks.
  A robust parameter set performs reasonably across a wide range of neighbors.
- Limit tunable parameters: a strategy with 3 well-reasoned parameters is more trustworthy
  than one with 10 parameters discovered through grid search.
- Document the parameter selection rationale BEFORE running the backtest.

**Phase Mapping:** Phase 5 (Parameter Sweep and Dashboard). The walk-forward split must be
defined in the test configuration before the sweep is run.

---

### 2. Slippage and Commission Underestimation

**Description:**
Using zero or unrealistically low slippage and commissions inflates returns dramatically,
especially for high-frequency strategies on 1-minute data. On 1-minute Forex data, a strategy
making 50 trades per day with 0 slippage might show 40% annual return — reduce that to a
realistic 0.5 pip slippage and it becomes -10%.

Sources of underestimation:
- Using bid/ask midpoint as fill price when in reality you pay the spread
- Ignoring the fact that limit orders may not fill at all (assuming 100% fill rate)
- Using constant slippage when real slippage increases with position size and volatility
- Ignoring overnight financing costs (swap rates) for Forex positions held past rollover
- Ignoring borrowing costs for short stock positions

**Warning Signs:**
- Strategy performs equally well on 1-minute and daily data (high-frequency strategies
  should be much more sensitive to friction)
- Slippage model is `Decimal('0')` or a flat 0.0001 regardless of market conditions
- No commission model at all
- Strategy makes 20+ round trips per day but shows positive net P&L after costs

**Prevention:**
- Forex realistic costs:
  - EUR/USD bid-ask spread: 0.5–1.5 pips in liquid hours, 2–5 pips off-hours
  - Commission: 0 (spread-based for retail), or $3.5–7/lot for ECN
  - Slippage on market orders: 0.3–1.0 pips additional during news events
- US Stocks realistic costs:
  - Commission: $0–1 per trade (most retail brokers), or $0.005/share minimum
  - Bid-ask spread: $0.01–0.05 for large-cap, $0.10–0.50 for small-cap
  - Slippage: 0.05%–0.15% of trade value for market orders
- In ExecutionHandler: implement configurable slippage model with percentage-based AND
  fixed pip/cent slippage. Default to conservative (high) estimates.
- Add a friction sensitivity test: run the same strategy with 0 friction, realistic friction,
  and 2x friction. Any strategy whose profitability disappears under realistic friction has no edge.
- Model the bid-ask spread as a fixed cost even without explicit spread data.

**Phase Mapping:** Phase 2 (ExecutionHandler). Conservative defaults must be set before
any strategy results are reported.

---

### 3. Unrealistic Position Sizing and Leverage

**Description:**
Backtests often use constant position sizing (e.g., always trade 1 lot or 100 shares)
regardless of account equity. This produces results that cannot be reproduced: if a strategy
starts with $10,000 and uses 1 lot EUR/USD positions throughout a 5-year backtest, the risk
per trade as a percentage of equity changes dramatically as the account grows or shrinks.

Forex-specific: using margin/leverage without modeling margin calls. A 50:1 leveraged Forex
account with a 2% adverse move triggers a margin call. If the backtest doesn't model this,
it allows trades that would have been force-closed in reality.

**Warning Signs:**
- `position_size = Decimal('100')` hardcoded anywhere in strategy or portfolio
- No `account_equity` reference in position sizing logic
- Maximum drawdown in the backtest never triggers a margin call despite high leverage
- Strategy uses 10:1+ leverage on intraday Forex without any margin monitoring

**Prevention:**
- Implement percentage-based position sizing: risk X% of current equity per trade (e.g., 1-2%).
  `position_size = (equity * risk_per_trade) / (stop_loss_distance * pip_value)`
- Portfolio must track current equity (cash + unrealized P&L) in real-time.
- Implement margin monitoring in Portfolio: if margin usage exceeds a configurable threshold,
  reject new orders and log a warning (or simulate forced liquidation).
- For Forex: calculate actual pip value based on current exchange rate and lot size, in `Decimal`.
- Unit test: verify that position size decreases proportionally as equity decreases after losses.

**Phase Mapping:** Phase 2 (Portfolio) and Phase 3 (Strategy base class).

---

### 4. Ignoring Market Hours, Holidays, and Session Effects

**Description:**
Forex and stock markets have fundamentally different operating hours, and backtests that ignore
this produce incorrect results:

- Forex: 24/5 market with distinct session volatility patterns. London-New York overlap
  (13:00-17:00 UTC) is fundamentally different from Asian session (00:00-09:00 UTC). A breakout
  strategy parameterized on London-session data behaves differently during Asian session.
- US Stocks: 09:30–16:00 ET only. Pre-market and after-hours data from yfinance exists but
  has completely different liquidity characteristics. A 1-minute strategy that accidentally
  uses pre-market data (08:00 ET bars) will see artificial gaps and low-volume moves.
- Market holidays: yfinance returns no bars for US market holidays. If your DataHandler does
  not detect and handle gaps, the strategy may interpret a 3-day gap (e.g., Thanksgiving) as
  a signal.
- Forex weekend gap: EUR/USD closes Friday ~22:00 UTC and reopens Sunday ~22:00 UTC. The
  opening price often gaps from Friday's close. If the strategy holds a position over the
  weekend, the gap is real P&L impact and must be modeled.

**Warning Signs:**
- DataHandler does not filter by session (yields all bars including pre/post-market)
- No holiday calendar used anywhere in the data pipeline
- Strategy generates signals during known low-liquidity periods (e.g., 22:00-01:00 UTC for Forex)
- Equity curve shows irregular large moves on Monday opens without explanation (weekend gap)
- 1-minute data from yfinance includes bars before 09:30 ET

**Prevention:**
- For US Stocks 1-minute data: filter bars to 09:30–15:59 ET before yielding from DataHandler.
  Use `pandas_market_calendars` library or a simple hardcoded NYSE session filter.
- For Forex: document which session(s) the strategy is designed for. Consider adding a
  `session_filter` parameter that restricts signals to specific UTC hour ranges.
- Weekend gap modeling: when the DataHandler detects a gap greater than 2 calendar days,
  log it and optionally model the gap as a risk event for open positions.
- Add a test: verify that DataHandler does not yield any bars outside the configured market
  session for US stocks.

**Phase Mapping:** Phase 1 (DataHandler) for session filtering; Phase 3 (Strategy) for
session-aware signal generation.

---

### 5. Incorrect Handling of Adjusted vs. Unadjusted Prices

**Description:**
yfinance returns adjusted close prices by default that account for stock splits and dividends.
Using adjusted prices for signal generation combined with unadjusted prices for P&L calculation
(or vice versa) produces incorrect results. This is particularly severe for high-dividend stocks
or stocks that underwent large splits.

Example: Apple (AAPL) had a 4:1 split in August 2020. The pre-split price was ~$500. Post-split
adjusted close prices before August 2020 are divided by 4, showing ~$125. If a strategy uses
adjusted prices for its SMA but calculates position value using unadjusted share prices, the
P&L calculation is wrong by a factor of 4 for all pre-split trades.

**Warning Signs:**
- Using `yf.download(..., auto_adjust=True)` (default) for some calculations and raw prices
  for others
- Strategy tested on stocks with known large splits shows anomalous performance exactly around
  split dates
- No documentation of which price series (adjusted/unadjusted) is used where
- Dividend income is neither excluded nor included consistently

**Prevention:**
- Establish a single convention and enforce it project-wide:
  - For signal generation: use adjusted close prices (captures economic reality)
  - For P&L calculation: use the same adjusted prices, and model position size in adjusted-price
    units consistently
- Document in DataHandler which columns are adjusted and which are raw.
- Add assertion in DataHandler: `assert 'adj_close' in df.columns or 'close' in df.columns`
  with explicit logging of which is used.
- For Forex: not applicable (no splits/dividends), but document this.
- Write a regression test using a stock with a known split date and verify the equity curve
  shows no discontinuity on the split date.

**Phase Mapping:** Phase 1 (DataHandler) — must be resolved before any stock strategy testing.

---

### 6. Ignoring Overnight Gaps (Gap Risk)

**Description:**
On daily and intraday timeframes, a stop-loss order that is set at price X does not guarantee
execution at price X. If the market opens the next day (or after a news event) with a gap
below the stop, the fill occurs at the gap price — which can be significantly worse. Backtests
that assume stop orders always fill at the stop price systematically underestimate losses.

For Forex on 1-minute data: a news event (Non-Farm Payroll, FOMC) can cause a 50-150 pip move
in a single second. The strategy's stop-loss at 20 pips may fill at 70 pips below entry. This
is called gap slippage and it is NOT the same as normal spread slippage.

**Warning Signs:**
- ExecutionHandler fills stop orders at exactly the stop price, always
- Maximum single-trade loss in the backtest exactly equals the theoretical stop-loss distance
- No differentiation between "stop hit within bar" and "gap through stop" in the execution model
- Strategy was tested on daily data but fill logic is "fill at stop price"

**Prevention:**
- Implement gap detection in ExecutionHandler: if a stop-loss at price P exists, and the next
  bar opens at Q where Q < P (for long position), fill at Q, not P.
- For daily bars: compare stop price to next day's open price. If next open gaps through stop,
  fill at open.
- For 1-minute bars: on bars immediately following major news events (identifiable by unusual
  volume or price range), apply additional gap slippage multiplier.
- Add a configurable `gap_fill_model`: `'exact'` (unrealistic), `'gap_at_open'` (realistic),
  `'worst_case'` (conservative).
- Write a test: place a stop-loss at 1.2000, next bar opens at 1.1950, assert fill price is
  `Decimal('1.1950')`, not `Decimal('1.2000')`.

**Phase Mapping:** Phase 2 (ExecutionHandler — stop order logic).

---

## Common Mistakes (Quality-Reducing)

These mistakes don't invalidate results entirely but reduce reliability and make the engine
harder to trust and maintain.

---

### 1. Metrics Computed on Equity Curve Instead of Trade Log

**Description:**
Computing Sharpe Ratio or Sortino Ratio from the equity curve's daily returns is not the same
as computing it from individual trade returns. Equity-curve-based metrics are sensitive to
the choice of return period (daily? hourly? per-bar?) and can be gamed by holding positions
across multiple bars. The correct base for metrics is the trade-level return series.

**Warning Signs:**
- `sharpe = equity_curve.pct_change().mean() / equity_curve.pct_change().std()`
- Sharpe calculation appears in `dashboard/callbacks.py` rather than `metrics.py`
- No `trade_log` object — only an equity timeseries is stored

**Prevention:**
- Maintain a `TradeLog` dataclass that records every FillEvent: entry price, exit price,
  entry time, exit time, P&L in Decimal, position size.
- Compute Sharpe, Sortino, Calmar from the trade P&L series: `[trade.pnl for trade in trade_log]`.
- The equity curve is derived from the trade log, not the primary data source.
- Annualization factor must match the data frequency:
  - Daily data: `sqrt(252)`
  - Hourly data: `sqrt(252 * 24)` (or `sqrt(252 * 6.5)` for stocks)
  - 1-minute: `sqrt(252 * 390)` for stocks

**Phase Mapping:** Phase 4 (Metrics module). Define the TradeLog structure before implementing
any KPI calculation.

---

### 2. Wrong Annualization Factor for Sharpe Ratio

**Description:**
The Sharpe Ratio is meaningless without the correct annualization factor. Using `sqrt(252)` for
a 1-minute Forex strategy (which should use `sqrt(252 * 1440)`) understates the annualized
Sharpe by a factor of 38. The result looks like 0.2 when it should be 7.6 — and vice versa.

**Warning Signs:**
- Same `sqrt(252)` factor used for all timeframes
- Sharpe Ratio changes significantly when you change the data frequency without changing strategy
- No documentation of which annualization factor is used where

**Prevention:**
- Define a `ANNUALIZATION_FACTORS` dict in `metrics.py`:
  ```python
  ANNUALIZATION_FACTORS = {
      '1min':  Decimal('252') * Decimal('1440'),  # Forex: 24h * 60min
      '5min':  Decimal('252') * Decimal('288'),
      '1h':    Decimal('252') * Decimal('24'),
      '4h':    Decimal('252') * Decimal('6'),
      'daily': Decimal('252'),
  }
  ```
- For stocks: adjust for market hours (1min stock = `252 * 390`).
- Pass the timeframe to every metrics calculation function explicitly.
- Unit test: verify the Sharpe calculation produces the expected value for a known return series.

**Phase Mapping:** Phase 4 (Metrics module).

---

### 3. Reusing DataHandler State Between Backtest Runs

**Description:**
When running parameter sweeps, a DataHandler or Portfolio instance that is not fully reset
between runs carries state (buffered bars, open positions, cash balance) from the previous run
into the next. This corrupts sweep results and makes them non-reproducible.

**Warning Signs:**
- Parameter sweep results depend on the order in which parameter combinations are evaluated
- Running the sweep twice produces different best-parameter results
- DataHandler has a `self.current_index` attribute that is not reset to 0 between runs
- Portfolio `self.cash` is not reset to initial capital between runs

**Prevention:**
- Each backtest run must instantiate fresh objects: `DataHandler()`, `Portfolio()`,
  `Strategy()`, `ExecutionHandler()` — never reuse across runs.
- Add a `reset()` method to each class as a backup, but prefer fresh instantiation.
- In the sweep runner: use a factory function `create_engine(params) -> Engine` that returns
  a fully fresh engine for each parameter combination.
- Test: run two sweeps with identical parameters in different orders, assert results are identical.

**Phase Mapping:** Phase 5 (Parameter Sweep runner design).

---

### 4. Not Testing Edge Cases in the Event Loop

**Description:**
The event loop must handle edge cases gracefully: no signal generated (empty queue step),
insufficient capital to fill an order, zero-volume bars, missing data gaps, simultaneous
signals in opposite directions. Without explicit tests for these cases, the engine will crash
or silently produce wrong results in production data.

**Warning Signs:**
- `test_causality.py` exists but no test for "what happens when no signal is generated"
- Portfolio does not check available cash before accepting an order
- No test for what happens when DataHandler encounters a gap of 5 missing bars

**Prevention:**
- Test: strategy generates no signal — assert event queue is empty after processing, no crash.
- Test: order size exceeds available capital — assert order is rejected, portfolio unchanged.
- Test: DataHandler receives a bar with volume = 0 — assert it is skipped or logged.
- Test: 5 consecutive missing bars — assert DataHandler handles the gap, indicators are not
  corrupted by the discontinuity.
- Test: simultaneous long and short signals — assert portfolio handles this deterministically.

**Phase Mapping:** Phase 2 (Engine Core) — write these tests alongside the event loop.

---

### 5. PnL Attribution Errors in Multi-Position Scenarios

**Description:**
When multiple positions are open simultaneously (or the strategy adds to an existing position),
calculating P&L per trade becomes ambiguous. Average entry price must be tracked correctly with
`Decimal` arithmetic to avoid incorrect per-trade attribution. FIFO vs. average-cost accounting
produces different realized P&L.

**Warning Signs:**
- Portfolio only tracks a single position per symbol
- Adding to a position recalculates average entry using float division
- Closing part of a position does not reduce the tracked quantity correctly
- Total P&L from trade log does not reconcile with final cash balance

**Prevention:**
- Define the accounting method before implementing Portfolio: FIFO is standard for stocks in
  the US; average cost is common for Forex.
- Track for each symbol: `quantity (Decimal)`, `average_entry_price (Decimal)`, `unrealized_pnl`.
- Unit test for average entry: buy 100 shares at $10.00, buy 100 more at $12.00, assert
  `average_entry_price == Decimal('11.00')`.
- Reconciliation test: run a full backtest, sum all trade P&L from the trade log, assert it
  equals `final_cash - initial_cash` (adjusted for any open positions at end).

**Phase Mapping:** Phase 2 (Portfolio — position tracking logic).

---

## Data-Specific Pitfalls

### Forex Data Issues

**1. Spread Not Included in OHLCV Data**

Free Forex data (yfinance Forex pairs, Alpha Vantage) provides midpoint OHLCV prices, not
actual bid/ask prices. In reality, every retail Forex trade crosses the spread. If you model
a 20-pip stop-loss strategy with a 1-pip spread and 0.3-pip slippage, the effective cost is
~6.5% of the stop-loss per trade — significant at scale.

- **Prevention:** Add a configurable spread parameter to ExecutionHandler. Default to realistic
  values: EUR/USD = 0.8 pips, GBP/USD = 1.2 pips, USD/JPY = 0.9 pips during liquid hours.
  Double these for off-hours.

**2. Pip Value Calculation Depends on Account Currency**

For a USD-denominated account trading EUR/USD: 1 standard lot = $10/pip. But for USD/JPY:
1 standard lot = ~$9.09/pip (depends on current exchange rate). Using a fixed pip value
produces incorrect position sizing and P&L for non-USD/USD pairs.

- **Prevention:** Calculate pip value dynamically: `pip_value = (pip_size * lot_size) / current_price`
  for pairs where USD is the base. For cross pairs (EUR/GBP), convert to USD using a reference
  rate. All calculations in `Decimal`.

**3. Missing Weekend and Holiday Data**

yfinance Forex data has no bars for Saturday-Sunday and occasionally has gaps for major holidays.
A strategy that expects continuous 1-minute data and encounters a 2-day gap will have corrupted
indicators (e.g., a 14-period RSI computed across a weekend gap is not equivalent to one computed
on continuous data).

- **Prevention:** DataHandler must detect gaps greater than `expected_bar_duration * 3` and
  either skip the gap or reset short-term indicators. Log all detected gaps. Never compute
  indicators that span detected gaps without explicit gap handling.

**4. Forex Data Quality in yfinance**

yfinance Forex data (`EURUSD=X`) has known quality issues: missing bars, duplicate timestamps,
and occasional price spikes. These "bad ticks" can trigger false signals (e.g., a spike to
1.5000 in EUR/USD triggers a breakout signal that never existed).

- **Prevention:** Implement a data validation step in DataHandler:
  - Flag bars where High/Low ratio > 1.02 (2% intrabar range) on 1-minute data as suspect
  - Detect and remove duplicate timestamps
  - Detect price spikes: if `|close - prev_close| / prev_close > 0.005` (0.5%) on 1-minute,
    log a warning
  - Use `df.drop_duplicates(subset='timestamp')` before yielding any bars

---

### Stock Data Issues

**1. Split and Dividend Adjustment Inconsistency (Already Covered Above)**

Reiterated here as a data-layer concern: always validate which price series yfinance returns
for each ticker by checking known split dates against the adjusted vs. raw close prices.

**2. Suspended and Delisted Tickers**

yfinance silently returns empty DataFrames or raises exceptions for delisted tickers. This
causes silent failures in multi-asset backtests: the strategy simply never trades that asset,
rather than flagging an error.

- **Prevention:** Add explicit error handling in DataHandler for each symbol load:
  if `df.empty` after fetching, raise a `DataError` with the ticker name and date range.
  Never silently skip a symbol.

**3. Intraday Data Limitations in yfinance**

yfinance limits free intraday data:
- 1-minute bars: maximum 7 calendar days of history
- 5-minute bars: maximum 60 days of history
- 1-hour bars: maximum 730 days of history

For 1-minute strategy backtesting, 7 days is insufficient for statistical significance.
Alpha Vantage free tier provides more history (up to 2 years for intraday) but has rate
limits (5 requests/minute on free tier, 25 requests/day on some endpoints).

- **Prevention:**
  - Document data availability limits in DataHandler docstring.
  - For 1-minute strategies: use the local CSV/Parquet storage layer as the primary source.
    Download and cache data once, reload from cache for all subsequent backtest runs.
  - Implement a caching layer in DataHandler that saves fetched data to `data/` directory
    as Parquet, with the symbol and date range in the filename.
  - For Alpha Vantage: implement exponential backoff and respect rate limits. Never hammer
    the API in a parameter sweep.

**4. Volume Data Unreliability for Forex via yfinance**

Forex volume from yfinance represents tick volume (number of price changes), not actual traded
volume. It is not directly comparable to stock market volume. Any volume-based strategy
(e.g., volume breakout) designed for stocks will behave unexpectedly if applied to Forex
volume data without this understanding.

- **Prevention:** Document this distinction. If a strategy uses volume, assert in the
  strategy's `__init__` which asset class it supports. Do not silently apply stock
  volume logic to Forex data.

---

### Free API Limitations

**1. Alpha Vantage Rate Limiting and Silent Failures**

Alpha Vantage free tier: 5 API calls/minute, 500 calls/day. If the engine exceeds this during
a parameter sweep (fetching fresh data for each parameter combination), the API returns an
error JSON instead of data. The `alpha_vantage` Python library does not always raise an
exception — it may return an empty or malformed DataFrame silently.

- **Prevention:**
  - Always check the returned DataFrame is non-empty and contains expected columns before use.
  - Implement `time.sleep(12)` between consecutive Alpha Vantage calls (5 calls/min = 12s gap).
  - Cache all downloaded data locally. The DataHandler should check the local cache first and
    only call the API if the cached data is older than a configurable staleness threshold
    (e.g., 24 hours for daily data).
  - Never call the API inside the parameter sweep inner loop. Fetch data once before the sweep.

**2. yfinance Data Source Instability**

yfinance is an unofficial scraper of Yahoo Finance data. It has broken multiple times due to
Yahoo Finance API changes and requires periodic updates. The library may return different
column names (e.g., `'Adj Close'` vs `'adj_close'`) depending on the version.

- **Prevention:**
  - Pin the yfinance version in `requirements.txt`.
  - After every yfinance download, normalize column names to lowercase with underscores
    in DataHandler: `df.columns = [c.lower().replace(' ', '_') for c in df.columns]`.
  - Add a DataHandler smoke test that fetches 5 days of AAPL data and asserts the expected
    columns exist and values are non-null.
  - Maintain a local data cache so that a yfinance outage does not break development.

---

## Testing Pitfalls

### 1. Testing the Vectorized Output Instead of the Event Sequence

**Description:**
Writing a test that checks `final_portfolio_value` without checking the sequence of events
that produced it. A look-ahead biased engine and a correct engine may produce the same final
portfolio value on some test data while having completely different internal event sequences.

**Prevention:**
- `test_causality.py` must assert the ORDER of events: for bar `t`, assert that no FillEvent
  with timestamp > `t` exists in the event log before bar `t+1` is processed.
- Record the complete event sequence for known test data and assert the sequence is identical
  on every run (determinism test).

---

### 2. Using Random Data in Tests Without a Fixed Seed

**Description:**
Generating random price series in tests without a fixed random seed. If `numpy.random` or
`random` is used to generate test data, each test run produces different data, making test
failures non-reproducible.

**Prevention:**
- Always set a fixed seed at the start of any test that uses random data:
  `numpy.random.seed(42)` or `random.seed(42)`.
- Prefer deterministic synthetic data over random data for unit tests: a hardcoded list of
  10 OHLCV bars is more reliable than a randomly generated series.
- Use `pytest` fixtures with `@pytest.fixture` to ensure deterministic test data is shared
  across test functions.

---

### 3. Mocking Out the Core Logic Instead of Testing It

**Description:**
Over-mocking in tests leads to test suites that pass 100% while the actual logic is never
exercised. Common mistake: mocking `decimal.Decimal` operations or the event queue in a
test for `portfolio.py`, which means the portfolio calculation is never actually tested.

**Prevention:**
- Only mock external dependencies (API calls, file I/O). Never mock `Decimal`, `deque`, or
  any internal engine class in tests for other engine classes.
- Use real `Decimal` values in all portfolio and execution tests.
- `test_pnl_accuracy.py` must use zero mocks for the calculation path — only mock the
  DataHandler's data source.

---

### 4. Not Testing the DataHandler's Causality Guarantee

**Description:**
The most critical test in the entire project — that the DataHandler never provides future data
to the strategy — is often the last to be written or skipped entirely. Without this test,
look-ahead bias can be introduced by any code change and go undetected.

**Prevention:**
- `test_causality.py` must be the FIRST test file written, before any strategy code.
- Test structure:
  ```python
  def test_no_future_data_access():
      handler = DataHandler(symbol='EURUSD', bars=synthetic_bars)
      seen_timestamps = []
      for bar in handler.stream_bars():
          seen_timestamps.append(bar.timestamp)
          # Strategy must NOT be able to access bars beyond current index
          assert handler.get_bar(bar.timestamp + timedelta(minutes=1)) is None
  ```
- This test must remain in the CI suite permanently and must be run on every commit.

---

### 5. Ignoring Transaction Costs in PnL Verification Tests

**Description:**
Writing `test_pnl_accuracy.py` with zero commissions and zero slippage to make the math
simple. This means the execution cost model is never tested, and bugs in commission or
slippage calculation go undetected until a real backtest is run.

**Prevention:**
- `test_pnl_accuracy.py` must include at least one test with non-zero commissions AND
  non-zero slippage.
- Example test: buy 1 lot EUR/USD at 1.10000, spread = 0.8 pip, slippage = 0.3 pip,
  close at 1.10050. Assert final P&L = `(50 - 8 - 3) * pip_value = 39 * pip_value`.
- All P&L assertions use exact `Decimal` equality, not `pytest.approx()`.

---

*Research compiled 2026-02-21 for apex-backtest greenfield project.*
*Sources: Academic literature on backtesting methodology, practitioner experience from*
*open-source backtrader/zipline/vectorbt communities, and analysis of common failure modes*
*in event-driven backtesting architectures.*
