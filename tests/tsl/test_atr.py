import pytest
from trader.tsl.atr import compute_atr, ATRTSLStrategy


class TestComputeATR:
    """Test compute_atr function."""

    def test_compute_atr_correct_calculation(self):
        """Test ATR calculation with known candles."""
        # Construct 15 candles with predictable True Range values
        # Each candle has TR = 5.0
        candles = []
        for i in range(15):
            candles.append({
                "open": 100.0,
                "high": 102.5,
                "low": 97.5,
                "close": 100.0
            })

        atr = compute_atr(candles, period=14)
        # TR for each candle: max(102.5-97.5, abs(102.5-100), abs(97.5-100))
        #                   = max(5.0, 2.5, 2.5) = 5.0
        # We need 15 candles for 14 TRs, last 14 TRs average to 5.0
        assert atr == 5.0

    def test_compute_atr_with_varying_true_ranges(self):
        """Test ATR with varying TR values."""
        candles = [
            {"open": 100, "high": 100, "low": 100, "close": 100},  # TR = 0
            {"open": 100, "high": 110, "low": 90, "close": 105},   # TR = 20
            {"open": 105, "high": 115, "low": 95, "close": 110},   # TR = 20
        ]
        # Add 12 more candles with TR = 10 each to reach 14 candles for averaging
        for _ in range(12):
            candles.append({
                "open": 110,
                "high": 115,
                "low": 105,
                "close": 110
            })

        atr = compute_atr(candles, period=14)
        # TRs: 0, 20, 20, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10
        # Last 14 TRs: 20, 20, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10
        # Sum = 20 + 20 + 120 = 160, avg = 160/14 ≈ 11.428571...
        expected_atr = (20 + 20 + 10 * 12) / 14
        assert abs(atr - expected_atr) < 0.0001

    def test_compute_atr_raises_with_insufficient_candles(self):
        """Test that compute_atr raises ValueError with < 15 candles (period 14)."""
        candles = [{"open": 100, "high": 105, "low": 95, "close": 100}] * 14
        with pytest.raises(ValueError, match="Need at least 15 candles"):
            compute_atr(candles, period=14)


class TestATRTSLStrategyInitialStop:
    """Test ATRTSLStrategy.initial_stop."""

    def test_initial_stop_before_on_position_opened_raises_error(self):
        """initial_stop should raise RuntimeError if _atr not set."""
        strategy = ATRTSLStrategy(k=2.0)
        with pytest.raises(RuntimeError, match="ATR not set"):
            strategy.initial_stop(fill_price=100.0)

    def test_initial_stop_after_atr_set(self):
        """fill=100, k=2.0, atr=5.0 → stop=90.0"""
        strategy = ATRTSLStrategy(k=2.0)
        strategy._atr = 5.0
        stop = strategy.initial_stop(fill_price=100.0)
        assert stop == 90.0


class TestATRTSLStrategyUpdateStop:
    """Test ATRTSLStrategy.update_stop."""

    def test_update_stop_monotonic(self):
        """Stop should not decrease when peak unchanged."""
        strategy = ATRTSLStrategy(k=2.0)
        strategy._atr = 5.0

        # Initial stop
        current_stop = strategy.initial_stop(fill_price=100.0)  # 90.0

        # Peak stays at 100, LTP drops but stop shouldn't change
        new_stop = strategy.update_stop(current_stop=current_stop, ltp=95.0, peak=100.0)
        assert new_stop == 90.0

    def test_update_stop_increases_with_peak(self):
        """Stop should increase when peak rises."""
        strategy = ATRTSLStrategy(k=2.0)
        strategy._atr = 5.0

        current_stop = strategy.initial_stop(fill_price=100.0)  # 90.0

        # Peak rises to 110
        new_stop = strategy.update_stop(current_stop=current_stop, ltp=108.0, peak=110.0)
        # new_stop = 110 - 2*5 = 100, which is > 90.0
        assert new_stop == 100.0

    def test_update_stop_before_atr_set_raises_error(self):
        """update_stop should raise RuntimeError if _atr not set."""
        strategy = ATRTSLStrategy(k=2.0)
        with pytest.raises(RuntimeError, match="ATR not set"):
            strategy.update_stop(current_stop=90.0, ltp=95.0, peak=100.0)


class TestATRTSLStrategyOnPositionOpened:
    """Test ATRTSLStrategy.on_position_opened."""

    @pytest.mark.asyncio
    async def test_on_position_opened_fetches_ohlc_and_sets_atr(self):
        """on_position_opened should fetch OHLC via broker and set _atr."""
        # Mock broker
        class MockBroker:
            async def get_ohlc(self, symbol, exchange, days=20):
                # Return 21 candles with predictable TR
                return [{"open": 100, "high": 105, "low": 95, "close": 100}] * 21

        # Mock position
        class MockPosition:
            symbol = "TEST"
            exchange = "NSE"

        strategy = ATRTSLStrategy(k=2.0)
        position = MockPosition()
        broker = MockBroker()

        # Before on_position_opened, _atr should be None
        assert strategy._atr is None

        # Call on_position_opened
        await strategy.on_position_opened(position, broker)

        # After, _atr should be set
        assert strategy._atr is not None
        # For these candles, TR = max(high-low, abs(high-prev_close), abs(low-prev_close))
        # All 21 have same OHLC, so TR = max(10, 5, 5) = 10
        # Last 14 TRs average to 10
        assert strategy._atr == 10.0

    @pytest.mark.asyncio
    async def test_initial_stop_works_after_on_position_opened(self):
        """After on_position_opened, initial_stop should work."""
        class MockBroker:
            async def get_ohlc(self, symbol, exchange, days=20):
                return [{"open": 100, "high": 105, "low": 95, "close": 100}] * 21

        class MockPosition:
            symbol = "TEST"
            exchange = "NSE"

        strategy = ATRTSLStrategy(k=2.0)
        position = MockPosition()
        broker = MockBroker()

        await strategy.on_position_opened(position, broker)

        # Now initial_stop should work
        stop = strategy.initial_stop(fill_price=100.0)
        assert stop == 80.0  # 100 - 2*10
