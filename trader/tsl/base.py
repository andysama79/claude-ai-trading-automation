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
