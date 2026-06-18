import pytest
from trader.tsl.chandelier import ChandelierTSL


class TestChandelierTSLInitialStop:
    """Test ChandelierTSL.initial_stop."""

    def test_initial_stop_before_on_position_opened_raises_error(self):
        """initial_stop should raise RuntimeError if _stop_anchor not set."""
        strategy = ChandelierTSL(k=3.0, period=14)
        with pytest.raises(RuntimeError, match="Chandelier not initialized"):
            strategy.initial_stop(fill_price=100.0)

    def test_initial_stop_after_position_opened(self):
        """After on_position_opened, initial_stop returns _stop_anchor."""
        strategy = ChandelierTSL(k=3.0, period=14)
        # Simulate on_position_opened setting _stop_anchor
        strategy._stop_anchor = 50.0
        stop = strategy.initial_stop(fill_price=100.0)
        assert stop == 50.0


class TestChandelierTSLUpdateStop:
    """Test ChandelierTSL.update_stop."""

    def test_update_stop_monotonic_ratchet_up(self):
        """Stop should ratchet up to _stop_anchor if current_stop < anchor."""
        strategy = ChandelierTSL(k=3.0, period=14)
        strategy._stop_anchor = 50.0

        # Current stop is below anchor
        current_stop = 40.0
        new_stop = strategy.update_stop(current_stop=current_stop, ltp=100.0, peak=110.0)
        # Should ratchet up to anchor
        assert new_stop == 50.0

    def test_update_stop_stays_at_anchor_when_equal(self):
        """Stop should stay at anchor when current_stop == anchor."""
        strategy = ChandelierTSL(k=3.0, period=14)
        strategy._stop_anchor = 50.0

        current_stop = 50.0
        new_stop = strategy.update_stop(current_stop=current_stop, ltp=100.0, peak=110.0)
        assert new_stop == 50.0

    def test_update_stop_stays_above_anchor(self):
        """Stop should stay above anchor when current_stop > anchor."""
        strategy = ChandelierTSL(k=3.0, period=14)
        strategy._stop_anchor = 50.0

        current_stop = 60.0
        new_stop = strategy.update_stop(current_stop=current_stop, ltp=100.0, peak=110.0)
        # Should keep current_stop since it's higher
        assert new_stop == 60.0

    def test_update_stop_before_on_position_opened_raises_error(self):
        """update_stop should raise RuntimeError if _stop_anchor not set."""
        strategy = ChandelierTSL(k=3.0, period=14)
        with pytest.raises(RuntimeError, match="Chandelier not initialized"):
            strategy.update_stop(current_stop=90.0, ltp=95.0, peak=100.0)


class TestChandelierTSLOnPositionOpened:
    """Test ChandelierTSL.on_position_opened."""

    @pytest.mark.asyncio
    async def test_on_position_opened_fetches_ohlc_and_sets_anchor(self):
        """on_position_opened should fetch OHLC via broker and set _stop_anchor."""
        # Mock broker
        class MockBroker:
            async def get_ohlc(self, symbol, exchange, days=20):
                # Return 21 candles: high=110, low=90, close=100
                return [{"open": 95, "high": 110, "low": 90, "close": 100}] * 21

        # Mock position
        class MockPosition:
            symbol = "TEST"
            exchange = "NSE"

        strategy = ChandelierTSL(k=3.0, period=14)
        position = MockPosition()
        broker = MockBroker()

        # Before on_position_opened, _stop_anchor should be None
        assert strategy._stop_anchor is None

        # Call on_position_opened
        await strategy.on_position_opened(position, broker)

        # After, _stop_anchor should be set
        assert strategy._stop_anchor is not None
        # For these candles:
        # TR = max(110-90, abs(110-100), abs(90-100)) = max(20, 10, 10) = 20
        # All 21 candles have same OHLC, so last 14 TRs all = 20
        # ATR = 20
        # highest_high = 110
        # _stop_anchor = 110 - 3.0 * 20 = 110 - 60 = 50
        assert strategy._stop_anchor == 50.0

    @pytest.mark.asyncio
    async def test_initial_stop_works_after_on_position_opened(self):
        """After on_position_opened, initial_stop should work."""
        class MockBroker:
            async def get_ohlc(self, symbol, exchange, days=20):
                return [{"open": 95, "high": 110, "low": 90, "close": 100}] * 21

        class MockPosition:
            symbol = "TEST"
            exchange = "NSE"

        strategy = ChandelierTSL(k=3.0, period=14)
        position = MockPosition()
        broker = MockBroker()

        await strategy.on_position_opened(position, broker)

        # Now initial_stop should work
        stop = strategy.initial_stop(fill_price=100.0)
        assert stop == 50.0

    @pytest.mark.asyncio
    async def test_on_position_opened_with_different_k_values(self):
        """Test _stop_anchor calculation with different k values."""
        class MockBroker:
            async def get_ohlc(self, symbol, exchange, days=20):
                return [{"open": 95, "high": 110, "low": 90, "close": 100}] * 21

        class MockPosition:
            symbol = "TEST"
            exchange = "NSE"

        # Test with k=2.0
        strategy = ChandelierTSL(k=2.0, period=14)
        position = MockPosition()
        broker = MockBroker()

        await strategy.on_position_opened(position, broker)
        # _stop_anchor = 110 - 2.0 * 20 = 70
        assert strategy._stop_anchor == 70.0

    @pytest.mark.asyncio
    async def test_on_position_opened_calls_broker_with_correct_days(self):
        """on_position_opened should call broker.get_ohlc with days=period+6."""
        # Mock broker that tracks its calls
        class MockBroker:
            def __init__(self):
                self.call_args = None

            async def get_ohlc(self, symbol, exchange, days=20):
                self.call_args = (symbol, exchange, days)
                return [{"open": 95, "high": 110, "low": 90, "close": 100}] * 21

        class MockPosition:
            symbol = "BTC"
            exchange = "BINANCE"

        strategy = ChandelierTSL(k=3.0, period=14)
        position = MockPosition()
        broker = MockBroker()

        await strategy.on_position_opened(position, broker)

        # Check broker was called with correct arguments
        assert broker.call_args == ("BTC", "BINANCE", 20)  # period + 6 = 14 + 6 = 20
