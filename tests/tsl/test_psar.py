import pytest
from unittest.mock import AsyncMock, MagicMock
from trader.tsl.psar import ParabolicSARTSL


class TestParabolicSARTSLInitialStop:
    """Test initial_stop computes stop price at position entry."""

    def test_initial_stop_without_prior_data(self):
        """fill=100 → stop=95.0 (5% below)"""
        tsl = ParabolicSARTSL()
        stop = tsl.initial_stop(fill_price=100.0)
        assert stop == 95.0

    def test_initial_stop_idempotent(self):
        """Calling initial_stop twice returns the same value."""
        tsl = ParabolicSARTSL()
        stop1 = tsl.initial_stop(fill_price=100.0)
        stop2 = tsl.initial_stop(fill_price=100.0)
        assert stop1 == stop2 == 95.0

    def test_initial_stop_initializes_state(self):
        """initial_stop should initialize _sar, _ep, and _af."""
        tsl = ParabolicSARTSL(af_start=0.02)
        tsl.initial_stop(fill_price=100.0)
        assert tsl._sar == 95.0
        assert tsl._ep == 100.0
        assert tsl._af == 0.02


class TestParabolicSARTSLUpdateStop:
    """Test update_stop advances SAR state and maintains monotonicity."""

    def test_update_stop_advances_sar_state(self):
        """After initial_stop(100), update_stop(95, 102, 102) should return > 95."""
        tsl = ParabolicSARTSL()
        current_stop = tsl.initial_stop(fill_price=100.0)  # 95.0
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=102.0, peak=102.0)
        assert new_stop > 95.0

    def test_update_stop_never_decreases(self):
        """Stop never decreases (monotonic)."""
        tsl = ParabolicSARTSL()
        current_stop = tsl.initial_stop(fill_price=100.0)  # 95.0

        # First update with higher ltp
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=102.0, peak=102.0)
        first_stop = new_stop

        # Second update with lower ltp (should not decrease)
        new_stop = tsl.update_stop(current_stop=first_stop, ltp=98.0, peak=102.0)
        assert new_stop >= first_stop

    def test_update_stop_without_prior_initialization(self):
        """update_stop bootstraps SAR if not already initialized."""
        tsl = ParabolicSARTSL()
        # Call update_stop directly without initial_stop
        new_stop = tsl.update_stop(current_stop=95.0, ltp=100.0, peak=100.0)
        assert tsl._sar is not None
        assert tsl._ep is not None

    def test_af_accelerates_when_ltp_exceeds_ep(self):
        """When ltp > ep, af should increase by af_step."""
        tsl = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
        tsl.initial_stop(fill_price=100.0)
        initial_af = tsl._af  # 0.02

        # Update with ltp > ep (102 > 100)
        tsl.update_stop(current_stop=95.0, ltp=102.0, peak=102.0)

        # af should increase
        assert tsl._af > initial_af
        assert tsl._af == initial_af + tsl.af_step

    def test_af_respects_max_limit(self):
        """af should not exceed af_max."""
        tsl = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
        tsl.initial_stop(fill_price=100.0)

        # Force multiple updates with increasing peaks
        current_stop = 95.0
        for i in range(15):  # Multiple increases
            peak = 100.0 + (i * 2)
            current_stop = tsl.update_stop(current_stop=current_stop, ltp=peak, peak=peak)

        assert tsl._af <= tsl.af_max

    def test_af_unchanged_when_ltp_does_not_exceed_ep(self):
        """When ltp <= ep, af should remain unchanged."""
        tsl = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)
        tsl.initial_stop(fill_price=100.0)

        # First update to establish a peak
        tsl.update_stop(current_stop=95.0, ltp=110.0, peak=110.0)
        af_after_first = tsl._af

        # Second update with ltp < ep
        tsl.update_stop(current_stop=tsl._sar, ltp=105.0, peak=110.0)

        # af should not change
        assert tsl._af == af_after_first


class TestParabolicSARTSLOnPositionOpened:
    """Test on_position_opened seeds SAR from historical candle data."""

    @pytest.mark.asyncio
    async def test_on_position_opened_seeds_from_candles(self):
        """SAR should be seeded from first 5 candles' lows."""
        tsl = ParabolicSARTSL(af_start=0.02)

        # Mock broker with candle data
        mock_broker = AsyncMock()
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.exchange = "NYSE"

        candles = [
            {"low": 100.0, "high": 105.0},
            {"low": 99.0, "high": 106.0},
            {"low": 98.0, "high": 107.0},
            {"low": 97.0, "high": 108.0},
            {"low": 96.0, "high": 109.0},
            {"low": 95.0, "high": 110.0},
        ]
        mock_broker.get_ohlc.return_value = candles

        await tsl.on_position_opened(mock_position, mock_broker)

        # _sar should be min of first 5 lows
        assert tsl._sar == 96.0
        # _ep should be max of all candles
        assert tsl._ep == 110.0
        # _af should be reset to af_start
        assert tsl._af == 0.02

    @pytest.mark.asyncio
    async def test_on_position_opened_falls_back_on_broker_error(self):
        """If broker fails, should silently fall back."""
        tsl = ParabolicSARTSL()

        # Mock broker that raises
        mock_broker = AsyncMock()
        mock_broker.get_ohlc.side_effect = Exception("Broker unavailable")

        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.exchange = "NYSE"

        # Should not raise
        await tsl.on_position_opened(mock_position, mock_broker)

        # SAR should remain uninitialized (will be initialized later by initial_stop)
        assert tsl._sar is None

    @pytest.mark.asyncio
    async def test_on_position_opened_with_empty_candles(self):
        """If broker returns empty candles, should fall back gracefully."""
        tsl = ParabolicSARTSL()

        # Mock broker with empty response
        mock_broker = AsyncMock()
        mock_broker.get_ohlc.return_value = []

        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.exchange = "NYSE"

        # Should not raise
        await tsl.on_position_opened(mock_position, mock_broker)

        # SAR should remain uninitialized
        assert tsl._sar is None


class TestParabolicSARTSLStatefulBehavior:
    """Test that state persists across multiple update calls."""

    def test_state_persists_across_updates(self):
        """State (_sar, _ep, _af) should persist and evolve across calls."""
        tsl = ParabolicSARTSL(af_start=0.02, af_step=0.02, af_max=0.20)

        current_stop = tsl.initial_stop(fill_price=100.0)
        initial_sar = tsl._sar
        initial_ep = tsl._ep

        # Multiple updates
        for i in range(3):
            ltp = 100.0 + (i + 1) * 2
            current_stop = tsl.update_stop(current_stop=current_stop, ltp=ltp, peak=ltp)

        # State should have changed
        assert tsl._sar != initial_sar
        assert tsl._ep > initial_ep
        assert tsl._af > 0.02


class TestParabolicSARTSLParameters:
    """Test custom parameter initialization."""

    def test_custom_af_parameters(self):
        """Should accept custom af_start, af_step, af_max."""
        tsl = ParabolicSARTSL(af_start=0.01, af_step=0.01, af_max=0.10)
        assert tsl.af_start == 0.01
        assert tsl.af_step == 0.01
        assert tsl.af_max == 0.10

    def test_default_af_parameters(self):
        """Should use sensible defaults."""
        tsl = ParabolicSARTSL()
        assert tsl.af_start == 0.02
        assert tsl.af_step == 0.02
        assert tsl.af_max == 0.20
