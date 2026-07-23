from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod


class SourcePlugin(ABC):
    @abstractmethod
    async def start(self, queue: asyncio.Queue) -> None:
        """Push TradeSignal events onto queue indefinitely. Run until cancelled."""
        ...
