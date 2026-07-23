from __future__ import annotations
from typing import TYPE_CHECKING

from trader.tsl.base import TSLStrategy

if TYPE_CHECKING:
    from trader.brokers.base import BrokerPlugin
    from trader.core.events import Position


class ParabolicSARTSL(TSLStrategy):
    """Parabolic SAR trailing stop (long position only).

    State is updated each poll tick via update_stop.
    """

    def __init__(
        self, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.20
    ):
        """Initialize Parabolic SAR TSL strategy.

        Args:
            af_start: Initial acceleration factor
            af_step: Step to increase af by when new high is made
            af_max: Maximum acceleration factor
        """
        self.af_start = af_start
        self.af_step = af_step
        self.af_max = af_max
        self._sar: float | None = None
        self._ep: float | None = None
        self._af: float = af_start

    def initial_stop(self, fill_price: float) -> float:
        """Bootstrap SAR: start stop 5% below fill_price if no candle data."""
        if self._sar is None:
            self._sar = fill_price * 0.95
            self._ep = fill_price
            self._af = self.af_start
        return self._sar

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        """Advance SAR state and return new stop. Monotonically increasing.

        Args:
            current_stop: The current stop price
            ltp: Last traded price
            peak: Highest price seen so far

        Returns:
            New stop price (never decreases)
        """
        if self._sar is None:
            self._sar = ltp * 0.95
            self._ep = ltp
            self._af = self.af_start

        new_sar = self._sar + self._af * (self._ep - self._sar)
        if ltp > self._ep:
            self._ep = ltp
            self._af = min(self._af + self.af_step, self.af_max)
        self._sar = new_sar
        return max(self._sar, current_stop)

    async def on_position_opened(self, position: Position, broker: BrokerPlugin) -> None:
        """Optional: seed SAR from historical lows if broker available."""
        try:
            candles = await broker.get_ohlc(position.symbol, position.exchange, days=10)
            if candles:
                self._sar = min(c["low"] for c in candles[:5])
                self._ep = max(c["high"] for c in candles)
                self._af = self.af_start
        except Exception:
            pass  # Fall back to fill_price bootstrap in initial_stop
