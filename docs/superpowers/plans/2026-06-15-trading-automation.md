# Trading Automation Adapter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a plugin-based async service that listens for earnings signals on Telegram, places automated market buys via Zerodha Kite, and manages positions with a pluggable trailing stop-loss strategy.

**Architecture:** Single Python async process with an `asyncio.Queue` event bus. Source plugins push typed `TradeSignal` events; the dispatcher routes them to a broker plugin that places orders; a TSL monitor async task manages each open position; fundamentals are fetched post-buy and logged only.

**Tech Stack:** Python 3.12+, `python-telegram-bot>=21`, `kiteconnect>=4.1`, `pyotp`, `aiohttp`, `yfinance`, `pyyaml`, `python-dotenv`, `pytest`, `pytest-asyncio`

---

## File Map

```
trader/
├── __main__.py                  # entrypoint: wire plugins, start event loop
├── config.py                    # load config.yaml + env vars → Config dataclass
├── core/
│   ├── __init__.py
│   ├── events.py                # TradeSignal, Position, TradeRecord dataclasses
│   ├── dispatcher.py            # asyncio.Queue event bus
│   └── engine.py                # orchestrator: startup recovery + main loop
├── sources/
│   ├── __init__.py
│   ├── base.py                  # SourcePlugin ABC
│   └── telegram.py              # TelegramRelaySource + signal parser
├── brokers/
│   ├── __init__.py
│   ├── base.py                  # BrokerPlugin ABC
│   └── kite.py                  # KiteBroker: auth (manual/totp), orders, LTP, OHLC
├── tsl/
│   ├── __init__.py
│   ├── base.py                  # TSLStrategy ABC
│   ├── fixed.py                 # FixedPctTSL
│   ├── stepped.py               # SteppedTSL
│   ├── atr.py                   # ATRTSLStrategy
│   ├── chandelier.py            # ChandelierTSL
│   ├── psar.py                  # ParabolicSARTSL
│   ├── factory.py               # build_tsl_strategy(config) → TSLStrategy
│   └── monitor.py               # TSLMonitor async task
└── fundamentals/
    ├── __init__.py
    └── fetcher.py               # async fundamentals fetch (yahoo/none)

tests/
├── conftest.py
├── test_config.py
├── core/
│   ├── test_events.py
│   └── test_dispatcher.py
├── sources/
│   └── test_telegram_parser.py
├── tsl/
│   ├── test_fixed.py
│   ├── test_stepped.py
│   ├── test_atr.py
│   ├── test_chandelier.py
│   ├── test_psar.py
│   ├── test_factory.py
│   └── test_monitor.py
└── fundamentals/
    └── test_fetcher.py

config.example.yaml
.env.example
requirements.txt
pytest.ini
systemd/trader.service
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `config.example.yaml`
- Create: `.env.example`
- Create: `trader/__init__.py`, `trader/core/__init__.py`, `trader/sources/__init__.py`, `trader/brokers/__init__.py`, `trader/tsl/__init__.py`, `trader/fundamentals/__init__.py`
- Create: `tests/__init__.py`, `tests/core/__init__.py`, `tests/sources/__init__.py`, `tests/tsl/__init__.py`, `tests/fundamentals/__init__.py`
- Create: `logs/.gitkeep`

- [ ] **Step 1: Create requirements.txt**

```
python-telegram-bot>=21.0
kiteconnect>=4.1.0
pyotp>=2.9.0
aiohttp>=3.9.0
pyyaml>=6.0.0
python-dotenv>=1.0.0
yfinance>=0.2.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
aioresponses>=0.7.6
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 3: Create config.example.yaml**

```yaml
trading:
  default_amount: 10000
  exchange: NSE
  product: CNC
  dedup_open_positions: true

tsl:
  default_mode: stepped
  default_pct: 5.0
  k: 3.0
  tiers:
    - [10, 8.0]
    - [30, 5.0]
    - [60, 3.0]
    - [.inf, 2.0]
  poll_interval_sec: 10

auth:
  mode: manual
  totp_secret_env: KITE_TOTP_SECRET

sources:
  telegram:
    api_id_env: TG_API_ID
    api_hash_env: TG_API_HASH
    relay_bot_token_env: TG_BOT_TOKEN
    watch_chats: []
    symbol_regex: "\\b([A-Z&]{2,20})\\b"

fundamentals:
  enabled: true
  provider: yahoo

log:
  trade_log: logs/trades.jsonl
  level: INFO
```

- [ ] **Step 4: Create .env.example**

```
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret
KITE_TOTP_SECRET=your_totp_secret_base32
TG_API_ID=your_telegram_api_id
TG_API_HASH=your_telegram_api_hash
TG_BOT_TOKEN=your_relay_bot_token
```

- [ ] **Step 5: Create all __init__.py and logs/.gitkeep**

```bash
mkdir -p trader/core trader/sources trader/brokers trader/tsl trader/fundamentals
mkdir -p tests/core tests/sources tests/tsl tests/fundamentals
mkdir -p logs systemd
touch trader/__init__.py trader/core/__init__.py trader/sources/__init__.py
touch trader/brokers/__init__.py trader/tsl/__init__.py trader/fundamentals/__init__.py
touch tests/__init__.py tests/core/__init__.py tests/sources/__init__.py
touch tests/tsl/__init__.py tests/fundamentals/__init__.py
touch logs/.gitkeep
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 7: Add .env and logs to .gitignore**

Append to `.gitignore`:
```
.env
logs/*.jsonl
.kite_session
```

- [ ] **Step 8: Commit**

```bash
git add requirements.txt pytest.ini config.example.yaml .env.example .gitignore trader/ tests/ logs/ systemd/
git commit -m "chore: scaffold project structure and dependencies"
```

---

## Task 2: Core Events

**Files:**
- Create: `trader/core/events.py`
- Create: `tests/core/test_events.py`

- [ ] **Step 1: Write failing test**

```python
# tests/core/test_events.py
from datetime import datetime, timezone
from trader.core.events import TradeSignal, Position, TradeRecord

def test_trade_signal_defaults():
    sig = TradeSignal(symbol="RELIANCE", exchange="NSE")
    assert sig.amount is None
    assert sig.tsl_mode is None
    assert sig.tsl_pct is None
    assert sig.tsl_tiers is None
    assert sig.tsl_k is None

def test_position_fields():
    now = datetime.now(timezone.utc)
    pos = Position(
        symbol="RELIANCE", exchange="NSE",
        qty=10, fill_price=2500.0,
        order_id="ord123", opened_at=now,
    )
    assert pos.qty == 10
    assert pos.fill_price == 2500.0

def test_trade_record_pnl():
    now = datetime.now(timezone.utc)
    rec = TradeRecord(
        symbol="RELIANCE", exchange="NSE",
        qty=10, buy_price=2500.0, sell_price=2750.0,
        pnl=2500.0, tsl_mode="fixed",
        opened_at=now, closed_at=now,
        fundamentals={},
    )
    assert rec.pnl == 2500.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_events.py -v
```

Expected: `ImportError: No module named 'trader.core.events'`

- [ ] **Step 3: Implement events.py**

```python
# trader/core/events.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TradeSignal:
    symbol: str
    exchange: str = "NSE"
    amount: float | None = None
    tsl_mode: str | None = None
    tsl_pct: float | None = None
    tsl_tiers: list[tuple[float, float]] | None = None
    tsl_k: float | None = None


@dataclass
class Position:
    symbol: str
    exchange: str
    qty: int
    fill_price: float
    order_id: str
    opened_at: datetime
    peak_price: float = field(init=False)

    def __post_init__(self) -> None:
        self.peak_price = self.fill_price


@dataclass
class TradeRecord:
    symbol: str
    exchange: str
    qty: int
    buy_price: float
    sell_price: float
    pnl: float
    tsl_mode: str
    opened_at: datetime
    closed_at: datetime
    fundamentals: dict
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_events.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/core/events.py tests/core/test_events.py
git commit -m "feat: add core event dataclasses (TradeSignal, Position, TradeRecord)"
```

---

## Task 3: Config Loader

**Files:**
- Create: `trader/config.py`
- Create: `tests/test_config.py`
- Create: `tests/fixtures/config_test.yaml`

- [ ] **Step 1: Create fixture config**

```bash
mkdir -p tests/fixtures
```

```yaml
# tests/fixtures/config_test.yaml
trading:
  default_amount: 5000
  exchange: NSE
  product: CNC
  dedup_open_positions: true

tsl:
  default_mode: fixed
  default_pct: 4.0
  k: 2.5
  tiers:
    - [10, 8.0]
    - [.inf, 3.0]
  poll_interval_sec: 5

auth:
  mode: manual
  totp_secret_env: KITE_TOTP_SECRET

sources:
  telegram:
    api_id_env: TG_API_ID
    api_hash_env: TG_API_HASH
    relay_bot_token_env: TG_BOT_TOKEN
    watch_chats: [-1001234567890]
    symbol_regex: "\\b([A-Z&]{2,20})\\b"

fundamentals:
  enabled: false
  provider: yahoo

log:
  trade_log: logs/trades.jsonl
  level: DEBUG
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from trader.config import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "config_test.yaml"


def test_load_trading_config():
    cfg = load_config(FIXTURE)
    assert cfg.trading.default_amount == 5000.0
    assert cfg.trading.exchange == "NSE"
    assert cfg.trading.product == "CNC"
    assert cfg.trading.dedup_open_positions is True


def test_load_tsl_config():
    cfg = load_config(FIXTURE)
    assert cfg.tsl.default_mode == "fixed"
    assert cfg.tsl.default_pct == 4.0
    assert cfg.tsl.k == 2.5
    assert cfg.tsl.poll_interval_sec == 5
    assert cfg.tsl.tiers == [(10.0, 8.0), (float("inf"), 3.0)]


def test_load_telegram_config():
    cfg = load_config(FIXTURE)
    tg = cfg.sources.telegram
    assert tg.watch_chats == [-1001234567890]
    assert tg.symbol_regex == r"\b([A-Z&]{2,20})\b"


def test_fundamentals_disabled():
    cfg = load_config(FIXTURE)
    assert cfg.fundamentals.enabled is False
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError: No module named 'trader.config'`

- [ ] **Step 4: Implement config.py**

```python
# trader/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import math
import yaml


@dataclass
class TradingConfig:
    default_amount: float = 10000.0
    exchange: str = "NSE"
    product: str = "CNC"
    dedup_open_positions: bool = True


@dataclass
class TSLConfig:
    default_mode: str = "stepped"
    default_pct: float = 5.0
    k: float = 3.0
    tiers: list[tuple[float, float]] = field(
        default_factory=lambda: [(10.0, 8.0), (30.0, 5.0), (60.0, 3.0), (math.inf, 2.0)]
    )
    poll_interval_sec: int = 10


@dataclass
class AuthConfig:
    mode: str = "manual"
    totp_secret_env: str = "KITE_TOTP_SECRET"


@dataclass
class TelegramConfig:
    api_id_env: str = "TG_API_ID"
    api_hash_env: str = "TG_API_HASH"
    relay_bot_token_env: str = "TG_BOT_TOKEN"
    watch_chats: list[int] = field(default_factory=list)
    symbol_regex: str = r"\b([A-Z&]{2,20})\b"


@dataclass
class SourcesConfig:
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


@dataclass
class FundamentalsConfig:
    enabled: bool = True
    provider: str = "yahoo"


@dataclass
class LogConfig:
    trade_log: str = "logs/trades.jsonl"
    level: str = "INFO"


@dataclass
class Config:
    trading: TradingConfig = field(default_factory=TradingConfig)
    tsl: TSLConfig = field(default_factory=TSLConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    fundamentals: FundamentalsConfig = field(default_factory=FundamentalsConfig)
    log: LogConfig = field(default_factory=LogConfig)


def _parse_tiers(raw: list) -> list[tuple[float, float]]:
    result = []
    for threshold, pct in raw:
        t = math.inf if threshold == math.inf or str(threshold) in (".inf", "inf") else float(threshold)
        result.append((t, float(pct)))
    return result


def load_config(path: str | Path = "config.yaml") -> Config:
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    t = data.get("trading", {})
    trading = TradingConfig(
        default_amount=float(t.get("default_amount", 10000.0)),
        exchange=t.get("exchange", "NSE"),
        product=t.get("product", "CNC"),
        dedup_open_positions=bool(t.get("dedup_open_positions", True)),
    )

    ts = data.get("tsl", {})
    raw_tiers = ts.get("tiers", [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)])
    tsl = TSLConfig(
        default_mode=ts.get("default_mode", "stepped"),
        default_pct=float(ts.get("default_pct", 5.0)),
        k=float(ts.get("k", 3.0)),
        tiers=_parse_tiers(raw_tiers),
        poll_interval_sec=int(ts.get("poll_interval_sec", 10)),
    )

    a = data.get("auth", {})
    auth = AuthConfig(
        mode=a.get("mode", "manual"),
        totp_secret_env=a.get("totp_secret_env", "KITE_TOTP_SECRET"),
    )

    tg_raw = data.get("sources", {}).get("telegram", {})
    telegram = TelegramConfig(
        api_id_env=tg_raw.get("api_id_env", "TG_API_ID"),
        api_hash_env=tg_raw.get("api_hash_env", "TG_API_HASH"),
        relay_bot_token_env=tg_raw.get("relay_bot_token_env", "TG_BOT_TOKEN"),
        watch_chats=[int(c) for c in tg_raw.get("watch_chats", [])],
        symbol_regex=tg_raw.get("symbol_regex", r"\b([A-Z&]{2,20})\b"),
    )

    fu = data.get("fundamentals", {})
    fundamentals = FundamentalsConfig(
        enabled=bool(fu.get("enabled", True)),
        provider=fu.get("provider", "yahoo"),
    )

    lo = data.get("log", {})
    log = LogConfig(
        trade_log=lo.get("trade_log", "logs/trades.jsonl"),
        level=lo.get("level", "INFO"),
    )

    return Config(
        trading=trading,
        tsl=tsl,
        auth=auth,
        sources=SourcesConfig(telegram=telegram),
        fundamentals=fundamentals,
        log=log,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add trader/config.py tests/test_config.py tests/fixtures/config_test.yaml
git commit -m "feat: add config loader with typed dataclasses"
```

---

## Task 4: Source Plugin ABC + Telegram Signal Parser

**Files:**
- Create: `trader/sources/base.py`
- Create: `trader/sources/telegram.py`
- Create: `tests/sources/test_telegram_parser.py`

- [ ] **Step 1: Write failing tests for the parser**

The parser is the only unit-testable part of the Telegram source (the bot connection requires a live API). Test it in isolation.

```python
# tests/sources/test_telegram_parser.py
import pytest
from trader.sources.telegram import parse_signal
from trader.core.events import TradeSignal

# Default symbol_regex = r"\b([A-Z&]{2,20})\b"
REGEX = r"\b([A-Z&]{2,20})\b"


def test_parse_plain_symbol():
    sig = parse_signal("RELIANCE Q3 earnings beat, buy now", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.symbol == "RELIANCE"
    assert sig.exchange == "NSE"
    assert sig.amount == 10000.0


def test_parse_symbol_with_ampersand():
    sig = parse_signal("M&M strong results", REGEX, default_amount=5000.0)
    assert sig is not None
    assert sig.symbol == "M&M"


def test_parse_override_amount():
    sig = parse_signal("INFY buy AMOUNT:20000", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.amount == 20000.0


def test_parse_override_tsl_mode():
    sig = parse_signal("TCS strong beat TSL:chandelier", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.tsl_mode == "chandelier"


def test_parse_override_tsl_pct():
    sig = parse_signal("WIPRO beat TSL_PCT:3.5", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.tsl_pct == 3.5


def test_parse_no_symbol_returns_none():
    sig = parse_signal("no uppercase symbols here 123", REGEX, default_amount=10000.0)
    assert sig is None


def test_parse_skips_common_words():
    # Common words like "BUY", "NSE", "BSE" are filtered
    sig = parse_signal("BUY RELIANCE on NSE now", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.symbol == "RELIANCE"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/sources/test_telegram_parser.py -v
```

Expected: `ImportError: No module named 'trader.sources.telegram'`

- [ ] **Step 3: Implement base.py**

```python
# trader/sources/base.py
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod


class SourcePlugin(ABC):
    @abstractmethod
    async def start(self, queue: asyncio.Queue) -> None:
        """Push TradeSignal events onto queue indefinitely. Run until cancelled."""
        ...
```

- [ ] **Step 4: Implement telegram.py**

```python
# trader/sources/telegram.py
from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from trader.core.events import TradeSignal
from trader.sources.base import SourcePlugin

if TYPE_CHECKING:
    from trader.config import TelegramConfig

logger = logging.getLogger(__name__)

# Words to skip when extracting the stock symbol from a message.
_SKIP_WORDS = frozenset({"BUY", "SELL", "NSE", "BSE", "THE", "AND", "FOR", "EPS", "YOY", "QOQ"})

# Inline override patterns embedded in the signal message.
_AMOUNT_RE = re.compile(r"AMOUNT:(\d+(?:\.\d+)?)", re.IGNORECASE)
_TSL_MODE_RE = re.compile(r"TSL:(fixed|stepped|atr|chandelier|psar)", re.IGNORECASE)
_TSL_PCT_RE = re.compile(r"TSL_PCT:(\d+(?:\.\d+)?)", re.IGNORECASE)
_TSL_K_RE = re.compile(r"TSL_K:(\d+(?:\.\d+)?)", re.IGNORECASE)


def parse_signal(
    text: str,
    symbol_regex: str,
    default_amount: float,
) -> TradeSignal | None:
    """Extract a TradeSignal from raw message text. Returns None if no symbol found."""
    # Extract inline overrides first (so their tokens don't confuse symbol detection).
    amount_match = _AMOUNT_RE.search(text)
    amount = float(amount_match.group(1)) if amount_match else default_amount

    tsl_mode_match = _TSL_MODE_RE.search(text)
    tsl_mode = tsl_mode_match.group(1).lower() if tsl_mode_match else None

    tsl_pct_match = _TSL_PCT_RE.search(text)
    tsl_pct = float(tsl_pct_match.group(1)) if tsl_pct_match else None

    tsl_k_match = _TSL_K_RE.search(text)
    tsl_k = float(tsl_k_match.group(1)) if tsl_k_match else None

    # Find stock symbol: first match of symbol_regex not in skip list.
    for match in re.finditer(symbol_regex, text):
        candidate = match.group(1)
        if candidate not in _SKIP_WORDS:
            return TradeSignal(
                symbol=candidate,
                exchange="NSE",
                amount=amount,
                tsl_mode=tsl_mode,
                tsl_pct=tsl_pct,
                tsl_k=tsl_k,
            )

    return None


class TelegramRelaySource(SourcePlugin):
    def __init__(self, cfg: TelegramConfig, default_amount: float) -> None:
        self._token = os.environ[cfg.relay_bot_token_env]
        self._watch_chats: set[int] = set(cfg.watch_chats)
        self._symbol_regex = cfg.symbol_regex
        self._default_amount = default_amount

    async def start(self, queue: asyncio.Queue) -> None:
        app = Application.builder().token(self._token).build()

        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.message or not update.message.text:
                return
            chat_id = update.effective_chat.id
            if self._watch_chats and chat_id not in self._watch_chats:
                return
            text = update.message.text
            signal = parse_signal(text, self._symbol_regex, self._default_amount)
            if signal:
                logger.info("Signal parsed: %s from chat %d", signal.symbol, chat_id)
                await queue.put(signal)
            else:
                logger.debug("No signal in message from chat %d: %r", chat_id, text[:80])

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

        async with app:
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            try:
                await asyncio.get_event_loop().create_future()  # run forever
            finally:
                await app.updater.stop()
                await app.stop()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/sources/test_telegram_parser.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add trader/sources/base.py trader/sources/telegram.py tests/sources/test_telegram_parser.py
git commit -m "feat: add SourcePlugin ABC and Telegram relay source with signal parser"
```

---

## Task 5: Broker Plugin ABC

**Files:**
- Create: `trader/brokers/base.py`

No test needed — pure ABC, behaviour tested via Kite implementation.

- [ ] **Step 1: Implement base.py**

```python
# trader/brokers/base.py
from __future__ import annotations
from abc import ABC, abstractmethod

from trader.core.events import Position, TradeSignal


class BrokerPlugin(ABC):

    @abstractmethod
    async def place_buy(self, signal: TradeSignal) -> Position:
        """Place a market buy. Returns filled Position."""
        ...

    @abstractmethod
    async def place_sell(self, position: Position) -> float:
        """Place a market sell. Returns fill price."""
        ...

    @abstractmethod
    async def get_ltp(self, symbol: str, exchange: str) -> float:
        """Return last traded price."""
        ...

    @abstractmethod
    async def get_ohlc(self, symbol: str, exchange: str, days: int = 20) -> list[dict]:
        """Return list of daily candles: [{date, open, high, low, close, volume}, ...]."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Return open positions from broker (used for startup recovery)."""
        ...
```

- [ ] **Step 2: Commit**

```bash
git add trader/brokers/base.py
git commit -m "feat: add BrokerPlugin ABC"
```

---

## Task 6: TSL Strategy Base

**Files:**
- Create: `trader/tsl/base.py`

- [ ] **Step 1: Implement base.py**

```python
# trader/tsl/base.py
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trader.brokers.base import BrokerPlugin
    from trader.core.events import Position


class TSLStrategy(ABC):

    @abstractmethod
    def initial_stop(self, fill_price: float) -> float:
        """Compute stop price at position entry."""
        ...

    @abstractmethod
    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        """Called on each LTP poll tick. Must never return a value lower than current_stop."""
        ...

    def should_exit(self, ltp: float, stop: float) -> bool:
        """Return True when position should be closed."""
        return ltp <= stop

    async def on_position_opened(self, position: Position, broker: BrokerPlugin) -> None:
        """Override for strategies that need async setup (e.g., fetching historical OHLC)."""
        pass
```

- [ ] **Step 2: Commit**

```bash
git add trader/tsl/base.py
git commit -m "feat: add TSLStrategy ABC"
```

---

## Task 7: FixedPctTSL

**Files:**
- Create: `trader/tsl/fixed.py`
- Create: `tests/tsl/test_fixed.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_fixed.py
import pytest
from trader.tsl.fixed import FixedPctTSL


def test_initial_stop():
    s = FixedPctTSL(pct=5.0)
    assert s.initial_stop(1000.0) == pytest.approx(950.0)


def test_update_stop_rises_with_peak():
    s = FixedPctTSL(pct=5.0)
    stop = s.initial_stop(1000.0)      # 950
    stop = s.update_stop(stop, ltp=1200.0, peak=1200.0)
    assert stop == pytest.approx(1140.0)


def test_update_stop_never_decreases():
    s = FixedPctTSL(pct=5.0)
    stop = s.initial_stop(1000.0)      # 950
    stop = s.update_stop(stop, ltp=1200.0, peak=1200.0)  # 1140
    stop = s.update_stop(stop, ltp=1100.0, peak=1200.0)  # peak unchanged → 1140
    assert stop == pytest.approx(1140.0)


def test_should_exit_when_ltp_at_stop():
    s = FixedPctTSL(pct=5.0)
    stop = s.initial_stop(1000.0)
    assert s.should_exit(ltp=950.0, stop=stop) is True


def test_should_not_exit_above_stop():
    s = FixedPctTSL(pct=5.0)
    stop = s.initial_stop(1000.0)
    assert s.should_exit(ltp=960.0, stop=stop) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_fixed.py -v
```

Expected: `ImportError: No module named 'trader.tsl.fixed'`

- [ ] **Step 3: Implement fixed.py**

```python
# trader/tsl/fixed.py
from trader.tsl.base import TSLStrategy


class FixedPctTSL(TSLStrategy):
    def __init__(self, pct: float) -> None:
        self._pct = pct

    def initial_stop(self, fill_price: float) -> float:
        return fill_price * (1 - self._pct / 100)

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        candidate = peak * (1 - self._pct / 100)
        return max(current_stop, candidate)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_fixed.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/fixed.py tests/tsl/test_fixed.py
git commit -m "feat: add FixedPctTSL strategy"
```

---

## Task 8: SteppedTSL

**Files:**
- Create: `trader/tsl/stepped.py`
- Create: `tests/tsl/test_stepped.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_stepped.py
import math
import pytest
from trader.tsl.stepped import SteppedTSL

TIERS = [(10.0, 8.0), (30.0, 5.0), (60.0, 3.0), (math.inf, 2.0)]


def test_initial_stop_uses_first_tier():
    s = SteppedTSL(tiers=TIERS)
    # At entry, gain = 0, so first tier applies (8%)
    assert s.initial_stop(1000.0) == pytest.approx(920.0)


def test_update_stop_tier_transitions():
    s = SteppedTSL(tiers=TIERS)
    fill = 1000.0
    stop = s.initial_stop(fill)

    # gain 5% → still tier 0 (8%)
    stop = s.update_stop(stop, ltp=1050.0, peak=1050.0)
    assert stop == pytest.approx(1050.0 * 0.92)

    # gain 15% → tier 1 (5%)
    stop = s.update_stop(stop, ltp=1150.0, peak=1150.0)
    assert stop == pytest.approx(1150.0 * 0.95)

    # gain 35% → tier 2 (3%)
    stop = s.update_stop(stop, ltp=1350.0, peak=1350.0)
    assert stop == pytest.approx(1350.0 * 0.97)

    # gain 70% → tier 3 (2%)
    stop = s.update_stop(stop, ltp=1700.0, peak=1700.0)
    assert stop == pytest.approx(1700.0 * 0.98)


def test_update_stop_never_decreases():
    s = SteppedTSL(tiers=TIERS)
    fill = 1000.0
    stop = s.initial_stop(fill)
    stop = s.update_stop(stop, ltp=1500.0, peak=1500.0)
    high_stop = stop
    # price falls back, peak unchanged
    stop = s.update_stop(stop, ltp=1400.0, peak=1500.0)
    assert stop == pytest.approx(high_stop)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_stepped.py -v
```

Expected: `ImportError: No module named 'trader.tsl.stepped'`

- [ ] **Step 3: Implement stepped.py**

```python
# trader/tsl/stepped.py
from __future__ import annotations
import math
from trader.tsl.base import TSLStrategy


class SteppedTSL(TSLStrategy):
    def __init__(self, tiers: list[tuple[float, float]]) -> None:
        # tiers: [(gain_threshold_pct, tsl_pct), ...] sorted ascending by threshold
        self._tiers = sorted(tiers, key=lambda x: x[0])

    def _tsl_pct(self, peak: float, fill_price: float) -> float:
        gain_pct = (peak / fill_price - 1) * 100
        for threshold, pct in self._tiers:
            if gain_pct < threshold:
                return pct
        return self._tiers[-1][1]

    def initial_stop(self, fill_price: float) -> float:
        self._fill_price = fill_price
        first_pct = self._tiers[0][1]
        return fill_price * (1 - first_pct / 100)

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        pct = self._tsl_pct(peak, self._fill_price)
        candidate = peak * (1 - pct / 100)
        return max(current_stop, candidate)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_stepped.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/stepped.py tests/tsl/test_stepped.py
git commit -m "feat: add SteppedTSL strategy"
```

---

## Task 9: ATRTSLStrategy

**Files:**
- Create: `trader/tsl/atr.py`
- Create: `tests/tsl/test_atr.py`

The strategy fetches historical OHLC via `on_position_opened` and computes ATR once at entry. ATR is reused for the session (daily candles change slowly).

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_atr.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from trader.tsl.atr import ATRTSLStrategy, compute_atr
from trader.core.events import Position
from datetime import datetime, timezone


def make_candles(closes: list[float], spread: float = 10.0) -> list[dict]:
    candles = []
    for i, c in enumerate(closes):
        candles.append({
            "high": c + spread / 2,
            "low": c - spread / 2,
            "close": c,
        })
    return candles


def test_compute_atr_basic():
    candles = make_candles([100.0] * 20, spread=10.0)
    atr = compute_atr(candles, period=14)
    assert atr == pytest.approx(10.0, rel=0.01)


def test_compute_atr_requires_enough_candles():
    with pytest.raises(ValueError, match="Need at least"):
        compute_atr(make_candles([100.0] * 5), period=14)


@pytest.mark.asyncio
async def test_on_position_opened_sets_atr():
    strategy = ATRTSLStrategy(k=2.0, period=14)
    candles = make_candles([100.0] * 20, spread=10.0)

    broker = MagicMock()
    broker.get_ohlc = AsyncMock(return_value=candles)

    now = datetime.now(timezone.utc)
    pos = Position("RELIANCE", "NSE", 10, 1000.0, "ord1", now)
    await strategy.on_position_opened(pos, broker)

    assert strategy._atr == pytest.approx(10.0, rel=0.01)


@pytest.mark.asyncio
async def test_initial_stop_after_init():
    strategy = ATRTSLStrategy(k=2.0, period=14)
    candles = make_candles([100.0] * 20, spread=10.0)
    broker = MagicMock()
    broker.get_ohlc = AsyncMock(return_value=candles)

    now = datetime.now(timezone.utc)
    pos = Position("RELIANCE", "NSE", 10, 1000.0, "ord1", now)
    await strategy.on_position_opened(pos, broker)

    # stop = fill_price - k * ATR = 1000 - 2 * 10 = 980
    assert strategy.initial_stop(1000.0) == pytest.approx(980.0, rel=0.01)


@pytest.mark.asyncio
async def test_update_stop_rises_with_peak():
    strategy = ATRTSLStrategy(k=2.0, period=14)
    candles = make_candles([100.0] * 20, spread=10.0)
    broker = MagicMock()
    broker.get_ohlc = AsyncMock(return_value=candles)

    now = datetime.now(timezone.utc)
    pos = Position("RELIANCE", "NSE", 10, 1000.0, "ord1", now)
    await strategy.on_position_opened(pos, broker)

    stop = strategy.initial_stop(1000.0)  # 980
    stop = strategy.update_stop(stop, ltp=1200.0, peak=1200.0)
    # 1200 - 2 * 10 = 1180
    assert stop == pytest.approx(1180.0, rel=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_atr.py -v
```

Expected: `ImportError: No module named 'trader.tsl.atr'`

- [ ] **Step 3: Implement atr.py**

```python
# trader/tsl/atr.py
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from trader.tsl.base import TSLStrategy

if TYPE_CHECKING:
    from trader.brokers.base import BrokerPlugin
    from trader.core.events import Position

logger = logging.getLogger(__name__)


def compute_atr(candles: list[dict], period: int = 14) -> float:
    if len(candles) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles, got {len(candles)}")
    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period


class ATRTSLStrategy(TSLStrategy):
    def __init__(self, k: float = 2.0, period: int = 14) -> None:
        self._k = k
        self._period = period
        self._atr: float = 0.0

    async def on_position_opened(self, position: Position, broker: BrokerPlugin) -> None:
        candles = await broker.get_ohlc(position.symbol, position.exchange, days=self._period + 5)
        self._atr = compute_atr(candles, self._period)
        logger.debug("ATR(%d) for %s = %.4f", self._period, position.symbol, self._atr)

    def initial_stop(self, fill_price: float) -> float:
        return fill_price - self._k * self._atr

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        candidate = peak - self._k * self._atr
        return max(current_stop, candidate)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_atr.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/atr.py tests/tsl/test_atr.py
git commit -m "feat: add ATRTSLStrategy with historical OHLC fetch"
```

---

## Task 10: ChandelierTSL

**Files:**
- Create: `trader/tsl/chandelier.py`
- Create: `tests/tsl/test_chandelier.py`

Stop = highest high over last `period` candles − k × ATR. Fetched at entry.

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_chandelier.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from trader.tsl.chandelier import ChandelierTSL
from trader.core.events import Position
from datetime import datetime, timezone


def make_candles(highs: list[float], lows: list[float], closes: list[float]) -> list[dict]:
    return [{"high": h, "low": l, "close": c} for h, l, c in zip(highs, lows, closes)]


@pytest.mark.asyncio
async def test_initial_stop_chandelier():
    # 20 candles, all highs = 1100, lows = 990, closes = 1050 → spread = 110
    candles = make_candles(
        highs=[1100.0] * 20,
        lows=[990.0] * 20,
        closes=[1050.0] * 20,
    )
    broker = MagicMock()
    broker.get_ohlc = AsyncMock(return_value=candles)

    strategy = ChandelierTSL(k=3.0, period=14)
    now = datetime.now(timezone.utc)
    pos = Position("TCS", "NSE", 5, 1000.0, "ord2", now)
    await strategy.on_position_opened(pos, broker)

    # highest_high = 1100, ATR ≈ 110 (spread-based), stop = 1100 - 3*110 = 770
    stop = strategy.initial_stop(1000.0)
    assert stop == pytest.approx(1100.0 - 3.0 * strategy._atr, rel=0.01)


@pytest.mark.asyncio
async def test_update_stop_rises_as_peak_rises():
    candles = make_candles(
        highs=[1100.0] * 20,
        lows=[990.0] * 20,
        closes=[1050.0] * 20,
    )
    broker = MagicMock()
    broker.get_ohlc = AsyncMock(return_value=candles)

    strategy = ChandelierTSL(k=3.0, period=14)
    now = datetime.now(timezone.utc)
    pos = Position("TCS", "NSE", 5, 1000.0, "ord2", now)
    await strategy.on_position_opened(pos, broker)

    stop = strategy.initial_stop(1000.0)
    new_peak = 1300.0
    stop2 = strategy.update_stop(stop, ltp=1300.0, peak=new_peak)
    assert stop2 == pytest.approx(new_peak - 3.0 * strategy._atr, rel=0.01)
    assert stop2 > stop
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_chandelier.py -v
```

Expected: `ImportError: No module named 'trader.tsl.chandelier'`

- [ ] **Step 3: Implement chandelier.py**

```python
# trader/tsl/chandelier.py
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from trader.tsl.atr import compute_atr
from trader.tsl.base import TSLStrategy

if TYPE_CHECKING:
    from trader.brokers.base import BrokerPlugin
    from trader.core.events import Position

logger = logging.getLogger(__name__)


class ChandelierTSL(TSLStrategy):
    def __init__(self, k: float = 3.0, period: int = 14) -> None:
        self._k = k
        self._period = period
        self._atr: float = 0.0
        self._highest_high: float = 0.0

    async def on_position_opened(self, position: Position, broker: BrokerPlugin) -> None:
        candles = await broker.get_ohlc(position.symbol, position.exchange, days=self._period + 5)
        self._atr = compute_atr(candles, self._period)
        self._highest_high = max(c["high"] for c in candles[-self._period:])
        logger.debug(
            "Chandelier for %s: ATR=%.4f, HH=%.2f",
            position.symbol, self._atr, self._highest_high,
        )

    def initial_stop(self, fill_price: float) -> float:
        return self._highest_high - self._k * self._atr

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        # Use running peak as proxy for highest high post-entry
        candidate = peak - self._k * self._atr
        return max(current_stop, candidate)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_chandelier.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/chandelier.py tests/tsl/test_chandelier.py
git commit -m "feat: add ChandelierTSL strategy"
```

---

## Task 11: ParabolicSARTSL

**Files:**
- Create: `trader/tsl/psar.py`
- Create: `tests/tsl/test_psar.py`

Implements Parabolic SAR using running LTP as price. Tracks EP (extreme point = peak LTP), AF (acceleration factor). SAR = SAR + AF × (EP − SAR). Stop accelerates toward price as trend extends.

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_psar.py
import pytest
from trader.tsl.psar import ParabolicSARTSL


def test_initial_stop_below_fill():
    s = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
    stop = s.initial_stop(1000.0)
    assert stop < 1000.0


def test_sar_rises_as_peak_rises():
    s = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
    stop = s.initial_stop(1000.0)

    # Simulate 5 ticks of rising price with new highs each tick
    prices = [1050.0, 1100.0, 1150.0, 1200.0, 1250.0]
    for p in prices:
        stop = s.update_stop(stop, ltp=p, peak=p)

    assert stop > s.initial_stop(1000.0)


def test_af_caps_at_max():
    s = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
    stop = s.initial_stop(1000.0)
    # Drive 20+ new highs to force AF to cap
    for i in range(25):
        price = 1000.0 + i * 10
        stop = s.update_stop(stop, ltp=price, peak=price)
    assert s._af == pytest.approx(0.20)


def test_should_exit_when_ltp_below_sar():
    s = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
    stop = s.initial_stop(1000.0)
    # Simulate price drop immediately — stop will still be initial_stop
    assert s.should_exit(ltp=stop - 1, stop=stop) is True


def test_sar_never_decreases():
    s = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
    stop = s.initial_stop(1000.0)
    stop = s.update_stop(stop, ltp=1200.0, peak=1200.0)
    high_stop = stop
    # Peak stays at 1200, price pulls back
    stop = s.update_stop(stop, ltp=1100.0, peak=1200.0)
    assert stop >= high_stop
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_psar.py -v
```

Expected: `ImportError: No module named 'trader.tsl.psar'`

- [ ] **Step 3: Implement psar.py**

```python
# trader/tsl/psar.py
from trader.tsl.base import TSLStrategy


class ParabolicSARTSL(TSLStrategy):
    def __init__(
        self,
        af_start: float = 0.02,
        af_step: float = 0.02,
        af_max: float = 0.20,
    ) -> None:
        self._af_start = af_start
        self._af_step = af_step
        self._af_max = af_max
        self._af: float = af_start
        self._ep: float = 0.0   # extreme point (highest LTP seen)
        self._sar: float = 0.0  # current SAR value

    def initial_stop(self, fill_price: float) -> float:
        # Start SAR 2% below fill; EP = fill price
        self._sar = fill_price * (1 - self._af_start)
        self._ep = fill_price
        self._af = self._af_start
        return self._sar

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        if peak > self._ep:
            self._ep = peak
            self._af = min(self._af + self._af_step, self._af_max)
        self._sar = self._sar + self._af * (self._ep - self._sar)
        return max(current_stop, self._sar)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_psar.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/psar.py tests/tsl/test_psar.py
git commit -m "feat: add ParabolicSARTSL strategy"
```

---

## Task 12: TSL Factory

**Files:**
- Create: `trader/tsl/factory.py`
- Create: `tests/tsl/test_factory.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_factory.py
import math
import pytest
from trader.tsl.factory import build_tsl_strategy
from trader.tsl.fixed import FixedPctTSL
from trader.tsl.stepped import SteppedTSL
from trader.tsl.atr import ATRTSLStrategy
from trader.tsl.chandelier import ChandelierTSL
from trader.tsl.psar import ParabolicSARTSL
from trader.config import TSLConfig


def test_build_fixed():
    cfg = TSLConfig(default_mode="fixed", default_pct=4.0)
    s = build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
    assert isinstance(s, FixedPctTSL)


def test_build_stepped():
    cfg = TSLConfig(default_mode="stepped")
    s = build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
    assert isinstance(s, SteppedTSL)


def test_build_atr():
    cfg = TSLConfig(default_mode="atr", k=2.0)
    s = build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
    assert isinstance(s, ATRTSLStrategy)


def test_build_chandelier():
    cfg = TSLConfig(default_mode="chandelier", k=3.0)
    s = build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
    assert isinstance(s, ChandelierTSL)


def test_build_psar():
    cfg = TSLConfig(default_mode="psar")
    s = build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
    assert isinstance(s, ParabolicSARTSL)


def test_signal_overrides_config_mode():
    cfg = TSLConfig(default_mode="fixed", default_pct=5.0)
    s = build_tsl_strategy(cfg, signal_tsl_mode="chandelier", signal_tsl_pct=None, signal_tsl_k=2.5, signal_tsl_tiers=None)
    assert isinstance(s, ChandelierTSL)


def test_unknown_mode_raises():
    cfg = TSLConfig(default_mode="bogus")
    with pytest.raises(ValueError, match="Unknown TSL mode"):
        build_tsl_strategy(cfg, signal_tsl_mode=None, signal_tsl_pct=None, signal_tsl_k=None, signal_tsl_tiers=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_factory.py -v
```

Expected: `ImportError: No module named 'trader.tsl.factory'`

- [ ] **Step 3: Implement factory.py**

```python
# trader/tsl/factory.py
from __future__ import annotations

from trader.config import TSLConfig
from trader.tsl.atr import ATRTSLStrategy
from trader.tsl.base import TSLStrategy
from trader.tsl.chandelier import ChandelierTSL
from trader.tsl.fixed import FixedPctTSL
from trader.tsl.psar import ParabolicSARTSL
from trader.tsl.stepped import SteppedTSL


def build_tsl_strategy(
    cfg: TSLConfig,
    signal_tsl_mode: str | None,
    signal_tsl_pct: float | None,
    signal_tsl_k: float | None,
    signal_tsl_tiers: list[tuple[float, float]] | None,
) -> TSLStrategy:
    """Build a TSLStrategy from config, with per-signal overrides applied."""
    mode = signal_tsl_mode or cfg.default_mode
    k = signal_tsl_k or cfg.k
    pct = signal_tsl_pct or cfg.default_pct
    tiers = signal_tsl_tiers or cfg.tiers

    match mode:
        case "fixed":
            return FixedPctTSL(pct=pct)
        case "stepped":
            return SteppedTSL(tiers=tiers)
        case "atr":
            return ATRTSLStrategy(k=k)
        case "chandelier":
            return ChandelierTSL(k=k)
        case "psar":
            return ParabolicSARTSL()
        case _:
            raise ValueError(f"Unknown TSL mode: {mode!r}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_factory.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/factory.py tests/tsl/test_factory.py
git commit -m "feat: add TSL strategy factory with per-signal overrides"
```

---

## Task 13: TSL Monitor

**Files:**
- Create: `trader/tsl/monitor.py`
- Create: `tests/tsl/test_monitor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/tsl/test_monitor.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from trader.tsl.monitor import TSLMonitor
from trader.tsl.fixed import FixedPctTSL
from trader.core.events import Position


def make_position(fill_price: float = 1000.0) -> Position:
    return Position("RELIANCE", "NSE", 10, fill_price, "ord1", datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_monitor_calls_sell_when_stop_hit():
    strategy = FixedPctTSL(pct=5.0)
    broker = MagicMock()
    broker.get_ltp = AsyncMock(side_effect=[1100.0, 1200.0, 1140.0])  # rises then drops to stop
    broker.place_sell = AsyncMock(return_value=1140.0)

    pos = make_position(1000.0)
    on_closed = AsyncMock()

    monitor = TSLMonitor(
        position=pos,
        strategy=strategy,
        broker=broker,
        poll_interval=0,
        on_closed=on_closed,
    )
    await monitor.run()

    broker.place_sell.assert_called_once_with(pos)
    on_closed.assert_called_once()


@pytest.mark.asyncio
async def test_monitor_updates_peak():
    strategy = FixedPctTSL(pct=5.0)
    broker = MagicMock()
    # Returns rising prices then drops to stop
    broker.get_ltp = AsyncMock(side_effect=[1050.0, 1100.0, 1200.0, 1140.0])
    broker.place_sell = AsyncMock(return_value=1140.0)

    pos = make_position(1000.0)
    on_closed = AsyncMock()

    monitor = TSLMonitor(
        position=pos,
        strategy=strategy,
        broker=broker,
        poll_interval=0,
        on_closed=on_closed,
    )
    await monitor.run()

    assert pos.peak_price == 1200.0


@pytest.mark.asyncio
async def test_monitor_retries_on_ltp_failure():
    strategy = FixedPctTSL(pct=5.0)
    broker = MagicMock()
    # Two failures then success then stop hit
    broker.get_ltp = AsyncMock(
        side_effect=[Exception("timeout"), Exception("timeout"), 1000.0, 940.0]
    )
    broker.place_sell = AsyncMock(return_value=940.0)
    on_closed = AsyncMock()

    pos = make_position(1000.0)
    monitor = TSLMonitor(
        position=pos,
        strategy=strategy,
        broker=broker,
        poll_interval=0,
        on_closed=on_closed,
        max_ltp_retries=3,
    )
    await monitor.run()

    broker.place_sell.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tsl/test_monitor.py -v
```

Expected: `ImportError: No module named 'trader.tsl.monitor'`

- [ ] **Step 3: Implement monitor.py**

```python
# trader/tsl/monitor.py
from __future__ import annotations
import asyncio
import logging
from typing import Awaitable, Callable

from trader.brokers.base import BrokerPlugin
from trader.core.events import Position
from trader.tsl.base import TSLStrategy

logger = logging.getLogger(__name__)


class TSLMonitor:
    def __init__(
        self,
        position: Position,
        strategy: TSLStrategy,
        broker: BrokerPlugin,
        poll_interval: float,
        on_closed: Callable[[Position, float], Awaitable[None]],
        max_ltp_retries: int = 3,
    ) -> None:
        self._position = position
        self._strategy = strategy
        self._broker = broker
        self._poll_interval = poll_interval
        self._on_closed = on_closed
        self._max_retries = max_ltp_retries

    async def run(self) -> None:
        pos = self._position
        stop = self._strategy.initial_stop(pos.fill_price)
        logger.info("TSL monitor started for %s | fill=%.2f stop=%.2f", pos.symbol, pos.fill_price, stop)

        while True:
            if self._poll_interval > 0:
                await asyncio.sleep(self._poll_interval)

            ltp = await self._fetch_ltp_with_retry(pos)
            if ltp is None:
                logger.error("LTP fetch failed after %d retries for %s — halting monitor", self._max_retries, pos.symbol)
                return

            if ltp > pos.peak_price:
                pos.peak_price = ltp

            stop = self._strategy.update_stop(stop, ltp=ltp, peak=pos.peak_price)
            logger.debug("%s | ltp=%.2f peak=%.2f stop=%.2f", pos.symbol, ltp, pos.peak_price, stop)

            if self._strategy.should_exit(ltp=ltp, stop=stop):
                logger.info("TSL triggered for %s | ltp=%.2f stop=%.2f", pos.symbol, ltp, stop)
                sell_price = await self._broker.place_sell(pos)
                await self._on_closed(pos, sell_price)
                return

    async def _fetch_ltp_with_retry(self, pos: Position) -> float | None:
        for attempt in range(1, self._max_retries + 1):
            try:
                return await self._broker.get_ltp(pos.symbol, pos.exchange)
            except Exception as exc:
                logger.warning("LTP fetch attempt %d/%d failed for %s: %s", attempt, self._max_retries, pos.symbol, exc)
                if attempt < self._max_retries:
                    await asyncio.sleep(2 ** attempt)
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tsl/test_monitor.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/tsl/monitor.py tests/tsl/test_monitor.py
git commit -m "feat: add TSLMonitor async task with retry on LTP failure"
```

---

## Task 14: Fundamentals Fetcher

**Files:**
- Create: `trader/fundamentals/fetcher.py`
- Create: `tests/fundamentals/test_fetcher.py`

Uses `yfinance` (wrapped in `asyncio.to_thread`) for the `yahoo` provider. Returns a dict for logging; never raises — always returns `{}` on failure.

- [ ] **Step 1: Write failing tests**

```python
# tests/fundamentals/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
from trader.fundamentals.fetcher import fetch_fundamentals


@pytest.mark.asyncio
async def test_fetch_returns_dict_on_success():
    mock_info = {
        "trailingPE": 25.3,
        "trailingEps": 112.5,
        "totalRevenue": 5_000_000_000,
        "debtToEquity": 0.43,
    }
    mock_ticker = MagicMock()
    mock_ticker.info = mock_info

    with patch("trader.fundamentals.fetcher.yf.Ticker", return_value=mock_ticker):
        result = await fetch_fundamentals("RELIANCE", provider="yahoo")

    assert result["pe_ratio"] == 25.3
    assert result["eps"] == 112.5
    assert result["revenue"] == 5_000_000_000
    assert result["debt_to_equity"] == 0.43


@pytest.mark.asyncio
async def test_fetch_returns_empty_dict_on_error():
    with patch("trader.fundamentals.fetcher.yf.Ticker", side_effect=Exception("network error")):
        result = await fetch_fundamentals("RELIANCE", provider="yahoo")
    assert result == {}


@pytest.mark.asyncio
async def test_fetch_returns_empty_dict_for_none_provider():
    result = await fetch_fundamentals("RELIANCE", provider="none")
    assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/fundamentals/test_fetcher.py -v
```

Expected: `ImportError: No module named 'trader.fundamentals.fetcher'`

- [ ] **Step 3: Implement fetcher.py**

```python
# trader/fundamentals/fetcher.py
from __future__ import annotations
import asyncio
import logging

import yfinance as yf

logger = logging.getLogger(__name__)

_NSE_SUFFIX = ".NS"


def _yahoo_fetch_sync(symbol: str) -> dict:
    ticker = yf.Ticker(symbol + _NSE_SUFFIX)
    info = ticker.info
    return {
        "pe_ratio": info.get("trailingPE"),
        "eps": info.get("trailingEps"),
        "revenue": info.get("totalRevenue"),
        "debt_to_equity": info.get("debtToEquity"),
        "market_cap": info.get("marketCap"),
        "52w_high": info.get("fiftyTwoWeekHigh"),
        "52w_low": info.get("fiftyTwoWeekLow"),
    }


async def fetch_fundamentals(symbol: str, provider: str) -> dict:
    """Fetch fundamentals for symbol. Always returns a dict; returns {} on any failure."""
    if provider == "none":
        return {}
    if provider == "yahoo":
        try:
            return await asyncio.to_thread(_yahoo_fetch_sync, symbol)
        except Exception as exc:
            logger.warning("Fundamentals fetch failed for %s: %s", symbol, exc)
            return {}
    logger.warning("Unknown fundamentals provider %r — skipping", provider)
    return {}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/fundamentals/test_fetcher.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/fundamentals/fetcher.py tests/fundamentals/test_fetcher.py
git commit -m "feat: add async fundamentals fetcher (Yahoo Finance)"
```

---

## Task 15: Kite Broker

**Files:**
- Create: `trader/brokers/kite.py`

Wraps the synchronous `kiteconnect` library with `asyncio.to_thread`. Handles both `manual` and `totp` auth modes. Caches the instrument token map on first use.

No automated tests (requires live Kite credentials). Integration tested manually.

- [ ] **Step 1: Implement kite.py**

```python
# trader/brokers/kite.py
from __future__ import annotations
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyotp
from kiteconnect import KiteConnect

from trader.brokers.base import BrokerPlugin
from trader.config import AuthConfig, TradingConfig
from trader.core.events import Position, TradeSignal

logger = logging.getLogger(__name__)

_SESSION_FILE = Path(".kite_session")
_INSTRUMENT_CACHE: dict[str, int] = {}  # "NSE:RELIANCE" → instrument_token


class KiteBroker(BrokerPlugin):
    def __init__(self, trading_cfg: TradingConfig, auth_cfg: AuthConfig) -> None:
        self._trading = trading_cfg
        self._auth = auth_cfg
        self._api_key = os.environ["KITE_API_KEY"]
        self._api_secret = os.environ["KITE_API_SECRET"]
        self._kite = KiteConnect(api_key=self._api_key)

    # ------------------------------------------------------------------ auth

    async def authenticate(self) -> None:
        """Load cached session or trigger login flow based on auth.mode."""
        if _SESSION_FILE.exists():
            token = _SESSION_FILE.read_text().strip()
            self._kite.set_access_token(token)
            logger.info("Loaded cached Kite session")
            return

        if self._auth.mode == "totp":
            await self._totp_login()
        else:
            await self._manual_login()

    async def _totp_login(self) -> None:
        secret = os.environ[self._auth.totp_secret_env]
        totp = pyotp.TOTP(secret).now()
        # kiteconnect login flow requires a browser redirect; pyotp only generates TOTP.
        # Full TOTP automation requires selenium or a headless browser.
        # For now, use the request_token already exchanged externally.
        raise NotImplementedError(
            "Fully headless TOTP login requires selenium. "
            "Use mode=manual and run `python -m trader.brokers.kite auth` daily, "
            "or implement selenium-based login and replace this method."
        )

    async def _manual_login(self) -> None:
        login_url = self._kite.login_url()
        print(f"\nOpen in browser and complete login:\n{login_url}\n")
        request_token = input("Paste request_token from redirect URL: ").strip()
        data = await asyncio.to_thread(
            self._kite.generate_session, request_token, api_secret=self._api_secret
        )
        access_token = data["access_token"]
        self._kite.set_access_token(access_token)
        _SESSION_FILE.write_text(access_token)
        logger.info("Kite session established and cached")

    # ------------------------------------------------------------------ instrument cache

    async def _get_instrument_token(self, symbol: str, exchange: str) -> int:
        key = f"{exchange}:{symbol}"
        if key not in _INSTRUMENT_CACHE:
            instruments = await asyncio.to_thread(self._kite.instruments, exchange)
            for inst in instruments:
                _INSTRUMENT_CACHE[f"{inst['exchange']}:{inst['tradingsymbol']}"] = inst["instrument_token"]
        return _INSTRUMENT_CACHE[key]

    # ------------------------------------------------------------------ BrokerPlugin

    async def place_buy(self, signal: TradeSignal) -> Position:
        ltp = await self.get_ltp(signal.symbol, signal.exchange)
        amount = signal.amount or self._trading.default_amount
        qty = int(amount // ltp)
        if qty < 1:
            raise ValueError(f"Insufficient amount {amount} to buy {signal.symbol} at {ltp:.2f}")

        order_id = await asyncio.to_thread(
            self._kite.place_order,
            tradingsymbol=signal.symbol,
            exchange=signal.exchange,
            transaction_type=KiteConnect.TRANSACTION_TYPE_BUY,
            quantity=qty,
            order_type=KiteConnect.ORDER_TYPE_MARKET,
            product=self._trading.product,
            variety=KiteConnect.VARIETY_REGULAR,
        )
        logger.info("BUY order placed: %s qty=%d order_id=%s", signal.symbol, qty, order_id)

        fill_price = await self._wait_for_fill(order_id)
        return Position(
            symbol=signal.symbol,
            exchange=signal.exchange,
            qty=qty,
            fill_price=fill_price,
            order_id=order_id,
            opened_at=datetime.now(timezone.utc),
        )

    async def place_sell(self, position: Position) -> float:
        order_id = await asyncio.to_thread(
            self._kite.place_order,
            tradingsymbol=position.symbol,
            exchange=position.exchange,
            transaction_type=KiteConnect.TRANSACTION_TYPE_SELL,
            quantity=position.qty,
            order_type=KiteConnect.ORDER_TYPE_MARKET,
            product=self._trading.product,
            variety=KiteConnect.VARIETY_REGULAR,
        )
        logger.info("SELL order placed: %s qty=%d order_id=%s", position.symbol, position.qty, order_id)
        fill_price = await self._wait_for_fill(order_id)
        return fill_price

    async def get_ltp(self, symbol: str, exchange: str) -> float:
        key = f"{exchange}:{symbol}"
        data = await asyncio.to_thread(self._kite.ltp, [key])
        return data[key]["last_price"]

    async def get_ohlc(self, symbol: str, exchange: str, days: int = 20) -> list[dict]:
        token = await self._get_instrument_token(symbol, exchange)
        to_date = datetime.now(timezone.utc).date()
        from_date = to_date - timedelta(days=days + 10)  # buffer for weekends
        candles = await asyncio.to_thread(
            self._kite.historical_data,
            token,
            from_date,
            to_date,
            "day",
        )
        return [
            {"date": c["date"], "open": c["open"], "high": c["high"],
             "low": c["low"], "close": c["close"], "volume": c["volume"]}
            for c in candles
        ]

    async def get_open_positions(self) -> list[Position]:
        data = await asyncio.to_thread(self._kite.positions)
        positions = []
        for p in data.get("net", []):
            if p["quantity"] > 0:
                positions.append(Position(
                    symbol=p["tradingsymbol"],
                    exchange=p["exchange"],
                    qty=p["quantity"],
                    fill_price=p["average_price"],
                    order_id="",  # unknown for pre-existing positions
                    opened_at=datetime.now(timezone.utc),
                ))
        return positions

    async def _wait_for_fill(self, order_id: str, retries: int = 10, delay: float = 1.0) -> float:
        for _ in range(retries):
            orders = await asyncio.to_thread(self._kite.orders)
            for o in orders:
                if o["order_id"] == order_id and o["status"] == "COMPLETE":
                    return float(o["average_price"])
            await asyncio.sleep(delay)
        raise TimeoutError(f"Order {order_id} did not fill within {retries * delay}s")
```

- [ ] **Step 2: Commit**

```bash
git add trader/brokers/kite.py
git commit -m "feat: add KiteBroker with manual/totp auth and asyncio wrappers"
```

---

## Task 16: Event Bus Dispatcher

**Files:**
- Create: `trader/core/dispatcher.py`
- Create: `tests/core/test_dispatcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/core/test_dispatcher.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from trader.core.dispatcher import Dispatcher
from trader.core.events import TradeSignal


@pytest.mark.asyncio
async def test_dispatcher_routes_signal_to_handler():
    queue: asyncio.Queue[TradeSignal] = asyncio.Queue()
    handler = AsyncMock()

    dispatcher = Dispatcher(queue=queue, handler=handler)

    sig = TradeSignal(symbol="RELIANCE", exchange="NSE")
    await queue.put(sig)

    # Run dispatcher for one iteration then cancel
    task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    handler.assert_called_once_with(sig)


@pytest.mark.asyncio
async def test_dispatcher_skips_on_handler_exception():
    queue: asyncio.Queue[TradeSignal] = asyncio.Queue()
    handler = AsyncMock(side_effect=[Exception("boom"), None])

    dispatcher = Dispatcher(queue=queue, handler=handler)

    sig1 = TradeSignal(symbol="INFY", exchange="NSE")
    sig2 = TradeSignal(symbol="TCS", exchange="NSE")
    await queue.put(sig1)
    await queue.put(sig2)

    task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert handler.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_dispatcher.py -v
```

Expected: `ImportError: No module named 'trader.core.dispatcher'`

- [ ] **Step 3: Implement dispatcher.py**

```python
# trader/core/dispatcher.py
from __future__ import annotations
import asyncio
import logging
from typing import Awaitable, Callable

from trader.core.events import TradeSignal

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(
        self,
        queue: asyncio.Queue[TradeSignal],
        handler: Callable[[TradeSignal], Awaitable[None]],
    ) -> None:
        self._queue = queue
        self._handler = handler

    async def run(self) -> None:
        while True:
            signal = await self._queue.get()
            try:
                await self._handler(signal)
            except Exception as exc:
                logger.exception("Handler failed for signal %s: %s", signal.symbol, exc)
            finally:
                self._queue.task_done()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_dispatcher.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add trader/core/dispatcher.py tests/core/test_dispatcher.py
git commit -m "feat: add Dispatcher event bus with error isolation"
```

---

## Task 17: Engine (Orchestrator + Startup Recovery + Trade Log)

**Files:**
- Create: `trader/core/engine.py`

The engine:
1. On startup, calls `broker.get_open_positions()` and reattaches TSL monitors for any existing positions (startup recovery).
2. Handles incoming `TradeSignal`: deduplication → buy → spawn TSL monitor + fundamentals fetch.
3. On TSL exit: writes `TradeRecord` to JSONL trade log.

- [ ] **Step 1: Implement engine.py**

```python
# trader/core/engine.py
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from trader.brokers.base import BrokerPlugin
from trader.config import Config
from trader.core.events import Position, TradeRecord, TradeSignal
from trader.fundamentals.fetcher import fetch_fundamentals
from trader.tsl.factory import build_tsl_strategy
from trader.tsl.monitor import TSLMonitor

logger = logging.getLogger(__name__)


class Engine:
    def __init__(self, config: Config, broker: BrokerPlugin) -> None:
        self._config = config
        self._broker = broker
        self._open_positions: dict[str, Position] = {}  # symbol → Position
        self._log_path = Path(config.log.trade_log)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    async def recover_open_positions(self) -> None:
        """Re-attach TSL monitors for positions open at startup."""
        positions = await self._broker.get_open_positions()
        for pos in positions:
            logger.info("Recovering open position: %s", pos.symbol)
            self._open_positions[pos.symbol] = pos
            asyncio.create_task(self._start_tsl_monitor(pos))

    async def handle_signal(self, signal: TradeSignal) -> None:
        cfg = self._config

        if cfg.trading.dedup_open_positions and signal.symbol in self._open_positions:
            logger.info("Signal skipped — position already open for %s", signal.symbol)
            return

        logger.info("Processing signal: %s", signal.symbol)
        try:
            position = await self._broker.place_buy(signal)
        except Exception as exc:
            logger.exception("Buy failed for %s: %s", signal.symbol, exc)
            return

        self._open_positions[signal.symbol] = position

        asyncio.create_task(self._start_tsl_monitor(position, signal=signal))

        if cfg.fundamentals.enabled:
            asyncio.create_task(self._log_fundamentals(position))

    async def _start_tsl_monitor(
        self, position: Position, signal: TradeSignal | None = None
    ) -> None:
        cfg = self._config.tsl
        strategy = build_tsl_strategy(
            cfg=cfg,
            signal_tsl_mode=signal.tsl_mode if signal else None,
            signal_tsl_pct=signal.tsl_pct if signal else None,
            signal_tsl_k=signal.tsl_k if signal else None,
            signal_tsl_tiers=signal.tsl_tiers if signal else None,
        )
        await strategy.on_position_opened(position, self._broker)

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=self._broker,
            poll_interval=cfg.poll_interval_sec,
            on_closed=self._on_position_closed,
        )
        await monitor.run()

    async def _on_position_closed(self, position: Position, sell_price: float) -> None:
        self._open_positions.pop(position.symbol, None)
        pnl = (sell_price - position.fill_price) * position.qty
        record = TradeRecord(
            symbol=position.symbol,
            exchange=position.exchange,
            qty=position.qty,
            buy_price=position.fill_price,
            sell_price=sell_price,
            pnl=pnl,
            tsl_mode=self._config.tsl.default_mode,
            opened_at=position.opened_at,
            closed_at=datetime.now(timezone.utc),
            fundamentals={},
        )
        self._write_trade_record(record)
        logger.info(
            "Position closed: %s | buy=%.2f sell=%.2f pnl=%.2f",
            position.symbol, position.fill_price, sell_price, pnl,
        )

    async def _log_fundamentals(self, position: Position) -> None:
        fundamentals = await fetch_fundamentals(
            position.symbol, provider=self._config.fundamentals.provider
        )
        logger.info("Fundamentals for %s: %s", position.symbol, fundamentals)
        # Append fundamentals update to log
        entry = {"type": "fundamentals", "symbol": position.symbol, "data": fundamentals,
                 "ts": datetime.now(timezone.utc).isoformat()}
        with self._log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_trade_record(self, record: TradeRecord) -> None:
        def default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            raise TypeError(f"Object of type {type(o)} is not JSON serializable")

        with self._log_path.open("a") as f:
            f.write(json.dumps({"type": "trade", **asdict(record)}, default=default) + "\n")
```

- [ ] **Step 2: Commit**

```bash
git add trader/core/engine.py
git commit -m "feat: add Engine orchestrator with startup recovery and trade log"
```

---

## Task 18: Entrypoint + Systemd Service

**Files:**
- Create: `trader/__main__.py`
- Create: `systemd/trader.service`

- [ ] **Step 1: Implement __main__.py**

```python
# trader/__main__.py
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from trader.brokers.kite import KiteBroker
from trader.config import load_config
from trader.core.dispatcher import Dispatcher
from trader.core.engine import Engine
from trader.sources.telegram import TelegramRelaySource

load_dotenv()


async def main() -> None:
    config = load_config(os.environ.get("CONFIG_PATH", "config.yaml"))

    logging.basicConfig(
        level=getattr(logging, config.log.level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    broker = KiteBroker(trading_cfg=config.trading, auth_cfg=config.auth)
    await broker.authenticate()

    engine = Engine(config=config, broker=broker)
    await engine.recover_open_positions()

    queue: asyncio.Queue = asyncio.Queue()
    dispatcher = Dispatcher(queue=queue, handler=engine.handle_signal)

    source = TelegramRelaySource(
        cfg=config.sources.telegram,
        default_amount=config.trading.default_amount,
    )

    await asyncio.gather(
        source.start(queue),
        dispatcher.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Create systemd service file**

```ini
# systemd/trader.service
[Unit]
Description=Claude AI Trading Automation
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/claude-ai-trading-automation
EnvironmentFile=/opt/claude-ai-trading-automation/.env
ExecStart=/opt/claude-ai-trading-automation/.venv/bin/python -m trader
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add trader/__main__.py systemd/trader.service
git commit -m "feat: add entrypoint and systemd service unit"
```

---

## Task 19: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md with commands and architecture**

Replace the contents of `CLAUDE.md` with:

```markdown
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the service
python -m trader

# Run with a specific config
CONFIG_PATH=config.staging.yaml python -m trader

# Run all tests
pytest

# Run a single test file
pytest tests/tsl/test_fixed.py -v

# Run tests matching a name
pytest -k "test_update_stop" -v
```

## Architecture

Plugin-based async service. An `asyncio.Queue` acts as the internal event bus — sources push `TradeSignal` events, the `Dispatcher` routes them to the `Engine`, which calls the `BrokerPlugin` to place orders and spawns a `TSLMonitor` per position.

**Key extension points:**
- `trader/sources/base.py` — add new signal sources (Discord, WhatsApp) by implementing `SourcePlugin`
- `trader/brokers/base.py` — add new brokers (Upstox, Groww) by implementing `BrokerPlugin`
- `trader/tsl/base.py` — add new TSL strategies by implementing `TSLStrategy`; register in `trader/tsl/factory.py`

**TSL strategies:** `fixed` | `stepped` | `atr` | `chandelier` | `psar` — selected via `config.yaml` `tsl.default_mode`, overridable per signal via `TSL:<mode>` in the message text.

**Auth:** Kite session cached in `.kite_session`. Run daily before market open in `manual` mode, or set `auth.mode: totp` with `KITE_TOTP_SECRET` env var.

**Trade log:** Appended JSONL at `logs/trades.jsonl`. Each line is either `{"type": "trade", ...}` (position closed) or `{"type": "fundamentals", ...}` (post-buy fundamentals snapshot).

## Spec and Plan

- Design spec: `docs/superpowers/specs/2026-06-15-trading-automation-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-15-trading-automation.md`
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with commands and architecture"
```

---

## Full Test Run

- [ ] **Run full test suite**

```bash
pytest -v
```

Expected: all tests pass. (Kite broker excluded from automated tests — requires live credentials.)

---

## Self-Review Checklist

Spec sections vs plan coverage:

| Spec section | Covered by task |
|---|---|
| Architecture / plugin-based async | Task 16 (Dispatcher), Task 17 (Engine) |
| TradeSignal dataclass | Task 2 |
| Deduplication | Task 17 (Engine.handle_signal) |
| Market buy + qty calc | Task 15 (KiteBroker.place_buy) |
| Post-fill fork (TSL + fundamentals) | Task 17 (Engine._start_tsl_monitor + _log_fundamentals) |
| TSL Strategy ABC | Task 6 |
| FixedPctTSL | Task 7 |
| SteppedTSL | Task 8 |
| ATRTSLStrategy | Task 9 |
| ChandelierTSL | Task 10 |
| ParabolicSARTSL | Task 11 |
| TSL factory with per-signal overrides | Task 12 |
| TSL monitor with retry | Task 13 |
| Fundamentals fetcher (non-blocking) | Task 14 |
| Kite auth (manual + totp switch) | Task 15 |
| Config schema (YAML + env vars) | Task 3 |
| Error handling (parse fail, order reject, LTP retry, auth token) | Task 13 (LTP retry), Task 16 (dispatcher isolation), Task 17 (buy exception handling) |
| Startup recovery | Task 17 (Engine.recover_open_positions) |
| Trade log (JSONL) | Task 17 (Engine._write_trade_record) |
| Deployment (local + systemd) | Task 18 |
