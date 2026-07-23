import math
from trader.tsl.base import TSLStrategy


def compute_atr(candles: list[dict], period: int = 14) -> float:
    """Compute ATR from list of candles: [{open, high, low, close}, ...].
    Candles must be sorted oldest first. Returns ATR for the last `period` candles.
    """
    if len(candles) < period + 1:
        raise ValueError(f"Need at least {period + 1} candles, got {len(candles)}")

    true_ranges = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1]["close"]
        h = candles[i]["high"]
        l = candles[i]["low"]
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        true_ranges.append(tr)

    # Use last `period` TRs
    return sum(true_ranges[-period:]) / period


class ATRTSLStrategy(TSLStrategy):
    """Stop = peak - (k × ATR14). ATR fetched once on position open."""

    def __init__(self, k: float = 2.0):
        self.k = k
        self._atr: float | None = None

    def initial_stop(self, fill_price: float) -> float:
        if self._atr is None:
            raise RuntimeError("ATR not set — call on_position_opened first")
        return fill_price - self.k * self._atr

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        if self._atr is None:
            raise RuntimeError("ATR not set — call on_position_opened first")
        new_stop = peak - self.k * self._atr
        return max(new_stop, current_stop)

    async def on_position_opened(self, position, broker) -> None:
        candles = await broker.get_ohlc(position.symbol, position.exchange, days=20)
        self._atr = compute_atr(candles)
