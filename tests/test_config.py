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
