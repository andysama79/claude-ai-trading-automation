"""Entry point: python -m trader [--config path/to/config.yaml]"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys

from trader.brokers.kite import KiteBroker
from trader.config import load_config
from trader.core.engine import Engine
from trader.sources.telegram import TelegramRelaySource


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


async def main(config_path: str) -> None:
    config = load_config(config_path)
    _setup_logging(config.log.level)

    logger = logging.getLogger(__name__)
    logger.info("Starting trader — config: %s", config_path)

    broker = KiteBroker(
        api_key=os.environ["KITE_API_KEY"],
        api_secret=os.environ["KITE_API_SECRET"],
        auth_mode=config.auth.mode,
        totp_secret=os.environ.get(config.auth.totp_secret_env),
        default_amount=config.trading.default_amount,
        product=config.trading.product,
    )

    engine = Engine(broker=broker, config=config)

    # TelegramRelaySource takes (cfg: TelegramConfig, default_amount: float)
    # and reads env vars internally via cfg.*_env field names.
    telegram_source = TelegramRelaySource(
        cfg=config.sources.telegram,
        default_amount=config.trading.default_amount,
    )

    async def forward_to_engine(queue: asyncio.Queue) -> None:
        while True:
            signal = await queue.get()
            await engine.emit(signal)
            queue.task_done()

    signal_queue: asyncio.Queue = asyncio.Queue()

    await asyncio.gather(
        telegram_source.start(signal_queue),
        forward_to_engine(signal_queue),
        engine.start(),
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Claude AI Trading Automation")
    p.add_argument("--config", default="config.yaml", help="Path to config YAML")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    try:
        asyncio.run(main(args.config))
    except KeyboardInterrupt:
        sys.exit(0)
