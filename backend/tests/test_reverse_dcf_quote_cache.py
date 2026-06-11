"""Tests for the 30-second TTL cache on _fetch_live_price in models_api.

Verifies:
  1. First call hits FMP.
  2. Second call within TTL is served from cache (FMP not called again).
  3. After TTL expires, next call re-fetches from FMP.
  4. Cache is keyed per ticker (different tickers don't share entries).
  5. A price of 0.0 (FMP failure / zero) is never cached.
"""

import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

import backend.app.api.models_api as models_api_mod
from backend.app.api.models_api import _fetch_live_price


def _make_fmp(price: float | None):
    """Return a mock FMPClient whose get_quote returns ({"price": price}, citation)."""
    fmp = MagicMock()
    citation = MagicMock()
    if price is None:
        fmp.get_quote = AsyncMock(side_effect=Exception("FMP error"))
    else:
        fmp.get_quote = AsyncMock(return_value=({"price": price}, citation))
    return fmp


def _clear_cache():
    models_api_mod._LIVE_PRICE_CACHE.clear()


class TestFetchLivePriceCache(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _clear_cache()

    def tearDown(self):
        _clear_cache()

    async def test_first_call_hits_fmp(self):
        """First call for a ticker must hit FMP exactly once."""
        fmp = _make_fmp(150.0)
        price = await _fetch_live_price(fmp, "AAPL")
        self.assertEqual(price, 150.0)
        fmp.get_quote.assert_called_once_with("AAPL")

    async def test_second_within_ttl_cached(self):
        """Second call within the TTL window returns the cached value without calling FMP again."""
        fmp = _make_fmp(200.0)
        first = await _fetch_live_price(fmp, "MSFT")
        second = await _fetch_live_price(fmp, "MSFT")
        self.assertEqual(first, 200.0)
        self.assertEqual(second, 200.0)
        # FMP called only once despite two fetches
        self.assertEqual(fmp.get_quote.call_count, 1)

    async def test_expiry_refetches(self):
        """After TTL has elapsed the next call re-fetches from FMP."""
        fmp = _make_fmp(300.0)
        await _fetch_live_price(fmp, "GOOG")

        # Manually backdate the cached entry so it appears expired
        ticker = "GOOG"
        cached_price, _ = models_api_mod._LIVE_PRICE_CACHE[ticker]
        models_api_mod._LIVE_PRICE_CACHE[ticker] = (
            cached_price,
            time.monotonic() - models_api_mod._LIVE_PRICE_TTL_SECONDS - 1.0,
        )

        fmp.get_quote = AsyncMock(return_value=({"price": 310.0}, MagicMock()))
        price2 = await _fetch_live_price(fmp, "GOOG")
        self.assertEqual(price2, 310.0)
        self.assertEqual(fmp.get_quote.call_count, 1)  # called once for the re-fetch

    async def test_per_ticker_keying(self):
        """Cache entries are isolated per ticker — AAPL and MSFT don't share."""
        fmp_aapl = _make_fmp(150.0)
        fmp_msft = _make_fmp(200.0)
        price_aapl = await _fetch_live_price(fmp_aapl, "AAPL")
        price_msft = await _fetch_live_price(fmp_msft, "MSFT")

        # Each FMP mock was called exactly once with its own ticker
        fmp_aapl.get_quote.assert_called_once_with("AAPL")
        fmp_msft.get_quote.assert_called_once_with("MSFT")
        self.assertEqual(price_aapl, 150.0)
        self.assertEqual(price_msft, 200.0)

        # A second call for AAPL must not hit MSFT's mock (and vice versa)
        await _fetch_live_price(fmp_aapl, "AAPL")
        await _fetch_live_price(fmp_msft, "MSFT")
        self.assertEqual(fmp_aapl.get_quote.call_count, 1)
        self.assertEqual(fmp_msft.get_quote.call_count, 1)

    async def test_zero_price_not_cached(self):
        """A price of 0.0 (FMP error or zero quote) must not be written to the cache."""
        fmp = _make_fmp(None)  # raises → returns 0.0
        price = await _fetch_live_price(fmp, "ERR")
        self.assertEqual(price, 0.0)
        self.assertNotIn("ERR", models_api_mod._LIVE_PRICE_CACHE)

        # Subsequent call must still hit FMP (not serve a cached 0.0)
        fmp.get_quote = AsyncMock(return_value=({"price": 99.0}, MagicMock()))
        price2 = await _fetch_live_price(fmp, "ERR")
        self.assertEqual(price2, 99.0)
        fmp.get_quote.assert_called_once_with("ERR")


if __name__ == "__main__":
    unittest.main()
