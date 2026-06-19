from __future__ import annotations
import asyncio
import logging
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

from kiteconnect import KiteConnect
from trader.brokers.base import BrokerPlugin
from trader.core.events import Position, TradeSignal

logger = logging.getLogger(__name__)

_SESSION_FILE = Path(".kite_session")


class KiteBroker(BrokerPlugin):
    """Zerodha Kite Connect broker plugin.

    Auth modes:
      manual — expects .kite_session file with access_token on line 1
      totp   — uses pyotp to generate TOTP, completes login flow
    """

    def __init__(self, api_key: str, api_secret: str, auth_mode: str = "manual",
                 totp_secret: str | None = None, default_amount: float = 10000.0,
                 product: str = "CNC"):
        self.api_key = api_key
        self.api_secret = api_secret
        self.auth_mode = auth_mode
        self.totp_secret = totp_secret
        self.default_amount = default_amount
        self.product = product
        self._kite: KiteConnect | None = None

    async def connect(self) -> None:
        """Initialize KiteConnect and authenticate. Call once at startup."""
        self._kite = KiteConnect(api_key=self.api_key)
        if self.auth_mode == "totp":
            await asyncio.to_thread(self._auth_totp)
        else:
            self._load_session()

    def _load_session(self) -> None:
        if not _SESSION_FILE.exists():
            raise FileNotFoundError(f"No session file at {_SESSION_FILE}. Run auth.py first.")
        token = _SESSION_FILE.read_text().strip().splitlines()[0]
        self._kite.set_access_token(token)
        logger.info("Kite session loaded from %s", _SESSION_FILE)

    def _auth_totp(self) -> None:
        """TOTP-based auth. Runs in thread (synchronous Kite API calls)."""
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        # Kite Connect TOTP login flow
        session = self._kite.generate_session_with_totp(
            user_id=os.environ.get("KITE_USER_ID", ""),
            password=os.environ.get("KITE_PASSWORD", ""),
            totp=totp.now(),
        )
        self._kite.set_access_token(session["access_token"])
        _SESSION_FILE.write_text(session["access_token"])
        logger.info("Kite TOTP auth complete, session cached")

    async def place_buy(self, signal: TradeSignal) -> Position:
        amount = signal.amount or self.default_amount
        ltp = await self.get_ltp(signal.symbol, signal.exchange)
        qty = math.floor(amount / ltp)
        if qty < 1:
            raise ValueError(f"Calculated qty < 1 for {signal.symbol} (amount={amount}, ltp={ltp})")

        order_id = await asyncio.to_thread(
            self._kite.place_order,
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=signal.exchange,
            tradingsymbol=signal.symbol,
            transaction_type=KiteConnect.TRANSACTION_TYPE_BUY,
            quantity=qty,
            product=self.product,
            order_type=KiteConnect.ORDER_TYPE_MARKET,
        )
        logger.info("Buy order placed: %s qty=%d order_id=%s", signal.symbol, qty, order_id)

        fill_price = await self._await_fill(order_id)
        return Position(
            symbol=signal.symbol,
            exchange=signal.exchange,
            qty=qty,
            fill_price=fill_price,
            order_id=order_id,
            opened_at=datetime.now(),
        )

    async def place_sell(self, position: Position) -> float:
        order_id = await asyncio.to_thread(
            self._kite.place_order,
            variety=KiteConnect.VARIETY_REGULAR,
            exchange=position.exchange,
            tradingsymbol=position.symbol,
            transaction_type=KiteConnect.TRANSACTION_TYPE_SELL,
            quantity=position.qty,
            product=self.product,
            order_type=KiteConnect.ORDER_TYPE_MARKET,
        )
        logger.info("Sell order placed: %s qty=%d order_id=%s", position.symbol, position.qty, order_id)
        fill_price = await self._await_fill(order_id)
        return fill_price

    async def get_ltp(self, symbol: str, exchange: str) -> float:
        quote_key = f"{exchange}:{symbol}"
        data = await asyncio.to_thread(self._kite.ltp, [quote_key])
        return data[quote_key]["last_price"]

    async def get_ohlc(self, symbol: str, exchange: str, days: int = 20) -> list[dict]:
        """Fetch daily candles via Kite historical data API."""
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days + 10)  # buffer for weekends
        data = await asyncio.to_thread(
            self._kite.historical_data,
            instrument_token=await self._get_instrument_token(symbol, exchange),
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d"),
            interval="day",
        )
        # Kite returns: [{date, open, high, low, close, volume}, ...]
        return [
            {"date": c["date"], "open": c["open"], "high": c["high"],
             "low": c["low"], "close": c["close"], "volume": c["volume"]}
            for c in data[-days:]
        ]

    async def get_open_positions(self) -> list[Position]:
        """Fetch open net positions from Kite (for startup recovery)."""
        data = await asyncio.to_thread(self._kite.positions)
        positions = []
        for p in data.get("net", []):
            if p["quantity"] > 0:
                positions.append(Position(
                    symbol=p["tradingsymbol"],
                    exchange=p["exchange"],
                    qty=p["quantity"],
                    fill_price=p["average_price"],
                    order_id=f"RECOVERED_{p['tradingsymbol']}",
                    opened_at=datetime.now(),
                ))
        return positions

    async def _await_fill(self, order_id: str) -> float:
        """Poll order status until filled. Returns fill price."""
        for _ in range(30):
            await asyncio.sleep(1)
            orders = await asyncio.to_thread(self._kite.orders)
            for o in orders:
                if o["order_id"] == order_id and o["status"] == "COMPLETE":
                    return o["average_price"]
        raise TimeoutError(f"Order {order_id} did not fill within 30s")

    async def _get_instrument_token(self, symbol: str, exchange: str) -> int:
        """Look up instrument token for historical data API."""
        instruments = await asyncio.to_thread(self._kite.instruments, exchange)
        for i in instruments:
            if i["tradingsymbol"] == symbol:
                return i["instrument_token"]
        raise ValueError(f"Instrument not found: {exchange}:{symbol}")
