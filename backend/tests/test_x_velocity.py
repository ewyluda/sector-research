"""X velocity from daily post counts (2026-09-27). The old computation could
only return ratio 1.0, made a discarded duplicate search, capped counts at 100,
and stored 429s as real zero-mention signals."""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

import httpx  # noqa: E402

from backend.app.clients.x_client import (  # noqa: E402
    XClient,
    XClientError,
    velocity_from_daily_counts,
)


class VelocityMathTests(unittest.TestCase):
    def test_accelerating(self):
        # 4 baseline days at 100, 3 recent at 200, then today's partial bucket.
        v = velocity_from_daily_counts([100, 100, 100, 100, 200, 200, 200, 17])
        self.assertEqual(v["ratio"], 2.0)
        self.assertEqual(v["direction"], "accelerating")
        self.assertEqual(v["count_7d"], 1000)  # no 100-post cap

    def test_decelerating_and_stable(self):
        self.assertEqual(velocity_from_daily_counts([300, 300, 300, 300, 100, 100, 100, 5])["direction"], "decelerating")
        self.assertEqual(velocity_from_daily_counts([50] * 8)["direction"], "stable")

    def test_no_baseline(self):
        v = velocity_from_daily_counts([0, 0, 0, 0, 3, 4, 5, 1])
        self.assertIsNone(v["ratio"])
        self.assertEqual(v["direction"], "accelerating")
        self.assertIsNone(velocity_from_daily_counts([])["ratio"])


def _status_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.x.com/2/tweets/counts/recent")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, request=req))


class XErrorTests(unittest.IsolatedAsyncioTestCase):
    async def _client_raising(self, code: int) -> XClient:
        client = XClient()
        client._limiter = MagicMock(acquire=AsyncMock())
        resp = MagicMock(raise_for_status=MagicMock(side_effect=_status_error(code)))
        client._http = MagicMock(get=AsyncMock(return_value=resp))
        return client

    async def test_rate_limit_raises_instead_of_returning_zero_mentions(self):
        client = await self._client_raising(429)
        with self.assertRaisesRegex(XClientError, "429"):
            await client.compute_velocity_signal("NVDA")

    async def test_out_of_credits_raises(self):
        client = await self._client_raising(402)
        with self.assertRaisesRegex(XClientError, "credits depleted"):
            await client.compute_velocity_signal("NVDA")

    async def test_one_counts_request_per_ticker(self):
        client = XClient()
        client._limiter = MagicMock(acquire=AsyncMock())
        resp = MagicMock(raise_for_status=MagicMock(),
                         json=MagicMock(return_value={"data": [{"tweet_count": 10}] * 8}))
        client._http = MagicMock(get=AsyncMock(return_value=resp))
        data, cit = await client.compute_velocity_signal("NVDA")
        self.assertEqual(client._http.get.await_count, 1)
        self.assertIn("/tweets/counts/recent", client._http.get.call_args.args[0])
        self.assertEqual(data["ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
