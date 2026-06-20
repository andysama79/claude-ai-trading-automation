# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Claude AI-powered trading automation. Listens for earnings signals from Telegram, places market buys via Zerodha Kite Connect, and manages positions with pluggable trailing stop loss (TSL) strategies.

## Commands

```bash
# Install dependencies (first time)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run tests
python -m pytest

# Run the service (requires .env or system env vars)
python -m trader --config config.yaml

# Auth: generate .kite_session (manual mode)
python -m trader.auth  # TODO: not yet implemented — run auth.py when added
```

## Architecture

Plugin-based async service with `asyncio.Queue` event bus:

```
[Telegram Bot] → [TelegramRelaySource] → [asyncio.Queue] → [Engine]
                                                              ├── [KiteBroker] place_buy
                                                              ├── [TSLMonitor] polls LTP, fires sell
                                                              └── [FundamentalsFetcher] async, logging only
```

### Key modules

| Module | Role |
|--------|------|
| `trader/__main__.py` | Entrypoint, wires all plugins |
| `trader/core/engine.py` | Orchestrator, dedup, trade log |
| `trader/core/dispatcher.py` | asyncio.Queue event bus |
| `trader/sources/telegram.py` | Telegram relay source plugin |
| `trader/brokers/kite.py` | Zerodha Kite broker plugin |
| `trader/tsl/` | TSL strategies + factory + monitor |
| `trader/fundamentals/fetcher.py` | yfinance wrapper (post-buy, non-blocking) |
| `trader/config.py` | Typed config loader |

### TSL Strategies

| Mode | Class | Key param |
|------|-------|-----------|
| `fixed` | `FixedPctTSL` | `pct` |
| `stepped` | `SteppedTSL` | `tiers` |
| `atr` | `ATRTSLStrategy` | `k` (default 2.0) |
| `chandelier` | `ChandelierTSL` | `k` (default 3.0) |
| `psar` | `ParabolicSARTSL` | af_start/step/max |

### Config

Copy `config.example.yaml` → `config.yaml`. Copy `.env.example` → `.env` and fill in secrets.

Required env vars: `KITE_API_KEY`, `KITE_API_SECRET`, `TG_API_ID`, `TG_API_HASH`, `TG_BOT_TOKEN`.
Optional: `KITE_TOTP_SECRET` (for `auth.mode: totp`).

## Trade log

Append-only JSONL at `logs/trades.jsonl`. Each entry: symbol, exchange, qty, buy/sell price, P&L, TSL mode, timestamps, fundamentals snapshot.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
