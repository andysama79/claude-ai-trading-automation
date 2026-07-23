from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trader.config import Config, LogConfig
from trader.core.engine import Engine
from trader.core.events import Position, TradeSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_position(symbol: str = "INFY", exchange: str = "NSE") -> Position:
    return Position(
        symbol=symbol,
        exchange=exchange,
        qty=10,
        fill_price=100.0,
        order_id="ORD123",
        opened_at=datetime(2026, 1, 1, 10, 0, 0),
    )


def _make_config(tmp_path: Path) -> Config:
    cfg = Config()
    cfg.log = LogConfig(trade_log=str(tmp_path / "trades.jsonl"))
    return cfg


def _make_broker(position: Position | None = None) -> MagicMock:
    broker = MagicMock()
    broker.connect = AsyncMock()
    broker.place_buy = AsyncMock(return_value=position or _make_position())
    broker.place_sell = AsyncMock(return_value=110.0)
    broker.get_ltp = AsyncMock(return_value=105.0)
    broker.get_open_positions = AsyncMock(return_value=[])
    return broker


# ---------------------------------------------------------------------------
# Test 1: Deduplication — signal for already-open symbol is ignored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_ignores_signal_for_open_position(tmp_path):
    """Second signal for an open symbol must NOT call place_buy."""
    position = _make_position("INFY")
    broker = _make_broker(position)
    config = _make_config(tmp_path)

    with patch("trader.core.engine.build_tsl_strategy") as mock_build, \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls, \
         patch("trader.core.engine.fetch_fundamentals", new_callable=AsyncMock):

        mock_strategy = MagicMock()
        mock_build.return_value = mock_strategy

        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        signal = TradeSignal(symbol="INFY", exchange="NSE")

        # First signal — processes normally
        await engine._handle_signal(signal)
        await asyncio.sleep(0)  # yield for create_task

        assert broker.place_buy.call_count == 1
        assert "INFY" in engine._open_positions

        # Second signal for same symbol — must be deduped
        await engine._handle_signal(signal)
        await asyncio.sleep(0)

        # place_buy must still be 1 (not called again)
        assert broker.place_buy.call_count == 1


# ---------------------------------------------------------------------------
# Test 2: Signal flow — place_buy called → position stored
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signal_flow_opens_position(tmp_path):
    """Signal triggers place_buy and stores position in _open_positions."""
    position = _make_position("RELIANCE")
    broker = _make_broker(position)
    config = _make_config(tmp_path)

    with patch("trader.core.engine.build_tsl_strategy") as mock_build, \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls, \
         patch("trader.core.engine.fetch_fundamentals", new_callable=AsyncMock):

        mock_build.return_value = MagicMock()

        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        signal = TradeSignal(symbol="RELIANCE", exchange="NSE")

        await engine._handle_signal(signal)
        await asyncio.sleep(0)

        broker.place_buy.assert_awaited_once_with(signal)
        assert "RELIANCE" in engine._open_positions
        assert engine._open_positions["RELIANCE"] is position


# ---------------------------------------------------------------------------
# Test 3: Trade log — _on_position_exit appends JSONL entry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_position_exit_appends_trade_log(tmp_path):
    """_on_position_exit writes a JSONL record to the log file."""
    broker = _make_broker()
    config = _make_config(tmp_path)
    engine = Engine(broker=broker, config=config)

    position = _make_position("TCS")
    engine._open_positions["TCS"] = position
    sell_price = 120.0

    await engine._on_position_exit(position, sell_price)

    log_file = tmp_path / "trades.jsonl"
    assert log_file.exists(), "Trade log file was not created"

    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1, f"Expected 1 line, got {len(lines)}"

    entry = json.loads(lines[0])
    assert entry["symbol"] == "TCS"
    assert entry["exchange"] == "NSE"
    assert entry["qty"] == 10
    assert entry["buy_price"] == pytest.approx(100.0)
    assert entry["sell_price"] == pytest.approx(120.0)
    expected_pnl = (120.0 - 100.0) * 10  # 200.0
    assert entry["pnl"] == pytest.approx(expected_pnl)
    assert entry["tsl_mode"] == config.tsl.default_mode
    assert "opened_at" in entry
    assert "closed_at" in entry
    assert isinstance(entry["fundamentals"], dict)

    # Position should be removed from open positions
    assert "TCS" not in engine._open_positions


# ---------------------------------------------------------------------------
# Test 4: Recovery — recover_open_positions re-attaches TSL monitors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recover_open_positions_attaches_monitors(tmp_path):
    """recover_open_positions loads broker positions and starts TSL monitors for each."""
    position = _make_position("WIPRO")
    broker = _make_broker()
    broker.get_open_positions = AsyncMock(return_value=[position])
    config = _make_config(tmp_path)

    with patch("trader.core.engine.build_tsl_strategy") as mock_build, \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls:

        mock_build.return_value = MagicMock()

        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        await engine.recover_open_positions()
        await asyncio.sleep(0)  # yield for create_task

        # Position should be tracked
        assert "WIPRO" in engine._open_positions
        assert engine._open_positions["WIPRO"] is position

        # TSLMonitor should have been constructed and run scheduled
        mock_monitor_cls.assert_called_once()
        call_kwargs = mock_monitor_cls.call_args.kwargs
        assert call_kwargs["position"] is position
        assert call_kwargs["broker"] is broker


@pytest.mark.asyncio
async def test_recover_open_positions_skips_already_tracked(tmp_path):
    """recover_open_positions does not double-add positions already in _open_positions."""
    position = _make_position("HDFC")
    broker = _make_broker()
    broker.get_open_positions = AsyncMock(return_value=[position])
    config = _make_config(tmp_path)

    with patch("trader.core.engine.build_tsl_strategy"), \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls:

        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        # Pre-populate so recovery should skip it
        engine._open_positions["HDFC"] = position

        await engine.recover_open_positions()

        # Monitor should NOT have been created (position was already tracked)
        mock_monitor_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: Fundamentals persistence — result flows from fetch into TradeRecord
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fundamentals_result_persisted_onto_trade_record(tmp_path):
    """_handle_signal's fundamentals fetch result must reach the TradeRecord
    written by _on_position_exit, not be discarded as {} unconditionally."""
    position = _make_position("INFY")
    broker = _make_broker(position)
    config = _make_config(tmp_path)
    fake_fundamentals = {"pe_ratio": 25.0, "eps": 4.2}

    with patch("trader.core.engine.build_tsl_strategy") as mock_build, \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls, \
         patch("trader.core.engine.fetch_fundamentals", new_callable=AsyncMock) as mock_fetch:

        mock_fetch.return_value = fake_fundamentals
        mock_build.return_value = MagicMock()
        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        signal = TradeSignal(symbol="INFY", exchange="NSE")

        await engine._handle_signal(signal)
        await asyncio.sleep(0)  # let the fundamentals task run to completion

        assert engine._fundamentals_cache["INFY"] == fake_fundamentals

        await engine._on_position_exit(position, sell_price=120.0)

        log_file = tmp_path / "trades.jsonl"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert entry["fundamentals"] == fake_fundamentals
        # Cache entry consumed once written to the trade record.
        assert "INFY" not in engine._fundamentals_cache


@pytest.mark.asyncio
async def test_fundamentals_disabled_skips_fetch_entirely(tmp_path):
    """fundamentals.enabled = False must skip fetch_fundamentals, not fetch-then-discard."""
    position = _make_position("INFY")
    broker = _make_broker(position)
    config = _make_config(tmp_path)
    config.fundamentals.enabled = False

    with patch("trader.core.engine.build_tsl_strategy") as mock_build, \
         patch("trader.core.engine.TSLMonitor") as mock_monitor_cls, \
         patch("trader.core.engine.fetch_fundamentals", new_callable=AsyncMock) as mock_fetch:

        mock_build.return_value = MagicMock()
        mock_monitor = MagicMock()
        mock_monitor.run = AsyncMock()
        mock_monitor_cls.return_value = mock_monitor

        engine = Engine(broker=broker, config=config)
        signal = TradeSignal(symbol="INFY", exchange="NSE")

        await engine._handle_signal(signal)
        await asyncio.sleep(0)

        mock_fetch.assert_not_awaited()
        assert "INFY" not in engine._fundamentals_cache


@pytest.mark.asyncio
async def test_trade_record_fundamentals_defaults_empty_when_not_fetched_yet(tmp_path):
    """If the position exits before the fundamentals task resolves (or it was
    never scheduled, e.g. in a synthetic/recovered position), the trade
    record still gets written with fundamentals={} rather than erroring."""
    broker = _make_broker()
    config = _make_config(tmp_path)
    engine = Engine(broker=broker, config=config)

    position = _make_position("TCS")
    engine._open_positions["TCS"] = position

    await engine._on_position_exit(position, sell_price=120.0)

    log_file = tmp_path / "trades.jsonl"
    entry = json.loads(log_file.read_text().strip().splitlines()[0])
    assert entry["fundamentals"] == {}
