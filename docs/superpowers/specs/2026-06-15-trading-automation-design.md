# Trading Automation Adapter — Design Spec

**Date:** 2026-06-15  
**Status:** Approved

---

## Goal

Listen for earnings-call signals from Telegram, place an automated market buy via Zerodha Kite, and manage the position with a pluggable trailing stop loss (TSL) strategy to capture maximum momentum. Fundamentals are fetched post-buy for logging only — never block order execution.

---

## Architecture

**Approach:** Plugin-based async service with internal `asyncio.Queue` event bus. Single process, no external queue infrastructure. Components communicate through typed events. Process supervisor (systemd/supervisor) handles crash recovery.

```
[3rd-party Telegram Bot]
        ↓
[Relay Bot — SourcePlugin]     ← normalises to TradeSignal
        ↓
[asyncio.Queue — Event Bus]    ← dispatcher routes to broker
        ↓
[Kite Adapter — BrokerPlugin]  ← auth + market buy
        ↓ (on fill)
[TSL Monitor] ──────────────── polls LTP, fires sell on trigger
[Fundamentals Fetcher] ──────── async, post-buy, never blocks
[Trade Log] ─────────────────── JSONL, records full trade lifecycle
```

Extensibility points: new `SourcePlugin` implementations (Discord, WhatsApp) slot in without touching core. New `BrokerPlugin` implementations (Upstox, Groww) same. New `TSLStrategy` implementations register via factory.

---

## Data Flow

1. **Signal received** — relay bot receives message from 3rd-party Telegram channel/group via `python-telegram-bot`. Parses raw text into typed `TradeSignal`.

2. **TradeSignal emitted**
   ```python
   @dataclass
   class TradeSignal:
       symbol: str
       exchange: str                # NSE | BSE
       amount: float | None = None  # ₹ amount; None → use config default
       tsl_mode: str | None = None  # None → use config default
       tsl_pct: float | None = None # fixed mode
       tsl_tiers: list | None = None# stepped mode
       tsl_k: float | None = None   # atr / chandelier
   ```
   Deduplication: signal dropped if open position already exists for symbol.

3. **Event bus dispatch** — `TradeSignal` pushed to `asyncio.Queue`. Dispatcher pulls and routes to registered broker plugin.

4. **Market buy** — broker plugin calculates `qty = floor(amount / LTP)`, places `ORDER_TYPE_MARKET`. Awaits fill confirmation. Stores `Position(symbol, qty, fill_price, order_id)`.

5. **Post-fill fork** — two independent async tasks spawn:
   - **TSL Monitor**: polls LTP every N seconds, updates stop, fires sell when `ltp <= stop`
   - **Fundamentals Fetcher**: hits external provider (screener.in / NSE), appends to trade log

6. **TSL exit** — market sell placed. `TradeRecord` written to log (symbol, buy/sell price, qty, P&L, TSL mode, fundamentals snapshot, timestamps). Monitor task exits. Position removed from active store.

---

## TSL Strategy Abstraction

All TSL strategies implement a single interface:

```python
class TSLStrategy(ABC):

    @abstractmethod
    def initial_stop(self, fill_price: float) -> float:
        """Stop price at entry."""
        ...

    @abstractmethod
    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        """Called each poll tick. Monotonically increasing — never returns lower than current_stop."""
        ...

    def should_exit(self, ltp: float, stop: float) -> bool:
        return ltp <= stop
```

### Strategies

| Mode | Description | Key params |
|------|-------------|------------|
| `fixed` | Stop = peak × (1 − pct/100) | `tsl_pct` |
| `stepped` | TSL % tightens as unrealised gain grows | `tsl_tiers: [(gain_threshold, tsl_pct), ...]` |
| `atr` | Stop = peak − (k × ATR14) | `k` (default 2.0) |
| `chandelier` | Stop = highest_high(N) − (k × ATR14) | `k` (default 3.0), `period` |
| `psar` | Parabolic SAR with accelerating factor | `af_start=0.02`, `af_step=0.02`, `af_max=0.20` |

**Stepped tiers example:**
```
gain < 10%  → 8.0% TSL
gain < 30%  → 5.0% TSL
gain < 60%  → 3.0% TSL
gain ≥ 60%  → 2.0% TSL
```

**Factory resolves config or per-signal override → strategy instance:**
```python
def build_tsl_strategy(config: dict) -> TSLStrategy:
    match config["tsl_mode"]:
        case "fixed":      return FixedPctTSL(config["tsl_pct"])
        case "stepped":    return SteppedTSL(config["tsl_tiers"])
        case "atr":        return ATRTSLStrategy(config.get("k", 2.0))
        case "chandelier": return ChandelierTSL(config.get("k", 3.0))
        case "psar":       return ParabolicSARTSL()
```

Per-signal `tsl_mode` always overrides config default.

---

## Plugin Interfaces

```python
class SourcePlugin(ABC):
    @abstractmethod
    async def start(self, queue: asyncio.Queue) -> None:
        """Push TradeSignal onto queue indefinitely."""
        ...

class BrokerPlugin(ABC):
    @abstractmethod
    async def place_buy(self, signal: TradeSignal) -> Position: ...

    @abstractmethod
    async def place_sell(self, position: Position) -> None: ...

    @abstractmethod
    async def get_ltp(self, symbol: str, exchange: str) -> float: ...
```

---

## Authentication (Kite)

Kite Connect requires daily session token. Two modes, switched via config:

| Mode | Behaviour |
|------|-----------|
| `manual` | Run `auth.py` each morning. Prompts for TOTP, exchanges for session token, caches to `.kite_session`. |
| `totp` | `pyotp` generates TOTP from secret in env var `KITE_TOTP_SECRET`. Fully automated. |

On `TokenException` during trading: re-auth if `totp` mode, else pause trading and send alert via Telegram.

---

## Config Schema (`config.yaml`)

```yaml
trading:
  default_amount: 10000          # ₹ per trade, overridable per signal
  exchange: NSE
  product: CNC                   # CNC (delivery) or MIS (intraday)
  dedup_open_positions: true

tsl:
  default_mode: stepped
  default_pct: 5.0               # fixed mode only
  k: 3.0                         # atr / chandelier
  tiers:                         # stepped mode
    - [10, 8.0]
    - [30, 5.0]
    - [60, 3.0]
    - [.inf, 2.0]
  poll_interval_sec: 10

auth:
  mode: manual                   # manual | totp
  totp_secret_env: KITE_TOTP_SECRET

sources:
  telegram:
    api_id_env: TG_API_ID
    api_hash_env: TG_API_HASH
    relay_bot_token_env: TG_BOT_TOKEN
    watch_chats: []              # list of chat IDs to monitor

fundamentals:
  enabled: true
  provider: screener             # screener | nse | none

log:
  trade_log: logs/trades.jsonl
  level: INFO
```

Secrets always via env vars. `.env` for local dev, system env for VPS.

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| Signal parse failure | Log + skip, never crash |
| Kite order rejected | Log error + full order params, alert via Telegram |
| TSL LTP poll failure | Retry 3× with exponential backoff; halt monitor + alert if all fail |
| Auth token expired | Re-auth if `totp` mode; else alert + pause trading |
| Fundamentals fetch fails | Log warning, continue — non-blocking by design |
| Process crash | systemd/supervisor auto-restarts; startup recovery re-attaches TSL monitors |

**Startup recovery:** on boot, fetch open positions from Kite positions API, reconstruct `Position` objects, re-attach TSL monitors with last known peak price from trade log. No orphaned positions.

---

## Deployment

| Environment | Method |
|-------------|--------|
| Local dev | `python -m trader` + `.env` file |
| VPS | systemd service, env vars in `/etc/environment` or service unit |

`.env` is gitignored. Secrets never committed.

---

## Project Layout

```
claude-ai-trading-automation/
├── trader/
│   ├── __main__.py          # entrypoint, wires plugins + starts event loop
│   ├── core/
│   │   ├── events.py        # TradeSignal, Position, TradeRecord dataclasses
│   │   ├── dispatcher.py    # asyncio.Queue event bus
│   │   └── engine.py        # main orchestrator
│   ├── sources/
│   │   ├── base.py          # SourcePlugin ABC
│   │   └── telegram.py      # TelegramRelaySource
│   ├── brokers/
│   │   ├── base.py          # BrokerPlugin ABC
│   │   └── kite.py          # KiteBroker + auth (manual/totp)
│   ├── tsl/
│   │   ├── base.py          # TSLStrategy ABC
│   │   ├── fixed.py
│   │   ├── stepped.py
│   │   ├── atr.py
│   │   ├── chandelier.py
│   │   ├── psar.py
│   │   ├── factory.py       # build_tsl_strategy()
│   │   └── monitor.py       # TSLMonitor async task
│   ├── fundamentals/
│   │   └── screener.py      # async fundamentals fetcher
│   └── config.py            # loads config.yaml + env vars
├── config.yaml
├── config.example.yaml
├── .env.example
├── logs/
├── requirements.txt
└── systemd/
    └── trader.service
```
