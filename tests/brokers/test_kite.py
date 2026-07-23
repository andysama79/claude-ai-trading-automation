"""Tests for KiteBroker: session loading and instrument-token caching."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from trader.brokers import kite as kite_module
from trader.brokers.kite import KiteBroker


@pytest.fixture
def broker():
    return KiteBroker(api_key="key", api_secret="secret", auth_mode="manual")


@pytest.fixture(autouse=True)
def _isolate_session_file(tmp_path, monkeypatch):
    """Point _SESSION_FILE at a temp path so tests never touch the real .kite_session."""
    session_path = tmp_path / ".kite_session"
    monkeypatch.setattr(kite_module, "_SESSION_FILE", session_path)
    yield session_path


class TestLoadSession:
    def test_missing_session_file_raises_with_auth_hint(self, broker):
        broker._kite = object()  # not touched before the raise
        with pytest.raises(FileNotFoundError, match="python -m trader.auth"):
            broker._load_session()

    def test_empty_session_file_raises_with_auth_hint(self, broker, _isolate_session_file):
        _isolate_session_file.write_text("")
        broker._kite = object()
        with pytest.raises(ValueError, match="python -m trader.auth"):
            broker._load_session()

    def test_whitespace_only_session_file_raises(self, broker, _isolate_session_file):
        _isolate_session_file.write_text("   \n\n")
        broker._kite = object()
        with pytest.raises(ValueError, match="python -m trader.auth"):
            broker._load_session()

    def test_valid_session_file_sets_access_token(self, broker, _isolate_session_file):
        _isolate_session_file.write_text("abc123token\n")
        calls = []
        broker._kite = type("FakeKite", (), {"set_access_token": lambda self, t: calls.append(t)})()
        broker._load_session()
        assert calls == ["abc123token"]


class TestInstrumentTokenCache:
    @pytest.mark.asyncio
    async def test_fetches_instruments_once_then_uses_cache(self, broker):
        instruments_call = AsyncMock(return_value=[
            {"tradingsymbol": "RELIANCE", "instrument_token": 111},
            {"tradingsymbol": "SBIN", "instrument_token": 222},
        ])
        broker._kite = type("FakeKite", (), {"instruments": lambda self, ex: None})()

        with patch("trader.brokers.kite.asyncio.to_thread", instruments_call):
            token1 = await broker._get_instrument_token("RELIANCE", "NSE")
            token2 = await broker._get_instrument_token("SBIN", "NSE")

        assert token1 == 111
        assert token2 == 222
        # Only one underlying fetch for the whole NSE exchange, reused for both lookups.
        assert instruments_call.call_count == 1

    @pytest.mark.asyncio
    async def test_refetches_after_ttl_expires(self, broker):
        instruments_call = AsyncMock(return_value=[
            {"tradingsymbol": "RELIANCE", "instrument_token": 111},
        ])
        broker._kite = type("FakeKite", (), {"instruments": lambda self, ex: None})()

        with patch("trader.brokers.kite.asyncio.to_thread", instruments_call):
            await broker._get_instrument_token("RELIANCE", "NSE")
            # Force the cache to look stale.
            broker._instrument_cache_at["NSE"] = datetime.now() - timedelta(hours=25)
            await broker._get_instrument_token("RELIANCE", "NSE")

        assert instruments_call.call_count == 2

    @pytest.mark.asyncio
    async def test_unknown_symbol_raises(self, broker):
        instruments_call = AsyncMock(return_value=[
            {"tradingsymbol": "RELIANCE", "instrument_token": 111},
        ])
        broker._kite = type("FakeKite", (), {"instruments": lambda self, ex: None})()

        with patch("trader.brokers.kite.asyncio.to_thread", instruments_call):
            with pytest.raises(ValueError, match="Instrument not found"):
                await broker._get_instrument_token("UNKNOWN", "NSE")
