from __future__ import annotations
from abc import ABC, abstractmethod

from trader.core.events import Position, TradeSignal


class BrokerPlugin(ABC):

    @abstractmethod
    async def place_buy(self, signal: TradeSignal) -> Position:
        """Place a market buy. Returns filled Position."""
        ...

    @abstractmethod
    async def place_sell(self, position: Position) -> float:
        """Place a market sell. Returns fill price."""
        ...

    @abstractmethod
    async def get_ltp(self, symbol: str, exchange: str) -> float:
        """Return last traded price."""
        ...

    @abstractmethod
    async def get_ohlc(self, symbol: str, exchange: str, days: int = 20) -> list[dict]:
        """Return list of daily candles: [{date, open, high, low, close, volume}, ...]."""
        ...

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Return open positions from broker (used for startup recovery)."""
        ...
