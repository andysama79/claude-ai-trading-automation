import pytest
from trader.tsl.fixed import FixedPctTSL


class TestFixedPctTSLInitialStop:
    """Test initial_stop computes stop price at position entry."""

    def test_initial_stop_calculates_correctly(self):
        """fill=100, pct=5 → stop=95.0"""
        tsl = FixedPctTSL(pct=5.0)
        stop = tsl.initial_stop(fill_price=100.0)
        assert stop == 95.0

    def test_initial_stop_with_different_pct(self):
        """fill=200, pct=10 → stop=180.0"""
        tsl = FixedPctTSL(pct=10.0)
        stop = tsl.initial_stop(fill_price=200.0)
        assert stop == 180.0


class TestFixedPctTSLUpdateStop:
    """Test update_stop rises with peak and stays monotonic."""

    def test_update_stop_rises_with_peak(self):
        """peak=110, pct=5 → new_stop=104.5 (higher than initial 95)"""
        tsl = FixedPctTSL(pct=5.0)
        current_stop = tsl.initial_stop(fill_price=100.0)  # 95.0
        # Simulate peak rising to 110
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=108.0, peak=110.0)
        assert new_stop == 104.5

    def test_update_stop_monotonic_never_decreases(self):
        """Stop never decreases even when peak drops below previous peak."""
        tsl = FixedPctTSL(pct=5.0)
        current_stop = tsl.initial_stop(fill_price=100.0)  # 95.0

        # Peak rises to 110: stop becomes 104.5
        current_stop = tsl.update_stop(current_stop=current_stop, ltp=108.0, peak=110.0)
        assert current_stop == 104.5

        # LTP drops but peak stays at 110
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=105.0, peak=110.0)
        assert new_stop == 104.5  # Should not decrease

    def test_update_stop_increases_when_peak_exceeds_previous(self):
        """Stop increases when peak exceeds the previous peak."""
        tsl = FixedPctTSL(pct=5.0)
        current_stop = tsl.initial_stop(fill_price=100.0)  # 95.0

        # Peak rises to 110: stop becomes 104.5
        current_stop = tsl.update_stop(current_stop=current_stop, ltp=108.0, peak=110.0)
        assert current_stop == 104.5

        # Peak rises further to 120: stop becomes 114.0
        new_stop = tsl.update_stop(current_stop=current_stop, ltp=118.0, peak=120.0)
        assert new_stop == 114.0


class TestFixedPctTSLShouldExit:
    """Test should_exit returns True/False based on ltp vs stop."""

    def test_should_exit_returns_true_when_ltp_at_stop(self):
        """should_exit(ltp=95, stop=95) → True"""
        tsl = FixedPctTSL(pct=5.0)
        assert tsl.should_exit(ltp=95.0, stop=95.0) is True

    def test_should_exit_returns_true_when_ltp_below_stop(self):
        """should_exit(ltp=90, stop=95) → True"""
        tsl = FixedPctTSL(pct=5.0)
        assert tsl.should_exit(ltp=90.0, stop=95.0) is True

    def test_should_exit_returns_false_when_ltp_above_stop(self):
        """should_exit(ltp=100, stop=95) → False"""
        tsl = FixedPctTSL(pct=5.0)
        assert tsl.should_exit(ltp=100.0, stop=95.0) is False
