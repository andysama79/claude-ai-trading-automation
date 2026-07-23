import asyncio
import pytest
from trader.core.dispatcher import Dispatcher
from trader.core.events import TradeSignal


def make_signal(symbol="RELIANCE"):
    return TradeSignal(symbol=symbol, exchange="NSE")


@pytest.mark.asyncio
async def test_emit_and_handler_called():
    """Test 1: emit() puts signal on queue; run() calls registered handler with signal."""
    received = []
    dispatcher = Dispatcher()

    async def handler(signal):
        received.append(signal.symbol)

    dispatcher.register(handler)

    task = asyncio.create_task(dispatcher.run())
    await dispatcher.emit(make_signal("RELIANCE"))
    await asyncio.sleep(0)  # yield to let dispatcher process
    await dispatcher._queue.join()  # wait for queue to drain
    task.cancel()

    assert received == ["RELIANCE"]


@pytest.mark.asyncio
async def test_multiple_handlers():
    """Test 2: Multiple handlers all called for one signal."""
    results = {"handler1": [], "handler2": [], "handler3": []}
    dispatcher = Dispatcher()

    async def handler1(signal):
        results["handler1"].append(signal.symbol)

    async def handler2(signal):
        results["handler2"].append(signal.symbol)

    async def handler3(signal):
        results["handler3"].append(signal.symbol)

    dispatcher.register(handler1)
    dispatcher.register(handler2)
    dispatcher.register(handler3)

    task = asyncio.create_task(dispatcher.run())
    await dispatcher.emit(make_signal("INFY"))
    await asyncio.sleep(0)
    await dispatcher._queue.join()
    task.cancel()

    assert results["handler1"] == ["INFY"]
    assert results["handler2"] == ["INFY"]
    assert results["handler3"] == ["INFY"]


@pytest.mark.asyncio
async def test_handler_exception_does_not_crash_loop():
    """Test 3: Handler exception doesn't crash the run loop — subsequent signals still processed."""
    results = []
    dispatcher = Dispatcher()

    async def bad_handler(signal):
        raise ValueError(f"Error processing {signal.symbol}")

    async def good_handler(signal):
        results.append(signal.symbol)

    dispatcher.register(bad_handler)
    dispatcher.register(good_handler)

    task = asyncio.create_task(dispatcher.run())
    await dispatcher.emit(make_signal("RELIANCE"))
    await asyncio.sleep(0)
    await dispatcher._queue.join()

    # Second signal should still be processed despite first handler error
    await dispatcher.emit(make_signal("INFY"))
    await asyncio.sleep(0)
    await dispatcher._queue.join()

    task.cancel()

    # good_handler should have been called for both signals
    assert results == ["RELIANCE", "INFY"]


@pytest.mark.asyncio
async def test_fifo_order():
    """Test 4: run() processes signals in order (FIFO)."""
    received = []
    dispatcher = Dispatcher()

    async def handler(signal):
        received.append(signal.symbol)

    dispatcher.register(handler)

    task = asyncio.create_task(dispatcher.run())

    # Emit signals in order
    await dispatcher.emit(make_signal("RELIANCE"))
    await dispatcher.emit(make_signal("INFY"))
    await dispatcher.emit(make_signal("TCS"))

    await asyncio.sleep(0)
    await dispatcher._queue.join()
    task.cancel()

    assert received == ["RELIANCE", "INFY", "TCS"]


@pytest.mark.asyncio
async def test_emit_is_async():
    """Test 5: emit() is async and puts to queue."""
    dispatcher = Dispatcher()
    signal = make_signal("RELIANCE")

    # This should be awaitable and put the signal on the queue
    await dispatcher.emit(signal)

    # Verify it's in the queue
    assert dispatcher._queue.qsize() == 1
    retrieved = await dispatcher._queue.get()
    assert retrieved.symbol == "RELIANCE"
