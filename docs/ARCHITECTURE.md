# Architecture & Status

Snapshot of the trading automation system as of 2026-07-23.
Covers component wiring, data flow, what is built, what is missing, and the backtesting question.

## 1. System overview

The service is a single async process (`python -m trader`).
Three plugin families connect through one in-process event bus.

```text
                                  ┌─────────────────────────┐
                                  │   Telegram channel(s)    │
                                  └────────────┬─────────────┘
                                               │ raw text messages
                                               ▼
                              ┌────────────────────────────────┐
                              │ TelegramRelaySource             │
                              │ trader/sources/telegram.py      │
                              │ - polls Telegram Bot API        │
                              │ - parse_signal() regex extract  │
                              │ - filters by watch_chats        │
                              └────────────────┬─────────────────┘
                                               │ TradeSignal
                                               ▼
                              ┌────────────────────────────────┐
                              │ asyncio.Queue (in __main__.py)  │
                              └────────────────┬─────────────────┘
                                               │ forward_to_engine()
                                               ▼
                              ┌────────────────────────────────┐
                              │ Engine.emit()                   │
                              │ trader/core/engine.py           │
                              └────────────────┬─────────────────┘
                                               │
                                               ▼
                              ┌────────────────────────────────┐
                              │ Dispatcher (asyncio.Queue bus)  │
                              │ trader/core/dispatcher.py       │
                              │ - single queue, N handlers      │
                              └────────────────┬─────────────────┘
                                               │ Engine._handle_signal()
                    ┌──────────────────────────┼──────────────────────────┐
                    ▼                          ▼                          ▼
        ┌───────────────────┐    ┌──────────────────────┐    ┌────────────────────────┐
        │ KiteBroker         │    │ build_tsl_strategy()  │    │ fetch_fundamentals()    │
        │ trader/brokers/    │    │ trader/tsl/factory.py │    │ trader/fundamentals/    │
        │ kite.py             │    │ picks fixed/stepped/  │    │ fetcher.py               │
        │ - place_buy()       │    │ atr/chandelier/psar   │    │ - yfinance, fire-and-    │
        │ - fills Position     │    │                        │    │   forget, logging only  │
        └─────────┬───────────┘    └───────────┬────────────┘    └─────────────────────────┘
                  │ Position                    │ TSLStrategy
                  └──────────────┬──────────────┘
                                 ▼
                      ┌────────────────────────┐
                      │ TSLMonitor (per position)│
                      │ trader/tsl/monitor.py    │
                      │ - polls broker.get_ltp() │
                      │ - strategy.update_stop() │
                      │ - strategy.should_exit() │
                      │ - broker.place_sell()    │
                      └────────────┬──────────────┘
                                   │ on_exit callback
                                   ▼
                      ┌────────────────────────┐
                      │ Engine._on_position_exit│
                      │ - appends TradeRecord   │
                      │   to logs/trades.jsonl  │
                      └────────────────────────┘
```

Startup also runs `Engine.recover_open_positions()`, which pulls open positions from
the broker and re-attaches a `TSLMonitor` to each one, so a process restart does not
orphan a live position.

## 2. Component reference

| Component | File | Responsibility | Talks to |
|---|---|---|---|
| `TelegramRelaySource` | `trader/sources/telegram.py` | Polls Telegram, regex-parses symbol + inline overrides (`AMOUNT:`, `TSL:`, `TSL_PCT:`, `TSL_K:`) into a `TradeSignal` | Pushes onto `asyncio.Queue`, implements `SourcePlugin` ABC |
| `SourcePlugin` (ABC) | `trader/sources/base.py` | One method: `start(queue)`. Any new signal source (RSS, webhook, manual CLI) implements this | Nothing else implements it yet |
| `Engine` | `trader/core/engine.py` | Orchestrator: dedup by symbol, calls broker to buy, builds TSL strategy, spawns monitor task, fires fundamentals fetch, writes trade log, does startup recovery | `BrokerPlugin`, `Dispatcher`, `build_tsl_strategy`, `TSLMonitor`, `fetch_fundamentals` |
| `Dispatcher` | `trader/core/dispatcher.py` | Minimal pub/sub: one `asyncio.Queue`, list of async handlers, catches handler exceptions so the loop never dies | Used only by `Engine` (single handler registered: `_handle_signal`) |
| `BrokerPlugin` (ABC) | `trader/brokers/base.py` | Contract: `place_buy`, `place_sell`, `get_ltp`, `get_ohlc`, `get_open_positions` | `KiteBroker` is the only implementation |
| `KiteBroker` | `trader/brokers/kite.py` | Wraps `kiteconnect.KiteConnect`. Market orders, LTP quotes, daily OHLC via Kite's historical data API, position recovery. Two auth modes: `manual` (reads `.kite_session`) and `totp` (pyotp-driven login) | Zerodha Kite Connect REST API |
| `TSLStrategy` (ABC) | `trader/tsl/base.py` | Contract: `initial_stop`, `update_stop`, `should_exit` (default `ltp <= stop`), optional async `on_position_opened` for strategies that need historical data | Five concrete strategies below |
| `FixedPctTSL` | `trader/tsl/fixed.py` | Flat trailing % from peak | — |
| `SteppedTSL` | `trader/tsl/stepped.py` | Trailing % tightens as unrealised gain crosses configured tiers | — |
| `ATRTSLStrategy` | `trader/tsl/atr.py` | Stop = peak − k×ATR(14). Fetches 20 days OHLC via `broker.get_ohlc()` on open | `BrokerPlugin.get_ohlc` |
| `ChandelierTSL` | `trader/tsl/chandelier.py` | Chandelier exit variant of the ATR idea | `BrokerPlugin.get_ohlc` |
| `ParabolicSARTSL` | `trader/tsl/psar.py` | Classic PSAR acceleration-factor trail | — |
| `build_tsl_strategy` | `trader/tsl/factory.py` | Resolves config defaults + per-signal inline overrides into a strategy instance | `Config.tsl`, `TradeSignal` |
| `TSLMonitor` | `trader/tsl/monitor.py` | One instance per open position. Polls LTP every `poll_interval_sec`, advances the stop, sells and reports back on trigger. LTP poll has 3-retry exponential backoff before giving up | `BrokerPlugin`, one `TSLStrategy`, `Engine._on_position_exit` |
| `fetch_fundamentals` | `trader/fundamentals/fetcher.py` | Fire-and-forget post-buy lookup (`yfinance` or `none` provider). Logged, not persisted onto the trade record today | External Yahoo Finance via `yfinance` |
| `Config` / `load_config` | `trader/config.py` | Typed dataclass tree loaded from `config.yaml`, with defaults matching `config.example.yaml` | Read once at startup in `__main__.py` |
| `__main__.py` | `trader/__main__.py` | Wires `KiteBroker` + `Engine` + `TelegramRelaySource`, runs all three concurrently via `asyncio.gather` | Everything above |

Events (`TradeSignal`, `Position`, `TradeRecord`) live in `trader/core/events.py` as plain
dataclasses shared by every layer, no serialization boundary between them in-process.

## 3. Data flow, one trade end to end

1. Telegram message arrives → `parse_signal()` extracts symbol + optional inline TSL override.
2. `TelegramRelaySource` puts a `TradeSignal` on the local queue.
3. `__main__.forward_to_engine` drains that queue and calls `Engine.emit()`.
4. `Engine.emit()` pushes onto the `Dispatcher` queue.
5. `Dispatcher.run()` calls `Engine._handle_signal()`.
6. Dedup check against `_open_positions` (in-memory dict, symbol keyed).
7. `broker.place_buy()` sizes qty from `amount / ltp`, places a market order, polls order status up to 30s for fill.
8. `build_tsl_strategy()` picks the strategy from signal overrides or config defaults.
9. Fundamentals fetch is spawned as a detached task, does not block the trade path.
10. `TSLMonitor` is spawned as a detached task and takes over: poll LTP, tighten stop, sell on trigger.
11. On exit, `Engine._on_position_exit()` computes P&L and appends one JSON line to `logs/trades.jsonl`.

Nothing here is durable except that one log file: `_open_positions` is in-memory, rebuilt only from the broker's live position list at startup.

## 4. What is built (status: done)

All 19 tasks from `docs/superpowers/plans/2026-06-15-trading-automation.md` are implemented and committed. 121 tests pass (`python -m pytest`).

- Event dataclasses, typed config loader with YAML round-trip.
- Plugin ABCs for sources, brokers, TSL strategies.
- Telegram signal source with inline-override parsing.
- Kite broker: buy, sell, LTP, OHLC, open-position recovery, manual + TOTP auth paths.
- Five TSL strategies plus a factory that resolves per-signal overrides.
- Async TSL monitor with retry/backoff on LTP polling.
- Fundamentals fetcher (yfinance), non-blocking.
- Event bus dispatcher with exception isolation.
- Engine: dedup, trade logging, startup recovery.
- Entrypoint, systemd unit, Dockerfile, docker-compose, fly.toml, deploy docs.

## 5. Gaps and open issues

### Critical bug: default TSL mode crashes on first tick

`trader/tsl/factory.py` builds `SteppedTSL` as `SteppedTSL(fill_price=0.0, tiers=tiers)`,
with a comment claiming the real fill price is supplied later.
It is not.
`SteppedTSL._active_pct()` divides by `self.fill_price` (the constructor value, permanently 0.0), not by the `fill_price` argument passed into `initial_stop()`.
The very first call to `initial_stop()` raises `ZeroDivisionError`.

`stepped` is the default `tsl.default_mode` in both `trader/config.py` and `config.example.yaml`, so an unmodified config crashes the TSL monitor on every position, immediately after the buy fills.
The buy itself still executes, so this leaves a live, unmonitored position with no trailing stop attached.
Unit tests do not catch it because every `test_stepped.py` case constructs `SteppedTSL` directly with a real fill price, never through the factory.

Fix is a one-line change: store the real fill price on the strategy at `initial_stop()` time, or drop the constructor `fill_price` and always compute gain from `self.fill_price = fill_price` set inside `initial_stop`. Say the word and it's a two-minute patch.

### Missing: `trader/auth.py`

`KiteBroker._load_session()` reads `.kite_session` and tells the user to "run auth.py first" if it is missing.
That file does not exist.
`CLAUDE.md` already flags this as a TODO.
Without it, `auth.mode: manual` (the default) has no way to produce the session file, so the service cannot authenticate at all out of the box. `auth.mode: totp` works today since `_auth_totp()` is fully implemented.

### Minor: instrument token lookup is unbounded and uncached

`KiteBroker._get_instrument_token()` fetches the entire exchange instrument list on every `get_ohlc()` call and linearly scans it.
Works, but is one HTTP round-trip plus O(n) scan per OHLC fetch, which happens on every ATR/Chandelier position open.
Not a correctness gap, only a latency/rate-limit one.

### Not persisted: fundamentals on the trade record

`Engine._on_position_exit()` writes `fundamentals={}` unconditionally into the trade log.
The async `fetch_fundamentals()` task result is never joined back into the `TradeRecord`, it is only logged.
CLAUDE.md's own trade log description ("fundamentals snapshot") is currently not true of the data on disk.

### No CI

No `.github/workflows`. Tests exist and pass locally; nothing runs them on push. Not part of the original 19-task plan.

## 6. Backtesting: current state and path to it

**Short answer: not today. There is no backtest code, no historical replay loop, and no P&L simulator anywhere in the repo.** Confirmed by a full-repo search for "backtest" (zero hits in code, docs, or the plan spec) and by `requirements.txt`, which has no `pandas`, `numpy`, or backtesting library.

What already exists that a backtester would reuse:

- `BrokerPlugin.get_ohlc()` is already a broker-agnostic interface, and `KiteBroker` implements it against Kite's historical data API (daily candles). That is a real historical data source, live today.
- Every `TSLStrategy` is decoupled from the live broker for its core logic: `initial_stop`, `update_stop`, `should_exit` are pure functions of price data, no I/O. Only `ATRTSLStrategy` and `ChandelierTSL` need `on_position_opened(position, broker)` to pull 20 days of OHLC, and that already goes through the same `BrokerPlugin.get_ohlc()` interface, so a fake/offline broker satisfies it for free.
- `TradeRecord` and the JSONL trade log already give you a real-trading P&L format to compare a backtest against.

What is missing to actually run one:

1. A historical price feed for replay, either Kite's `get_ohlc` at finer granularity (it is daily-only right now, no intraday) or a separate data source, since daily bars alone will not resolve intraday TSL triggers realistically.
2. A `BrokerPlugin` implementation that fills instantly at a given historical price instead of hitting Zerodha, so the exact same `Engine` / `TSLMonitor` / `TSLStrategy` code path runs unmodified. This is the natural seam, the plugin architecture was built for exactly this kind of swap.
3. A replay driver: iterate historical candles/ticks in time order, feed them to the fake broker's `get_ltp`, drive `TSLMonitor`'s loop without the real `asyncio.sleep(poll_interval)` wait (needs a time-compression hook or a rewritten poll loop for backtest mode).
4. Historical signals to replay, either recorded past Telegram messages, or (more realistically for evaluating TSL strategies in isolation) a synthetic signal generator that just says "bought symbol X on date Y" and lets you test TSL strategy performance against real historical price action.
5. A P&L aggregator across many simulated trades: win rate, average P&L, max drawdown, per-TSL-mode comparison. None of this exists; the current trade log is built for one-trade-at-a-time live logging, not batch analysis.

None of this is large. The plugin boundaries (`BrokerPlugin`, `TSLStrategy`) were already built cleanly enough that a backtest is mostly "write a `SimulatedBroker` and a replay loop," not a rewrite. Realistic estimate is a small, self-contained module (`trader/backtest/`) reusing the existing `TSLStrategy` and `TSLMonitor` logic. Worth scoping as its own task list once the `SteppedTSL` bug and `auth.py` gap above are closed, since those block real trading regardless of backtesting.

## 7. Suggested order of work

1. Fix `SteppedTSL` zero-division bug (default mode, currently broken).
2. Add `trader/auth.py` for manual-mode session generation.
3. Wire fundamentals result into `TradeRecord` instead of discarding it.
4. Decide if intraday OHLC is needed before backtesting TSL strategies meaningfully.
5. Build `SimulatedBroker` + replay driver + P&L aggregator for backtesting.
