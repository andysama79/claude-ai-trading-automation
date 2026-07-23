from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from trader.core.events import TradeSignal

logger = logging.getLogger(__name__)

Handler = Callable[[TradeSignal], Coroutine[Any, Any, None]]


class Dispatcher:
    """asyncio.Queue-based event bus. Routes TradeSignals to registered async handlers."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[TradeSignal] = asyncio.Queue()
        self._handlers: list[Handler] = []

    def register(self, handler: Handler) -> None:
        """Register an async handler for TradeSignal events."""
        self._handlers.append(handler)

    async def emit(self, signal: TradeSignal) -> None:
        """Push a signal onto the queue."""
        await self._queue.put(signal)

    async def run(self) -> None:
        """Consume signals from the queue and dispatch to all registered handlers.

        Runs indefinitely. Each handler is awaited sequentially.
        Handler exceptions are caught and logged — never crash the loop.
        """
        logger.info("Dispatcher started")
        while True:
            signal = await self._queue.get()
            logger.debug("Dispatching signal: %s", signal.symbol)
            for handler in self._handlers:
                try:
                    await handler(signal)
                except Exception as e:
                    logger.error("Handler error for %s: %s", signal.symbol, e)
            self._queue.task_done()
