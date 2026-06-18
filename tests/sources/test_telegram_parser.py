import pytest
from trader.sources.telegram import parse_signal
from trader.core.events import TradeSignal

# Default symbol_regex = r"\b([A-Z&]{2,20})\b"
REGEX = r"\b([A-Z&]{2,20})\b"


def test_parse_plain_symbol():
    sig = parse_signal("RELIANCE Q3 earnings beat, buy now", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.symbol == "RELIANCE"
    assert sig.exchange == "NSE"
    assert sig.amount == 10000.0


def test_parse_symbol_with_ampersand():
    sig = parse_signal("M&M strong results", REGEX, default_amount=5000.0)
    assert sig is not None
    assert sig.symbol == "M&M"


def test_parse_override_amount():
    sig = parse_signal("INFY buy AMOUNT:20000", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.amount == 20000.0


def test_parse_override_tsl_mode():
    sig = parse_signal("TCS strong beat TSL:chandelier", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.tsl_mode == "chandelier"


def test_parse_override_tsl_pct():
    sig = parse_signal("WIPRO beat TSL_PCT:3.5", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.tsl_pct == 3.5


def test_parse_no_symbol_returns_none():
    sig = parse_signal("no uppercase symbols here 123", REGEX, default_amount=10000.0)
    assert sig is None


def test_parse_skips_common_words():
    # Common words like "BUY", "NSE", "BSE" are filtered
    sig = parse_signal("BUY RELIANCE on NSE now", REGEX, default_amount=10000.0)
    assert sig is not None
    assert sig.symbol == "RELIANCE"
