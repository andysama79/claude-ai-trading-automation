from __future__ import annotations

import asyncio
import logging
from trader.brokers.base import BrokerPlugin
from trader.core.events import Position
from trader.tsl.base import TSLStrategy

logger = logging.getLogger(__name__)

_RETRY_DELAYS = (1, 2, 4)  # exponential backoff seconds for LTP poll failures


class TSLMonitor:
    """Async task: polls LTP, advances TSL stop, fires sell on trigger.

    Lifecycle:
      1. on_position_opened: let strategy fetch OHLC if needed
      2. initial_stop: compute initial stop from fill_price
      3. poll loop: get_ltp → update_stop → should_exit → sell
    """

    def __init__(
        self,
        position: Position,
        strategy: TSLStrategy,
        broker: BrokerPlugin,
        poll_interval: float = 10.0,
        on_exit: callable | None = None,
    ):
        self.position = position
        self.strategy = strategy
        self.broker = broker
        self.poll_interval = poll_interval
        self.on_exit = on_exit  # async callback(position, sell_price) — notifies engine

    async def run(self) -> None:
        """Run the TSL monitor loop until position exits or task is cancelled."""
        await self.strategy.on_position_opened(self.position, self.broker)
        stop = self.strategy.initial_stop(self.position.fill_price)
        logger.info(
            "TSL monitor started: %s stop=%.2f fill=%.2f",
            self.position.symbol, stop, self.position.fill_price,
        )

        while True:
            ltp = await self._poll_ltp()
            if ltp is None:
                logger.error(
                    "TSL monitor: LTP poll failed 3x for %s — halting",
                    self.position.symbol,
                )
                break

            if ltp > self.position.peak_price:
                self.position.peak_price = ltp

            stop = self.strategy.update_stop(stop, ltp, self.position.peak_price)

            if self.strategy.should_exit(ltp, stop):
                logger.info(
                    "TSL triggered for %s: ltp=%.2f stop=%.2f",
                    self.position.symbol, ltp, stop,
                )
                sell_price = await self.broker.place_sell(self.position)
                if self.on_exit:
                    await self.on_exit(self.position, sell_price)
                break

            await asyncio.sleep(self.poll_interval)

    async def _poll_ltp(self) -> float | None:
        """Poll LTP with 3 retries and exponential backoff. Returns None on all failures."""
        for delay in (0, *_RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self.broker.get_ltp(
                    self.position.symbol, self.position.exchange
                )
            except Exception as e:
                logger.warning("LTP poll failed for %s: %s", self.position.symbol, e)
        return None
