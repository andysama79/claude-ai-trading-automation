from trader.core.events import TradeSignal
from trader.tsl.base import TSLStrategy
from trader.tsl.fixed import FixedPctTSL
from trader.tsl.stepped import SteppedTSL
from trader.tsl.atr import ATRTSLStrategy
from trader.tsl.chandelier import ChandelierTSL
from trader.tsl.psar import ParabolicSARTSL


def build_tsl_strategy(signal: TradeSignal, config: dict) -> TSLStrategy:
    """Resolve TSL config + per-signal overrides → strategy instance.

    Per-signal fields on TradeSignal override config defaults:
      signal.tsl_mode   → overrides config["tsl_mode"]  (or config["default_mode"])
      signal.tsl_pct    → overrides config["default_pct"]
      signal.tsl_tiers  → overrides config["tiers"]
      signal.tsl_k      → overrides config["k"]

    fill_price is required for SteppedTSL; pass 0.0 as placeholder —
    SteppedTSL.initial_stop receives the real fill_price at position open.
    """
    mode = signal.tsl_mode or config.get("tsl_mode") or config.get("default_mode", "fixed")
    # Strip whitespace if mode is a string
    if isinstance(mode, str):
        mode = mode.strip()

    match mode:
        case "fixed":
            pct = signal.tsl_pct or config.get("default_pct", 5.0)
            return FixedPctTSL(pct=pct)

        case "stepped":
            tiers = signal.tsl_tiers or config.get("tiers", [(10, 8.0), (30, 5.0), (60, 3.0), (float("inf"), 2.0)])
            return SteppedTSL(fill_price=0.0, tiers=tiers)

        case "atr":
            k = signal.tsl_k or config.get("k", 2.0)
            return ATRTSLStrategy(k=k)

        case "chandelier":
            k = signal.tsl_k or config.get("k", 3.0)
            return ChandelierTSL(k=k)

        case "psar":
            return ParabolicSARTSL()

        case _:
            raise ValueError(f"Unknown TSL mode: {mode!r}")
