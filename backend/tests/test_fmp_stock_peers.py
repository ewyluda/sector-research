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


class StockPeersTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_symbols_excluding_self(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "AMD", "companyName": "Advanced Micro Devices"},
            {"symbol": "nvda", "companyName": "NVIDIA (self, lowercase)"},
            {"symbol": "INTC", "companyName": "Intel"},
            {"companyName": "no symbol key — skipped"},
        ])
        peers, citation = await client.get_stock_peers("NVDA")
        self.assertEqual(peers, ["AMD", "INTC"])
        self.assertIsInstance(citation, Citation)

    async def test_non_list_payload_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"error": "not found"})
        peers, _ = await client.get_stock_peers("ZZZQ")
        self.assertEqual(peers, [])


if __name__ == "__main__":
    unittest.main()
