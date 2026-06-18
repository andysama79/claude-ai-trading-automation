from __future__ import annotations
import asyncio
import logging
import os
import re
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

from trader.core.events import TradeSignal
from trader.sources.base import SourcePlugin

if TYPE_CHECKING:
    from trader.config import TelegramConfig

logger = logging.getLogger(__name__)

# Words to skip when extracting the stock symbol from a message.
_SKIP_WORDS = frozenset({"BUY", "SELL", "NSE", "BSE", "THE", "AND", "FOR", "EPS", "YOY", "QOQ"})

# Inline override patterns embedded in the signal message.
_AMOUNT_RE = re.compile(r"AMOUNT:(\d+(?:\.\d+)?)", re.IGNORECASE)
_TSL_MODE_RE = re.compile(r"TSL:(fixed|stepped|atr|chandelier|psar)", re.IGNORECASE)
_TSL_PCT_RE = re.compile(r"TSL_PCT:(\d+(?:\.\d+)?)", re.IGNORECASE)
_TSL_K_RE = re.compile(r"TSL_K:(\d+(?:\.\d+)?)", re.IGNORECASE)


def parse_signal(
    text: str,
    symbol_regex: str,
    default_amount: float,
) -> TradeSignal | None:
    """Extract a TradeSignal from raw message text. Returns None if no symbol found."""
    # Extract inline overrides first (so their tokens don't confuse symbol detection).
    amount_match = _AMOUNT_RE.search(text)
    amount = float(amount_match.group(1)) if amount_match else default_amount

    tsl_mode_match = _TSL_MODE_RE.search(text)
    tsl_mode = tsl_mode_match.group(1).lower() if tsl_mode_match else None

    tsl_pct_match = _TSL_PCT_RE.search(text)
    tsl_pct = float(tsl_pct_match.group(1)) if tsl_pct_match else None

    tsl_k_match = _TSL_K_RE.search(text)
    tsl_k = float(tsl_k_match.group(1)) if tsl_k_match else None

    # Find stock symbol: first match of symbol_regex not in skip list.
    for match in re.finditer(symbol_regex, text):
        candidate = match.group(1)
        if candidate not in _SKIP_WORDS:
            return TradeSignal(
                symbol=candidate,
                exchange="NSE",
                amount=amount,
                tsl_mode=tsl_mode,
                tsl_pct=tsl_pct,
                tsl_k=tsl_k,
            )

    return None


class TelegramRelaySource(SourcePlugin):
    def __init__(self, cfg: TelegramConfig, default_amount: float) -> None:
        self._token = os.environ[cfg.relay_bot_token_env]
        self._watch_chats: set[int] = set(cfg.watch_chats)
        self._symbol_regex = cfg.symbol_regex
        self._default_amount = default_amount

    async def start(self, queue: asyncio.Queue) -> None:
        app = Application.builder().token(self._token).build()

        async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
            if not update.message or not update.message.text:
                return
            chat_id = update.effective_chat.id
            if self._watch_chats and chat_id not in self._watch_chats:
                return
            text = update.message.text
            signal = parse_signal(text, self._symbol_regex, self._default_amount)
            if signal:
                logger.info("Signal parsed: %s from chat %d", signal.symbol, chat_id)
                await queue.put(signal)
            else:
                logger.debug("No signal in message from chat %d: %r", chat_id, text[:80])

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))

        async with app:
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            try:
                await asyncio.get_event_loop().create_future()  # run forever
            finally:
                await app.updater.stop()
                await app.stop()
