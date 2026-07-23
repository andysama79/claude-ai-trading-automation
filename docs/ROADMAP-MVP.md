# Roadmap: MVP -> Backtest -> Real-World Trading

Companion to docs/PRD-MVP-backtest-and-live.md. Ordered task list, each item
sized to land as its own PR against the existing 121-test suite.

## Phase 0 — Unblock live safety (small, do first)
Status: DONE. Merged fix/stepped-tsl-zero-division into master (commit
61f4777) and completed 0.2–0.5 below. 131 tests passing. Fundamentals
persistence (0.6) is the one item still open.

- [x] 0.1 Fix SteppedTSL zero-division (commit 61f4777) — merged to master,
      verified via `python -m pytest`.
- [x] 0.2 Add factory-level regression test: build_tsl_strategy() with
      mode="stepped" -> call initial_stop() -> assert no exception, correct
      stop price. Added to tests/tsl/test_factory.py
      (TestFactorySteppedModeEndToEnd) — this test failed loudly against
      pre-merge master, confirming it actually catches the bug class.
- [x] 0.3 Implement trader/auth.py: interactive manual-mode session
      generator (login URL -> paste request_token -> exchange -> write
      .kite_session, mode 0600). KiteBroker._load_session() error messages
      updated to point at it.
- [x] 0.4 Startup guard: auth.mode == manual with missing OR empty
      .kite_session now raises with a clear message pointing at
      `python -m trader.auth` instead of an obscure downstream failure.
      Covered by tests/brokers/test_kite.py::TestLoadSession.
- [x] 0.5 Cache KiteBroker._get_instrument_token() (in-memory, 24h TTL,
      per-exchange) — needed before backtest hammers get_ohlc() in a loop.
      Covered by tests/brokers/test_kite.py::TestInstrumentTokenCache.
- [ ] 0.6 Wire fundamentals fetch result into TradeRecord.fundamentals
      instead of discarding it (data quality, unblocks fundamentals-aware
      strategy work later). Not started.

## Phase 1 — Backtest engine core
Add trader/backtest/ module. Target: one TSL config, one historical
symbol/date list in -> P&L report out, using real TSLStrategy classes.

- [ ] 1.1 trader/backtest/simulated_broker.py: SimulatedBroker(BrokerPlugin)
      — implements place_buy/place_sell/get_ltp/get_ohlc/get_open_positions
      against a pre-loaded price series, fills instantly, no network I/O.
- [ ] 1.2 trader/backtest/data.py: historical OHLC loader. Reuse
      KiteBroker.get_ohlc() for real data; support CSV fallback for offline
      dev/testing without hitting Kite.
- [ ] 1.3 trader/backtest/signals.py: synthetic signal generator — CSV of
      (symbol, exchange, buy_date, amount?, tsl_mode?) -> TradeSignal list.
- [ ] 1.4 trader/backtest/replay.py: time-compressed replay driver. Drives
      TSLMonitor's update loop across historical candles without real
      asyncio.sleep(poll_interval) waits — needs a pluggable "clock"/tick
      source instead of wall-clock sleep in TSLMonitor (small refactor:
      extract the sleep call so backtest can substitute an instant-tick
      driver).
- [ ] 1.5 trader/backtest/report.py: P&L aggregator — win rate, avg P&L %,
      max drawdown, best/worst trade, per-TSL-mode breakdown. CSV export.
- [ ] 1.6 CLI: python -m trader.backtest --config --signals --from --to.
      Writes logs/backtest_<ts>.jsonl (TradeRecord shape) + report CSV.
- [ ] 1.7 Unit tests for all of the above; python -m pytest stays green.
- [ ] 1.8 Manual spot-check: hand-verify one symbol/date's TSL math against
      the backtest's computed output.

Decision needed before 1.2: daily-only OHLC (fast) vs intraday granularity
(accurate) — see PRD section 4.3. Recommend shipping daily first.

## Phase 2 — Backtest usability + strategy comparison
- [ ] 2.1 Multi-strategy sweep: run the same signal set through all 5 TSL
      modes in one invocation, single comparison report.
- [ ] 2.2 Parameter sweep for one mode (e.g. fixed pct 3/5/8%, atr k
      1.5/2/3) — grid search, output ranked by a chosen metric (avg P&L,
      Sharpe-like ratio, max drawdown).
- [ ] 2.3 Intraday OHLC support (Option B from PRD 4.3) if Phase 1 daily
      results show the approximation is too coarse for real decisions.
- [ ] 2.4 Historical signal sourcing: if past Telegram messages are
      exportable, build a one-off importer to replace/augment the synthetic
      generator with real historical signal timing.

## Phase 3 — Real-world go-live readiness
- [ ] 3.1 Paper-trading mode: --dry-run / broker: paper config, routes
      through SimulatedBroker fed by *live* Kite LTP quotes (real market
      data, fake fills). Reuses Phase 1's SimulatedBroker.
- [ ] 3.2 Confirm/implement Telegram alerting on: order rejection, auth
      failure, TSL monitor halt after 3 failed LTP polls. Design spec
      requires this; verify it's actually implemented.
- [ ] 3.3 Capital guardrails: hard ceiling on trading.default_amount,
      optional check against available margin before placing a buy.
- [ ] 3.4 Run paper mode for >=1 week against the TSL config chosen from
      backtest results; compare directional consistency (see PRD success
      metrics).
- [ ] 3.5 Go-live checklist + rollback plan: who signs off, how to kill the
      process safely mid-position (existing startup recovery handles
      process restart, but need a documented "pull the plug" procedure for
      a bad TSL config caught in prod).

## Phase 4 — Post-MVP (not required to ship real trading, but planned)
- [ ] 4.1 CI: GitHub Actions running pytest on push (currently none).
- [ ] 4.2 Multi-broker BrokerPlugin (Upstox/Groww) — architecture supports
      it, no immediate need.
- [ ] 4.3 Portfolio-level capital allocation across concurrent positions
      (today: single dedup-by-symbol positions, no cross-position budget).
- [ ] 4.4 Web dashboard for trade log / backtest report visualization.

## Sequencing rationale
Phase 0 is mandatory and cheap — skipping it means backtesting a strategy
whose live implementation is currently guaranteed to crash on the default
config. Phase 1 is the actual "can we backtest" deliverable and is scoped
tightly to reuse existing plugin seams (per ARCHITECTURE.md's own analysis)
rather than a parallel simulation stack. Phase 2 is where the backtest
becomes useful for actually choosing a strategy instead of just proving the
pipeline works. Phase 3 is the only phase that touches real capital risk and
should not start until a Phase 1/2 backtest result exists to justify the TSL
config being deployed.
