"""Pins FMPClient.get_senate_trades / get_house_trades: list passthrough,
non-list → [], citation per call. Mocking convention: replace client._request
with AsyncMock (same as test_fmp_parsers.py)."""

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

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation


class SenateTradesTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_passthrough_with_citation(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "NVDA", "type": "Sale"}])
        rows, citation = await client.get_senate_trades("NVDA")
        self.assertEqual(rows, [{"symbol": "NVDA", "type": "Sale"}])
        self.assertIsInstance(citation, Citation)
        client._request.assert_awaited_once()
        endpoint = client._request.await_args.args[0]
        self.assertEqual(endpoint, "senate-trades")

    async def test_non_list_payload_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "denied"})
        rows, _ = await client.get_senate_trades("NVDA")
        self.assertEqual(rows, [])


class HouseTradesTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_passthrough_hits_house_endpoint(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "NVDA"}])
        rows, citation = await client.get_house_trades("NVDA")
        self.assertEqual(len(rows), 1)
        self.assertIsInstance(citation, Citation)
        endpoint = client._request.await_args.args[0]
        self.assertEqual(endpoint, "house-trades")

    async def test_none_payload_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=None)
        rows, _ = await client.get_house_trades("NVDA")
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
