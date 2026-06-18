from trader.tsl.base import TSLStrategy
from trader.tsl.atr import compute_atr


class ChandelierTSL(TSLStrategy):
    """Stop = highest_high(period) - (k × ATR(period)).
    Highest high and ATR fetched once on position open, then cached.
    """

    def __init__(self, k: float = 3.0, period: int = 14):
        self.k = k
        self.period = period
        self._stop_anchor: float | None = None  # highest_high - k * atr, computed once

    def initial_stop(self, fill_price: float) -> float:
        if self._stop_anchor is None:
            raise RuntimeError("Chandelier not initialized — call on_position_opened first")
        return self._stop_anchor

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        if self._stop_anchor is None:
            raise RuntimeError("Chandelier not initialized — call on_position_opened first")
        # Chandelier stop is fixed from historical data; only ratchet up via max
        return max(self._stop_anchor, current_stop)

    async def on_position_opened(self, position, broker) -> None:
        candles = await broker.get_ohlc(position.symbol, position.exchange, days=self.period + 6)
        atr = compute_atr(candles, self.period)
        highest_high = max(c["high"] for c in candles[-self.period:])
        self._stop_anchor = highest_high - self.k * atr
