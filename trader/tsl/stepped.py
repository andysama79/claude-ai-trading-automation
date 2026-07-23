import math
from trader.tsl.base import TSLStrategy


class SteppedTSL(TSLStrategy):
    """TSL % tightens as unrealised gain grows.

    tiers: list of (gain_threshold_pct, tsl_pct) sorted ascending by threshold.
    Last tier's threshold is math.inf (catches all remaining gains).

    Example tiers:
        [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)]

    Gain = (peak / fill_price - 1) * 100
    Active TSL % = tsl_pct from first tier where gain < threshold
    Stop = peak * (1 - active_pct / 100)
    """

    def __init__(self, fill_price: float, tiers: list[tuple[float, float]]):
        self.fill_price = fill_price
        self.tiers = sorted(tiers, key=lambda t: t[0])

    def _active_pct(self, peak: float) -> float:
        """Return TSL % for the current peak price based on unrealised gain."""
        gain = (peak / self.fill_price - 1) * 100
        for threshold, pct in self.tiers:
            if gain < threshold:
                return pct
        return self.tiers[-1][1]

    def initial_stop(self, fill_price: float) -> float:
        """Compute stop price at position entry."""
        return fill_price * (1 - self._active_pct(fill_price) / 100)

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        """Called on each LTP poll tick. Must never return a value lower than current_stop."""
        new_stop = peak * (1 - self._active_pct(peak) / 100)
        return max(new_stop, current_stop)
