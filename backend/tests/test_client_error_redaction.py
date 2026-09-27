"""Client errors must not carry API keys (they reach run state and HTTP responses)."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

import httpx

from backend.app.clients.fmp import FMPClient, FMPClientError
from backend.app.clients.fred import FREDClient, FREDClientError

SECRET = "SECRET-KEY-123"


def _always_401(request: httpx.Request) -> httpx.Response:
    return httpx.Response(401, request=request)


async def _no_sleep(_seconds):
    return None


class ClientErrorRedactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_fmp_error_text_has_no_apikey(self):
        client = FMPClient()
        client._api_key = SECRET
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(_always_401))
        with patch("asyncio.sleep", _no_sleep):
            with self.assertRaises(FMPClientError) as ctx:
                await client._request("quote", {"symbol": "AAPL"})
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertIn("apikey=REDACTED", str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)  # raw httpx error not chained

    async def test_fred_error_text_has_no_api_key(self):
        client = FREDClient()
        client._api_key = SECRET
        client._http = httpx.AsyncClient(transport=httpx.MockTransport(_always_401))
        with patch("asyncio.sleep", _no_sleep):
            with self.assertRaises(FREDClientError) as ctx:
                await client._request("series/observations", {"series_id": "DGS10"})
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)


if __name__ == "__main__":
    unittest.main()
