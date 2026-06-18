from datetime import datetime, timezone
from trader.core.events import TradeSignal, Position, TradeRecord


def test_trade_signal_defaults():
    sig = TradeSignal(symbol="RELIANCE", exchange="NSE")
    assert sig.amount is None
    assert sig.tsl_mode is None
    assert sig.tsl_pct is None
    assert sig.tsl_tiers is None
    assert sig.tsl_k is None


def test_position_fields():
    now = datetime.now(timezone.utc)
    pos = Position(
        symbol="RELIANCE", exchange="NSE",
        qty=10, fill_price=2500.0,
        order_id="ord123", opened_at=now,
    )
    assert pos.qty == 10
    assert pos.fill_price == 2500.0


def test_trade_record_pnl():
    now = datetime.now(timezone.utc)
    rec = TradeRecord(
        symbol="RELIANCE", exchange="NSE",
        qty=10, buy_price=2500.0, sell_price=2750.0,
        pnl=2500.0, tsl_mode="fixed",
        opened_at=now, closed_at=now,
        fundamentals={},
    )
    assert rec.pnl == 2500.0
