import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from datetime import datetime

from trader.core.events import Position
from trader.tsl.monitor import TSLMonitor


def make_position():
    return Position(
        symbol="RELIANCE",
        exchange="NSE",
        qty=10,
        fill_price=100.0,
        order_id="ORD001",
        opened_at=datetime(2026, 1, 1),
    )


def make_strategy(*, initial_stop=95.0, update_stop=95.0, should_exit=True):
    strategy = MagicMock()
    strategy.on_position_opened = AsyncMock(return_value=None)
    strategy.initial_stop = MagicMock(return_value=initial_stop)
    strategy.update_stop = MagicMock(return_value=update_stop)
    strategy.should_exit = MagicMock(return_value=should_exit)
    return strategy


def make_broker(*, ltp=90.0, sell_price=88.0):
    broker = MagicMock()
    broker.get_ltp = AsyncMock(return_value=ltp)
    broker.place_sell = AsyncMock(return_value=sell_price)
    return broker


class TestTSLMonitorExit:
    """Test 1: run() exits when strategy.should_exit returns True."""

    @pytest.mark.asyncio
    async def test_run_exits_when_should_exit_true(self):
        position = make_position()
        strategy = make_strategy(initial_stop=95.0, update_stop=95.0, should_exit=True)
        broker = make_broker(ltp=90.0, sell_price=88.0)
        on_exit = AsyncMock()

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
            on_exit=on_exit,
        )
        await monitor.run()

        broker.place_sell.assert_called_once_with(position)
        on_exit.assert_called_once_with(position, 88.0)


class TestTSLMonitorPeakPrice:
    """Test 2: run() updates position.peak_price when ltp exceeds current peak."""

    @pytest.mark.asyncio
    async def test_peak_price_updated_when_ltp_exceeds(self):
        position = make_position()
        # peak starts at fill_price=100.0; ltp=120 should raise peak to 120
        # but first tick should_exit=False so we get a second tick to exit
        should_exit_results = [False, True]
        strategy = MagicMock()
        strategy.on_position_opened = AsyncMock(return_value=None)
        strategy.initial_stop = MagicMock(return_value=95.0)
        strategy.update_stop = MagicMock(return_value=95.0)
        strategy.should_exit = MagicMock(side_effect=should_exit_results)

        broker = MagicMock()
        broker.get_ltp = AsyncMock(return_value=120.0)
        broker.place_sell = AsyncMock(return_value=118.0)

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )
        await monitor.run()

        assert position.peak_price == 120.0

    @pytest.mark.asyncio
    async def test_peak_price_not_reduced_when_ltp_below(self):
        position = make_position()
        # ltp=80 < fill_price=100 → peak stays at 100
        strategy = make_strategy(initial_stop=85.0, update_stop=85.0, should_exit=True)
        broker = make_broker(ltp=80.0, sell_price=79.0)

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )
        await monitor.run()

        assert position.peak_price == 100.0  # unchanged


class TestTSLMonitorUpdateStop:
    """Test 3: run() calls strategy.update_stop each tick."""

    @pytest.mark.asyncio
    async def test_update_stop_called_each_tick(self):
        position = make_position()
        # Two ticks: first should_exit=False, second should_exit=True
        strategy = MagicMock()
        strategy.on_position_opened = AsyncMock(return_value=None)
        strategy.initial_stop = MagicMock(return_value=95.0)
        strategy.update_stop = MagicMock(return_value=95.0)
        strategy.should_exit = MagicMock(side_effect=[False, True])

        broker = MagicMock()
        broker.get_ltp = AsyncMock(return_value=90.0)
        broker.place_sell = AsyncMock(return_value=88.0)

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )
        await monitor.run()

        assert strategy.update_stop.call_count == 2


class TestPollLtp:
    """Test 4: _poll_ltp retries on exception and returns None after 3 failures."""

    @pytest.mark.asyncio
    async def test_poll_ltp_returns_none_after_3_failures(self):
        position = make_position()
        strategy = make_strategy()
        broker = MagicMock()
        broker.get_ltp = AsyncMock(side_effect=Exception("network error"))

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._poll_ltp()

        assert result is None

    @pytest.mark.asyncio
    async def test_poll_ltp_retries_then_succeeds(self):
        position = make_position()
        strategy = make_strategy()
        broker = MagicMock()
        # Fail twice, succeed on third attempt
        broker.get_ltp = AsyncMock(
            side_effect=[Exception("err"), Exception("err"), 105.0]
        )

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await monitor._poll_ltp()

        assert result == 105.0
        assert broker.get_ltp.call_count == 3


class TestTSLMonitorHaltOnLtpFailure:
    """Test 5: run() halts (breaks) when _poll_ltp returns None."""

    @pytest.mark.asyncio
    async def test_run_halts_when_poll_ltp_returns_none(self):
        position = make_position()
        strategy = make_strategy()
        broker = make_broker()

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )

        # Patch _poll_ltp to return None immediately
        monitor._poll_ltp = AsyncMock(return_value=None)
        await monitor.run()

        # place_sell should NOT have been called
        broker.place_sell.assert_not_called()


class TestTSLMonitorOnPositionOpened:
    """Test 6: run() calls strategy.on_position_opened before first poll."""

    @pytest.mark.asyncio
    async def test_on_position_opened_called_before_first_poll(self):
        position = make_position()
        strategy = make_strategy(should_exit=True)
        broker = make_broker(ltp=90.0, sell_price=88.0)

        call_order = []
        strategy.on_position_opened = AsyncMock(
            side_effect=lambda *a: call_order.append("on_position_opened")
        )
        broker.get_ltp = AsyncMock(
            side_effect=lambda *a: call_order.append("get_ltp") or 90.0
        )

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=broker,
            poll_interval=0,
        )
        await monitor.run()

        assert call_order[0] == "on_position_opened"
        assert "get_ltp" in call_order
        assert call_order.index("on_position_opened") < call_order.index("get_ltp")
