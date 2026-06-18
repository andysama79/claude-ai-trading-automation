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
