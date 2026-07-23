import math
import pytest
from trader.tsl.stepped import SteppedTSL


class TestSteppedTSLActivePercentage:
    """Test _active_pct returns correct tier based on gain."""

    @pytest.fixture
    def tiers(self):
        """Standard test tiers: gain thresholds at 10, 30, 60, then inf."""
        return [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)]

    @pytest.fixture
    def tsl(self, tiers):
        """Create SteppedTSL with standard tiers."""
        return SteppedTSL(fill_price=100.0, tiers=tiers)

    def test_at_entry_gain_zero_uses_first_tier(self, tsl):
        """At entry (peak=fill_price, gain=0%), use first tier's 8.0%."""
        pct = tsl._active_pct(peak=100.0)
        assert pct == 8.0

    def test_at_15_percent_gain_uses_second_tier(self, tsl):
        """At 15% gain (past first threshold 10%), use 5.0%."""
        pct = tsl._active_pct(peak=115.0)
        assert pct == 5.0

    def test_at_45_percent_gain_uses_third_tier(self, tsl):
        """At 45% gain (past second threshold 30%), use 3.0%."""
        pct = tsl._active_pct(peak=145.0)
        assert pct == 3.0

    def test_at_70_percent_gain_uses_fourth_tier(self, tsl):
        """At 70% gain (past third threshold 60%), use 2.0%."""
        pct = tsl._active_pct(peak=170.0)
        assert pct == 2.0

    def test_exactly_at_threshold_uses_upper_tier(self, tsl):
        """At exactly 10% gain (at threshold), move to second tier (5.0%)."""
        pct = tsl._active_pct(peak=110.0)
        assert pct == 5.0

    def test_just_above_threshold_uses_upper_tier(self, tsl):
        """Just above 10% gain (10.1%), use second tier (5.0%)."""
        pct = tsl._active_pct(peak=110.1)
        assert pct == 5.0


class TestSteppedTSLInitialStop:
    """Test initial_stop at position entry."""

    @pytest.fixture
    def tiers(self):
        return [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)]

    @pytest.fixture
    def tsl(self, tiers):
        return SteppedTSL(fill_price=100.0, tiers=tiers)

    def test_initial_stop_uses_first_tier_pct(self, tsl):
        """At entry (gain=0%), stop = fill × (1 - 8.0/100) = 92.0"""
        stop = tsl.initial_stop(fill_price=100.0)
        assert stop == 92.0

    def test_initial_stop_with_different_fill_price(self, tiers):
        """fill=200, first tier 8.0% → stop = 184.0"""
        tsl = SteppedTSL(fill_price=200.0, tiers=tiers)
        stop = tsl.initial_stop(fill_price=200.0)
        assert stop == 184.0


class TestSteppedTSLUpdateStop:
    """Test update_stop tightens as peak grows through tiers."""

    @pytest.fixture
    def tiers(self):
        return [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)]

    @pytest.fixture
    def tsl(self, tiers):
        return SteppedTSL(fill_price=100.0, tiers=tiers)

    def test_update_stop_at_entry(self, tsl):
        """At entry, stop = 100 × (1 - 8.0/100) = 92.0"""
        current_stop = 92.0
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=100.0, peak=100.0)
        assert new_stop == 92.0

    def test_update_stop_tightens_at_15_percent_gain(self, tsl):
        """Peak at 115.0 (15% gain, uses 5.0%): stop = 115 × 0.95 = 109.25"""
        current_stop = 92.0
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=115.0, peak=115.0)
        assert new_stop == 109.25

    def test_update_stop_tightens_at_45_percent_gain(self, tsl):
        """Peak at 145.0 (45% gain, uses 3.0%): stop = 145 × 0.97 = 140.65"""
        current_stop = 109.25
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=145.0, peak=145.0)
        assert new_stop == 140.65

    def test_update_stop_tightens_at_70_percent_gain(self, tsl):
        """Peak at 170.0 (70% gain, uses 2.0%): stop = 170 × 0.98 = 166.6"""
        current_stop = 140.65
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=170.0, peak=170.0)
        assert new_stop == 166.6

    def test_update_stop_monotonically_increasing(self, tsl):
        """Stop never decreases through sequence of updates."""
        current_stop = tsl.initial_stop(fill_price=100.0)
        assert current_stop == 92.0

        # Peak rises to 115: stop becomes 109.25
        current_stop = tsl.update_stop(current_stop=current_stop, ltp=115.0, peak=115.0)
        assert current_stop == 109.25

        # LTP drops but peak stays at 115 (no higher peak): stop stays same
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=110.0, peak=115.0)
        assert new_stop == 109.25

        # Peak rises to 145: stop becomes 140.65
        current_stop = tsl.update_stop(current_stop=current_stop, ltp=145.0, peak=145.0)
        assert current_stop == 140.65

        # Even if LTP drops dramatically, stop never decreases
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=100.0, peak=145.0)
        assert new_stop == 140.65

    def test_update_stop_respects_previous_higher_stop(self, tsl):
        """If tier tightening produces lower stop than current, keep current."""
        current_stop = 109.25
        # Even if peak doesn't change, stop should not go down
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=114.0, peak=115.0)
        assert new_stop == 109.25


class TestSteppedTSLTierOrdering:
    """Test that tiers are automatically sorted by threshold."""

    def test_unsorted_tiers_are_sorted(self):
        """Tiers provided out of order should be sorted ascending by threshold."""
        # Provide tiers out of order
        unsorted_tiers = [(60, 3.0), (10, 8.0), (math.inf, 2.0), (30, 5.0)]
        tsl = SteppedTSL(fill_price=100.0, tiers=unsorted_tiers)
        # Should use 8.0% at entry (first tier after sorting)
        assert tsl._active_pct(peak=100.0) == 8.0
        # Should use 5.0% at 15% gain
        assert tsl._active_pct(peak=115.0) == 5.0


class TestSteppedTSLEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def tiers(self):
        return [(10, 8.0), (30, 5.0), (60, 3.0), (math.inf, 2.0)]

    def test_single_tier_inf(self, tiers):
        """Single tier with inf threshold."""
        single_tier_tsl = SteppedTSL(fill_price=100.0, tiers=[(math.inf, 5.0)])
        assert single_tier_tsl._active_pct(peak=100.0) == 5.0
        assert single_tier_tsl._active_pct(peak=1000.0) == 5.0

    def test_very_small_fill_price(self, tiers):
        """Fill price of 0.01 with very high percentage gain."""
        tsl = SteppedTSL(fill_price=0.01, tiers=tiers)
        # At 50x price: gain = (0.5 / 0.01 - 1) * 100 = 4900%
        pct = tsl._active_pct(peak=0.5)
        assert pct == 2.0  # Should use the last tier

    def test_large_fill_price(self, tiers):
        """Large fill price still calculates correctly."""
        tsl = SteppedTSL(fill_price=10000.0, tiers=tiers)
        # At 11000: gain = 10%, moves to second tier (5.0%)
        pct = tsl._active_pct(peak=11000.0)
        assert pct == 5.0
