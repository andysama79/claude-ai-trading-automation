from __future__ import annotations
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_fundamentals(symbol: str, exchange: str, provider: str = "yahoo") -> dict[str, Any]:
    """Fetch stock fundamentals asynchronously. Returns empty dict on failure.

    provider: "yahoo" (uses yfinance) | "none" (returns empty dict immediately)

    For Yahoo: yfinance Ticker.info is synchronous, wrapped in asyncio.to_thread.
    Returns subset of fields: pe_ratio, eps, revenue_growth, debt_equity, market_cap.
    Returns {} on any exception.
    """
    if provider == "none":
        return {}

    if provider == "yahoo":
        return await _fetch_yahoo(symbol, exchange)

    logger.warning("Unknown fundamentals provider: %s", provider)
    return {}


async def _fetch_yahoo(symbol: str, exchange: str) -> dict[str, Any]:
    """Fetch from yfinance. NSE symbols use .NS suffix, BSE uses .BO."""
    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    ticker_symbol = f"{symbol}{suffix}"

    try:
        info = await asyncio.to_thread(_get_yf_info, ticker_symbol)
        return {
            "pe_ratio": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_equity": info.get("debtToEquity"),
            "market_cap": info.get("marketCap"),
        }
    except Exception as e:
        logger.warning("Fundamentals fetch failed for %s: %s", ticker_symbol, e)
        return {}


def _get_yf_info(ticker_symbol: str) -> dict:
    """Synchronous yfinance call — run in thread via asyncio.to_thread."""
    import yfinance as yf
    return yf.Ticker(ticker_symbol).info
