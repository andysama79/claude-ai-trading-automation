import pytest
from unittest.mock import patch, MagicMock
import asyncio

from trader.fundamentals.fetcher import fetch_fundamentals, _fetch_yahoo


MOCK_YF_INFO = {
    "trailingPE": 28.5,
    "trailingEps": 12.3,
    "revenueGrowth": 0.15,
    "debtToEquity": 45.2,
    "marketCap": 1_500_000_000_000,
}


class TestFetchFundamentals:
    """Test fetch_fundamentals with different providers and exchanges."""

    @pytest.mark.asyncio
    async def test_provider_none_returns_empty_dict(self):
        """provider='none' should return empty dict immediately."""
        result = await fetch_fundamentals("RELIANCE", "NSE", provider="none")
        assert result == {}

    @pytest.mark.asyncio
    async def test_provider_yahoo_nse_exchange(self):
        """provider='yahoo' with NSE exchange should add .NS suffix."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO):
            result = await fetch_fundamentals("RELIANCE", "NSE", provider="yahoo")

            assert result["pe_ratio"] == 28.5
            assert result["eps"] == 12.3
            assert result["revenue_growth"] == 0.15
            assert result["debt_equity"] == 45.2
            assert result["market_cap"] == 1_500_000_000_000

    @pytest.mark.asyncio
    async def test_provider_yahoo_bse_exchange(self):
        """provider='yahoo' with BSE exchange should add .BO suffix."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO):
            result = await fetch_fundamentals("RELIANCE", "BSE", provider="yahoo")

            assert result["pe_ratio"] == 28.5
            assert result["eps"] == 12.3
            assert result["revenue_growth"] == 0.15
            assert result["debt_equity"] == 45.2
            assert result["market_cap"] == 1_500_000_000_000

    @pytest.mark.asyncio
    async def test_provider_yahoo_exception_returns_empty_dict(self):
        """provider='yahoo' with yfinance exception should return empty dict."""
        with patch("trader.fundamentals.fetcher._get_yf_info", side_effect=Exception("network error")):
            result = await fetch_fundamentals("RELIANCE", "NSE", provider="yahoo")

            assert result == {}

    @pytest.mark.asyncio
    async def test_provider_unknown_returns_empty_dict(self):
        """Unknown provider should return empty dict."""
        result = await fetch_fundamentals("RELIANCE", "NSE", provider="unknown")

        assert result == {}

    @pytest.mark.asyncio
    async def test_returned_dict_contains_expected_keys(self):
        """Returned dict should contain all expected keys."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO):
            result = await fetch_fundamentals("RELIANCE", "NSE", provider="yahoo")

            expected_keys = {"pe_ratio", "eps", "revenue_growth", "debt_equity", "market_cap"}
            assert set(result.keys()) == expected_keys


class TestFetchYahoo:
    """Test _fetch_yahoo helper function."""

    @pytest.mark.asyncio
    async def test_fetch_yahoo_constructs_correct_nse_ticker(self):
        """_fetch_yahoo should construct NSE ticker with .NS suffix."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO) as mock_get:
            await _fetch_yahoo("RELIANCE", "NSE")

            mock_get.assert_called_once_with("RELIANCE.NS")

    @pytest.mark.asyncio
    async def test_fetch_yahoo_constructs_correct_bse_ticker(self):
        """_fetch_yahoo should construct BSE ticker with .BO suffix."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO) as mock_get:
            await _fetch_yahoo("RELIANCE", "BSE")

            mock_get.assert_called_once_with("RELIANCE.BO")

    @pytest.mark.asyncio
    async def test_fetch_yahoo_case_insensitive_exchange(self):
        """_fetch_yahoo should handle case-insensitive exchange names."""
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=MOCK_YF_INFO) as mock_get:
            await _fetch_yahoo("RELIANCE", "nse")

            mock_get.assert_called_once_with("RELIANCE.NS")

    @pytest.mark.asyncio
    async def test_fetch_yahoo_maps_yf_fields_correctly(self):
        """_fetch_yahoo should map yfinance fields to expected output fields."""
        mock_info = {
            "trailingPE": 28.5,
            "trailingEps": 12.3,
            "revenueGrowth": 0.15,
            "debtToEquity": 45.2,
            "marketCap": 1_500_000_000_000,
        }
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=mock_info):
            result = await _fetch_yahoo("RELIANCE", "NSE")

            assert result["pe_ratio"] == mock_info["trailingPE"]
            assert result["eps"] == mock_info["trailingEps"]
            assert result["revenue_growth"] == mock_info["revenueGrowth"]
            assert result["debt_equity"] == mock_info["debtToEquity"]
            assert result["market_cap"] == mock_info["marketCap"]

    @pytest.mark.asyncio
    async def test_fetch_yahoo_handles_missing_fields(self):
        """_fetch_yahoo should handle missing fields gracefully."""
        mock_info = {
            "trailingPE": 28.5,
            # Missing other fields
        }
        with patch("trader.fundamentals.fetcher._get_yf_info", return_value=mock_info):
            result = await _fetch_yahoo("RELIANCE", "NSE")

            assert result["pe_ratio"] == 28.5
            assert result["eps"] is None
            assert result["revenue_growth"] is None
            assert result["debt_equity"] is None
            assert result["market_cap"] is None

    @pytest.mark.asyncio
    async def test_fetch_yahoo_exception_handling(self):
        """_fetch_yahoo should return empty dict on exception."""
        with patch("trader.fundamentals.fetcher._get_yf_info", side_effect=Exception("network error")):
            result = await _fetch_yahoo("RELIANCE", "NSE")

            assert result == {}
