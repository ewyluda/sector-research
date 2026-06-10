"""Contract tests for the two date-range calendar methods on FMPClient.

Wire facts live-verified 2026-06-09 (see the unified-calendar spec):
  - /stable/economic-calendar?from=&to=  → rows with country/impact/event/date(+time)/estimate/previous/actual/unit
  - /stable/earnings-calendar?from=&to=  → global firehose rows {symbol, date, epsActual, epsEstimated, revenueActual, revenueEstimated, lastUpdated}
"""
import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.clients.fmp import FMPClient, TTL_CALENDAR


class EconomicCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_economic_calendar_with_range_params(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"event": "CPI YoY"}])

        data, citation = await client.get_economic_calendar("2026-06-08", "2026-06-12")

        endpoint, params = client._request.await_args.args
        self.assertEqual(endpoint, "economic-calendar")
        self.assertEqual(params, {"from": "2026-06-08", "to": "2026-06-12"})
        self.assertEqual(client._request.await_args.kwargs["ttl"], TTL_CALENDAR)
        self.assertEqual(data, [{"event": "CPI YoY"}])
        self.assertEqual(citation.source_name, "FMP /economic-calendar")
        self.assertEqual(citation.tier, 1)

    async def test_non_list_response_returns_empty_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"error": "nope"})

        data, _ = await client.get_economic_calendar("2026-06-08", "2026-06-12")

        self.assertEqual(data, [])


class EarningsCalendarRangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_earnings_calendar_firehose_with_range_params(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "NVDA"}])

        data, citation = await client.get_earnings_calendar_range("2026-06-08", "2026-06-12")

        endpoint, params = client._request.await_args.args
        self.assertEqual(endpoint, "earnings-calendar")
        self.assertEqual(params, {"from": "2026-06-08", "to": "2026-06-12"})
        self.assertEqual(client._request.await_args.kwargs["ttl"], TTL_CALENDAR)
        self.assertEqual(data, [{"symbol": "NVDA"}])
        self.assertEqual(citation.source_name, "FMP /earnings-calendar")

    async def test_non_list_response_returns_empty_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=None)

        data, _ = await client.get_earnings_calendar_range("2026-06-08", "2026-06-12")

        self.assertEqual(data, [])


if __name__ == "__main__":
    unittest.main()
