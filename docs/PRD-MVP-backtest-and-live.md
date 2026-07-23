# PRD: MVP for Backtesting + Real-World Trading Readiness

Status: Draft
Date: 2026-07-23
Owner: TBD
Source of truth for current architecture: docs/ARCHITECTURE.md

## 1. Problem statement

The system (Telegram signal -> Kite market buy -> pluggable TSL exit) is fully
implemented and unit-tested (121 tests) as a live-trading pipeline, but has
two blockers before it can be trusted with real money:

1. No way to validate a TSL strategy against history before risking capital.
   Zero backtest code exists today (confirmed: no "backtest" hits anywhere in
   repo, no pandas/numpy in requirements.txt).
2. A live-path correctness bug and an auth gap that make the default config
   unsafe to run unattended right now (see Section 3).

MVP goal: close both gaps with the smallest amount of new code, reusing the
existing plugin boundaries (`BrokerPlugin`, `TSLStrategy`) rather than
building a parallel system.

## 2. Goals / non-goals

Goals:
- Backtest any TSL strategy against historical price data with a P&L report,
  using the exact same `TSLStrategy` and `TSLMonitor` code that runs live.
- Fix the correctness/auth issues that block safe live operation.
- Reach a state where a human can: pick a TSL config, backtest it over N
  months, decide it's good, then flip a switch to run it live with the same
  config file and be confident the code path is identical.

Non-goals (post-MVP):
- Multi-broker support (Upstox/Groww) — architecture allows it, not required now.
- Intraday tick-level backtest fidelity — MVP uses daily/OHLC granularity.
- Portfolio-level risk management (position sizing across concurrent trades,
  capital allocation) — MVP is single-position-at-a-time like today's engine.
- Web dashboard / UI — CLI + JSONL/CSV output is sufficient for MVP.
- Live paper-trading mode against Kite's sandbox — nice-to-have, see roadmap.

## 3. Must-fix blockers (do first, before backtest work)

These block "real-world trading" regardless of backtesting and should land
first since they're small and de-risk everything downstream.

### 3.1 SteppedTSL zero-division (P0, live-breaking)
`trader/tsl/factory.py` constructs `SteppedTSL(fill_price=0.0, tiers=tiers)`.
`SteppedTSL._active_pct()` divides by the constructor's `self.fill_price`
(permanently 0.0) instead of the real fill price passed to `initial_stop()`.
`stepped` is the default `tsl.default_mode`, so an unmodified config crashes
the TSL monitor on the first tick after every buy — leaving a live,
unmonitored position with real money in it and no stop loss attached.
Fix: store `self.fill_price = fill_price` inside `initial_stop()`, drop the
constructor placeholder. Add a factory-level regression test that goes
through `build_tsl_strategy()` + `initial_stop()` end-to-end (unit tests
today only construct `SteppedTSL` directly, which is why this shipped).

Note: branch `fix/stepped-tsl-zero-division` (commit 61f4777) already
addresses this per the current session's git log — verify it's merged to
master before anything else in this PRD proceeds.

### 3.2 Missing trader/auth.py (P0, blocks manual-mode startup)
`KiteBroker._load_session()` tells the user to "run auth.py first" but the
file doesn't exist. `auth.mode: manual` (the config default) has no way to
produce `.kite_session`. Only `auth.mode: totp` works out of the box today.
Fix: implement `trader/auth.py` — interactive CLI: login URL -> user pastes
request_token -> exchange for access_token -> write `.kite_session`. This is
also the auth path a backtester's "dry run against real quotes" mode would need.

### 3.3 Instrument token lookup unbounded/uncached (P1, correctness-adjacent)
`KiteBroker._get_instrument_token()` fetches the entire exchange instrument
dump and linearly scans it on every `get_ohlc()` call. Fine for one signal at
a time live; will be a real bottleneck once a backtest calls `get_ohlc()"`
in a loop over many symbols/dates. Fix: cache the instrument list (in-memory,
TTL'd, e.g. refresh once per day) before backtest work starts, since the
backtest data pipeline will hammer this path.

### 3.4 Fundamentals not persisted onto TradeRecord (P2, data quality)
`Engine._on_position_exit()` writes `fundamentals={}` unconditionally; the
async fetch result is logged but never joined back. Not a blocker for
backtesting or live safety, but fix before using trade log data for any
fundamentals-conditioned strategy work.

## 4. MVP feature: Backtesting engine

### 4.1 Design principle
Reuse `TSLStrategy` and as much of `TSLMonitor`'s stop-advance/exit logic as
possible unmodified. The only new components are a historical data source, a
simulated broker, a time-compressed replay driver, and a P&L aggregator. This
mirrors ARCHITECTURE.md Section 6's existing gap analysis — this PRD adopts
its conclusions as the plan.

### 4.2 New module: `trader/backtest/`
```
trader/backtest/
├── __init__.py
├── data.py          # historical OHLC loader (Kite historical API wrapper +
│                     #   optional CSV/parquet loader for offline runs)
├── simulated_broker.py   # SimulatedBroker(BrokerPlugin): fills instantly at
│                     #   a given historical price, no network calls
├── replay.py         # replay driver: iterate candles in time order, drive
│                     #   TSLMonitor's tick loop without asyncio.sleep waits
├── signals.py         # synthetic signal generator: "buy SYMBOL on DATE at
│                     #   OPEN/CLOSE price" — lets you test TSL strategies in
│                     #   isolation without needing real historical Telegram
│                     #   messages
└── report.py          # P&L aggregator: win rate, avg P&L, max drawdown,
                        #   per-TSL-mode / per-symbol breakdown, CSV export
```

### 4.3 Data granularity decision (must decide before building)
Kite's historical API is daily-only through the existing `get_ohlc()`
interface. Daily bars cannot resolve *intraday* TSL triggers realistically —
a strategy might "exit" mid-day in reality but daily bars only tell you
open/high/low/close. Two options:
- Option A (MVP-fast): backtest at daily granularity, accept that intraday
  stop-outs are approximated by day's low. Good enough to compare TSL modes
  relatively, not good enough for precise P&L.
- Option B (MVP-accurate): pull intraday OHLC (Kite supports minute-level
  historical candles via a different API param) for the subset of symbols
  under test. More realistic, more data/rate-limit cost.
Recommendation: ship Option A first (unblocks relative strategy comparison
fast), add Option B as a fast-follow once the pipeline exists — same
`get_ohlc()` interface, just finer granularity, no architecture change needed.

### 4.4 CLI entrypoint
`python -m trader.backtest --config config.yaml --signals signals.csv --from 2025-01-01 --to 2026-01-01`
Output: `logs/backtest_<timestamp>.jsonl` (same `TradeRecord` shape as live)
plus a summary report (stdout + `logs/backtest_<timestamp>_report.csv`).

### 4.5 Acceptance criteria
- Given a CSV of historical (symbol, buy_date) pairs and a TSL config, the
  backtest produces one TradeRecord per signal with realistic buy/sell prices
  and P&L, using the same `TSLStrategy` classes as production.
- Running the same TSL config through backtest and through a manually-scripted
  "replay via SimulatedBroker" for one hand-checked symbol/date produces
  matching numbers (manual spot-check, not automated, for MVP).
- Report shows: total trades, win rate, avg P&L %, max drawdown, best/worst
  trade, breakdown by TSL mode if multiple modes tested in one run.
- All new code has unit tests; `python -m pytest` still passes (currently 121).

## 5. MVP feature: Real-world trading readiness

Everything in Section 3 must be done. In addition:

- 5.1 Config safety net: reject startup if `auth.mode: manual` and
  `.kite_session` missing / expired, with a clear error pointing at
  `python -m trader.auth`, instead of failing deep inside the first buy.
- 5.2 Alerting: ARCHITECTURE.md/design spec both call for a Telegram alert on
  order rejection / auth failure / TSL monitor halt. Confirm this exists
  (grep shows design intent but verify implementation) — if missing, this is
  the difference between "found out at end of day from the trade log" and
  "found out in real time that a position has no stop loss."
- 5.3 Dry-run / paper mode: add a `--dry-run` flag or `broker: paper` config
  option that routes through `SimulatedBroker` fed by *live* LTP quotes
  (real Kite quotes, no real orders) instead of a real `KiteBroker`. This
  reuses backtest's `SimulatedBroker` and de-risks the go-live cutover — same
  code path, fake fills, real market data, for a few days before real capital.
- 5.4 Position size / capital guardrails: `trading.default_amount` today has
  no upper bound check and no check against available margin. Add a sanity
  cap (config value + hard-coded ceiling) before this touches real money.

## 6. Success metrics for MVP

- `python -m trader.backtest` runs end-to-end on at least 20 historical
  symbol/date pairs across 2 different TSL modes without crashing.
- Backtest report and a live 1-week paper-mode run against the same TSL
  config produce directionally consistent results (not identical — paper
  mode sees real intraday moves backtest can't at daily granularity).
- Zero occurrences of the SteppedTSL crash in either mode.
- `auth.mode: manual` works fully unattended after running `auth.py` once
  each morning (per existing design spec).

## 7. Open questions (need a decision before Section 4 starts)

1. Where do historical signals for backtesting come from — recorded past
   Telegram messages (if any exist / can be exported), or purely the
   synthetic "buy X on date Y" generator? Affects how "realistic" MVP
   backtest results are.
2. Daily vs intraday OHLC (Section 4.3) — confirm Option A is acceptable for
   MVP or if intraday is a hard requirement given the trading style (earnings
   momentum trades likely move fast intraday, so this matters more than for
   swing trades).
3. Who owns real-money risk sign-off before flipping from paper mode to live
   after backtest MVP ships?
