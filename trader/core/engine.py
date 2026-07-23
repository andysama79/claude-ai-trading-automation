from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from trader.brokers.base import BrokerPlugin
from trader.config import Config
from trader.core.dispatcher import Dispatcher
from trader.core.events import Position, TradeRecord, TradeSignal
from trader.fundamentals.fetcher import fetch_fundamentals
from trader.tsl.factory import build_tsl_strategy
from trader.tsl.monitor import TSLMonitor

logger = logging.getLogger(__name__)


class Engine:
    """Main orchestrator. Wires broker, dispatcher, TSL, fundamentals, trade log."""

    def __init__(self, broker: BrokerPlugin, config: Config) -> None:
        self.broker = broker
        self.config = config
        self.dispatcher = Dispatcher()
        self._open_positions: dict[str, Position] = {}
        self._log_path = Path(config.log.trade_log)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        self.dispatcher.register(self._handle_signal)

    async def start(self) -> None:
        """Connect broker, recover open positions, start dispatcher."""
        await self.broker.connect()
        await self.recover_open_positions()
        await self.dispatcher.run()

    async def emit(self, signal: TradeSignal) -> None:
        """Push a signal onto the event bus (called by SourcePlugins)."""
        await self.dispatcher.emit(signal)

    async def _handle_signal(self, signal: TradeSignal) -> None:
        """Route TradeSignal → buy → TSL monitor + fundamentals."""
        if signal.symbol in self._open_positions:
            logger.info("Dedup: already have open position for %s", signal.symbol)
            return

        logger.info("Processing signal: %s %s", signal.symbol, signal.exchange)
        position = await self.broker.place_buy(signal)
        self._open_positions[signal.symbol] = position
        logger.info("Position opened: %s qty=%d fill=%.2f", position.symbol, position.qty, position.fill_price)

        strategy = build_tsl_strategy(signal, {
            "tsl_mode": self.config.tsl.default_mode,
            "default_pct": self.config.tsl.default_pct,
            "tiers": self.config.tsl.tiers,
            "k": self.config.tsl.k,
        })

        asyncio.create_task(fetch_fundamentals(
            signal.symbol, signal.exchange,
            provider=self.config.fundamentals.provider,
        ))

        monitor = TSLMonitor(
            position=position,
            strategy=strategy,
            broker=self.broker,
            poll_interval=self.config.tsl.poll_interval_sec,
            on_exit=self._on_position_exit,
        )
        asyncio.create_task(monitor.run())

    async def _on_position_exit(self, position: Position, sell_price: float) -> None:
        """Called by TSLMonitor when position closes. Logs trade."""
        self._open_positions.pop(position.symbol, None)
        pnl = (sell_price - position.fill_price) * position.qty

        record = TradeRecord(
            symbol=position.symbol,
            exchange=position.exchange,
            qty=position.qty,
            buy_price=position.fill_price,
            sell_price=sell_price,
            pnl=pnl,
            tsl_mode=self.config.tsl.default_mode,
            opened_at=position.opened_at,
            closed_at=datetime.now(),
            fundamentals={},
        )
        self._append_trade_log(record)
        logger.info("Trade closed: %s P&L=%.2f", position.symbol, pnl)

    def _append_trade_log(self, record: TradeRecord) -> None:
        """Append TradeRecord to JSONL log file."""
        entry = {
            "symbol": record.symbol,
            "exchange": record.exchange,
            "qty": record.qty,
            "buy_price": record.buy_price,
            "sell_price": record.sell_price,
            "pnl": record.pnl,
            "tsl_mode": record.tsl_mode,
            "opened_at": record.opened_at.isoformat(),
            "closed_at": record.closed_at.isoformat(),
            "fundamentals": record.fundamentals,
        }
        with self._log_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    async def recover_open_positions(self) -> None:
        """On startup, fetch open positions from broker and attach TSL monitors."""
        positions = await self.broker.get_open_positions()
        for position in positions:
            if position.symbol not in self._open_positions:
                self._open_positions[position.symbol] = position
                signal = TradeSignal(symbol=position.symbol, exchange=position.exchange)
                strategy = build_tsl_strategy(signal, {
                    "tsl_mode": self.config.tsl.default_mode,
                    "default_pct": self.config.tsl.default_pct,
                    "tiers": self.config.tsl.tiers,
                    "k": self.config.tsl.k,
                })
                monitor = TSLMonitor(
                    position=position,
                    strategy=strategy,
                    broker=self.broker,
                    poll_interval=self.config.tsl.poll_interval_sec,
                    on_exit=self._on_position_exit,
                )
                asyncio.create_task(monitor.run())
                logger.info("Recovered position: %s qty=%d", position.symbol, position.qty)
        logger.info("Recovery complete: %d open positions", len(self._open_positions))
