from trader.tsl.base import TSLStrategy


class FixedPctTSL(TSLStrategy):
    """Stop = peak × (1 − pct/100). Monotonically increases as peak rises."""

    def __init__(self, pct: float):
        """
        Initialize FixedPctTSL.

        Args:
            pct: Stop loss percentage (e.g., 5.0 means 5%)
        """
        self.pct = pct

    def initial_stop(self, fill_price: float) -> float:
        """Compute stop price at position entry."""
        return fill_price * (1 - self.pct / 100)

    def update_stop(self, current_stop: float, ltp: float, peak: float) -> float:
        """Called on each LTP poll tick. Must never return a value lower than current_stop."""
        new_stop = peak * (1 - self.pct / 100)
        return max(new_stop, current_stop)  # monotonically increasing
