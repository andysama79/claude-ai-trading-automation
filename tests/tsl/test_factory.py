import pytest
from trader.core.events import TradeSignal
from trader.tsl.factory import build_tsl_strategy
from trader.tsl.fixed import FixedPctTSL
from trader.tsl.stepped import SteppedTSL
from trader.tsl.atr import ATRTSLStrategy
from trader.tsl.chandelier import ChandelierTSL
from trader.tsl.psar import ParabolicSARTSL


class TestFactoryDefaultMode:
    """Test default mode resolution when signal.tsl_mode is None."""

    def test_signal_tsl_mode_none_uses_config_default_mode(self):
        """Signal with tsl_mode=None → config default_mode="fixed" → FixedPctTSL"""
        signal = TradeSignal(symbol="SBIN", tsl_mode=None)
        config = {"default_mode": "fixed", "default_pct": 5.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, FixedPctTSL)
        assert strategy.pct == 5.0


class TestFactoryModeOverride:
    """Test that signal.tsl_mode overrides config mode."""

    def test_signal_tsl_mode_overrides_config(self):
        """Signal with tsl_mode="atr" overrides config mode → ATRTSLStrategy"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="atr")
        config = {"tsl_mode": "fixed", "k": 2.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ATRTSLStrategy)
        assert strategy.k == 2.0


class TestFactoryFixedMode:
    """Test FixedPctTSL strategy resolution."""

    def test_fixed_mode_with_default_pct(self):
        """Signal mode="fixed" with no pct → uses config default_pct"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="fixed", tsl_pct=None)
        config = {"default_pct": 5.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, FixedPctTSL)
        assert strategy.pct == 5.0

    def test_signal_tsl_pct_overrides_config_default_pct(self):
        """Signal with tsl_pct=3.0 overrides config default_pct=5.0"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="fixed", tsl_pct=3.0)
        config = {"default_pct": 5.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, FixedPctTSL)
        assert strategy.pct == 3.0

    def test_fixed_mode_default_pct_when_config_missing(self):
        """Signal mode="fixed", no config default_pct → uses 5.0"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="fixed")
        config = {}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, FixedPctTSL)
        assert strategy.pct == 5.0


class TestFactorySteppedMode:
    """Test SteppedTSL strategy resolution."""

    def test_stepped_mode_with_default_tiers(self):
        """Signal mode="stepped" → returns SteppedTSL with default tiers"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="stepped")
        config = {}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, SteppedTSL)
        # Check fill_price is 0.0 (placeholder)
        assert strategy.fill_price == 0.0
        # Check default tiers
        assert len(strategy.tiers) == 4
        assert strategy.tiers[0] == (10, 8.0)

    def test_signal_tsl_tiers_overrides_config(self):
        """Signal with tsl_tiers overrides config tiers"""
        custom_tiers = [(5, 10.0), (15, 7.0), (float("inf"), 4.0)]
        signal = TradeSignal(symbol="SBIN", tsl_mode="stepped", tsl_tiers=custom_tiers)
        config = {"tiers": [(10, 8.0), (30, 5.0), (60, 3.0), (float("inf"), 2.0)]}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, SteppedTSL)
        assert strategy.tiers == custom_tiers


class TestFactoryATRMode:
    """Test ATRTSLStrategy resolution."""

    def test_atr_mode_with_default_k(self):
        """Signal mode="atr" with no k → uses config k=2.0"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="atr")
        config = {"k": 2.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ATRTSLStrategy)
        assert strategy.k == 2.0

    def test_atr_mode_default_k_when_config_missing(self):
        """Signal mode="atr", no config k → uses 2.0"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="atr")
        config = {}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ATRTSLStrategy)
        assert strategy.k == 2.0

    def test_signal_tsl_k_overrides_config_k(self):
        """Signal with tsl_k=1.5 overrides config k=3.0"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="atr", tsl_k=1.5)
        config = {"k": 3.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ATRTSLStrategy)
        assert strategy.k == 1.5


class TestFactoryChandelierMode:
    """Test ChandelierTSL strategy resolution."""

    def test_chandelier_mode_with_default_params(self):
        """Signal mode="chandelier" → returns ChandelierTSL with defaults"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="chandelier")
        config = {}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ChandelierTSL)
        assert strategy.k == 3.0
        assert strategy.period == 14

    def test_chandelier_mode_with_config_k(self):
        """Signal mode="chandelier" uses config k"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="chandelier")
        config = {"k": 2.5}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ChandelierTSL)
        assert strategy.k == 2.5

    def test_signal_tsl_k_overrides_chandelier_config_k(self):
        """Signal with tsl_k overrides config k for chandelier"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="chandelier", tsl_k=2.0)
        config = {"k": 3.0}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ChandelierTSL)
        assert strategy.k == 2.0


class TestFactoryPSARMode:
    """Test ParabolicSARTSL strategy resolution."""

    def test_psar_mode_returns_psar_strategy(self):
        """Signal mode="psar" → returns ParabolicSARTSL"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="psar")
        config = {}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, ParabolicSARTSL)


class TestFactorySteppedModeEndToEnd:
    """Regression test for the SteppedTSL zero-division bug (fixed in stepped.py).

    build_tsl_strategy() constructs SteppedTSL(fill_price=0.0, ...) as a
    placeholder; only initial_stop() receives the real fill price. Prior to
    the fix, SteppedTSL._active_pct() divided by the constructor's
    self.fill_price (permanently 0.0), so calling initial_stop() through the
    factory-built strategy raised ZeroDivisionError on the very first live
    tick. Unit tests that construct SteppedTSL directly with a real
    fill_price never exercised this path — this test goes through the
    factory exactly as Engine.place_buy() -> build_tsl_strategy() ->
    initial_stop() does in production.
    """

    def test_factory_built_stepped_strategy_survives_initial_stop(self):
        signal = TradeSignal(symbol="SBIN", tsl_mode="stepped")
        config = {"tiers": [(10, 8.0), (30, 5.0), (60, 3.0), (float("inf"), 2.0)]}
        strategy = build_tsl_strategy(signal, config)
        assert isinstance(strategy, SteppedTSL)

        # Real fill price arrives only here, as it does in Engine after a buy fills.
        stop = strategy.initial_stop(fill_price=2500.0)

        assert stop == pytest.approx(2500.0 * (1 - 8.0 / 100))
        assert strategy.fill_price == 2500.0

    def test_factory_built_stepped_strategy_tightens_across_ticks(self):
        """Same object survives multiple update_stop() calls with real gains."""
        signal = TradeSignal(symbol="SBIN", tsl_mode="stepped")
        config = {"tiers": [(10, 8.0), (30, 5.0), (60, 3.0), (float("inf"), 2.0)]}
        strategy = build_tsl_strategy(signal, config)

        stop = strategy.initial_stop(fill_price=100.0)
        assert stop == 92.0

        stop = strategy.update_stop(current_stop=stop, ltp=115.0, peak=115.0)
        assert stop == pytest.approx(109.25)


class TestFactoryErrorHandling:
    """Test error handling for invalid modes."""

    def test_unknown_mode_raises_value_error(self):
        """Unknown mode raises ValueError"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="unknown_mode")
        config = {}
        with pytest.raises(ValueError, match="Unknown TSL mode: 'unknown_mode'"):
            build_tsl_strategy(signal, config)

    def test_whitespace_only_mode_raises_error(self):
        """Whitespace-only mode string raises ValueError"""
        signal = TradeSignal(symbol="SBIN", tsl_mode="   ")
        config = {}
        with pytest.raises(ValueError, match="Unknown TSL mode"):
            build_tsl_strategy(signal, config)
