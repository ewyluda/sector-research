"""Tests for compute_delta in-flight guard — concurrent calls must not race the unique constraint."""
import asyncio
import unittest
from unittest.mock import MagicMock, patch

from backend.app.services import transcript_delta


class TestComputeDeltaInFlightGuard(unittest.TestCase):
    def test_concurrent_same_key_calls_serialize(self):
        """Two parallel compute_delta() calls for the same (ticker, fingerprint) must
        serialize: Haiku is called exactly once, the second caller returns the cached row."""
        # Fake transcripts so fingerprint is stable
        fake_transcripts = [
            {"year": 2026, "quarter": 1, "content": "q1"},
            {"year": 2025, "quarter": 4, "content": "q4"},
        ]

        haiku_call_count = 0

        async def fake_fetch(*args, **kwargs):
            return (fake_transcripts, None)

        async def fake_complete(**kwargs):
            nonlocal haiku_call_count
            haiku_call_count += 1
            await asyncio.sleep(0.05)  # window for the race
            return '{"axes":{"business_quality":null,"risk_assessment":null,"growth_earnings":null,"sentiment_narrative":null,"management_governance":null,"future_durability":null,"macro_regime":null,"financial_health":null,"valuation_stage":null}}'

        # Stub the DB: SELECTs return cache.get("row"); add() populates the cache.
        cache: dict = {}

        async def fake_execute(q):
            result = MagicMock()
            row = cache.get("row")
            result.scalar_one_or_none = MagicMock(return_value=row)
            scalars_proxy = MagicMock()
            scalars_proxy.all = MagicMock(
                return_value=list(cache.values()) if cache else []
            )
            result.scalars = MagicMock(return_value=scalars_proxy)
            return result

        async def fake_flush():
            return None

        async def fake_delete(obj):
            return None

        db = MagicMock()
        db.execute = fake_execute
        db.flush = fake_flush
        db.delete = fake_delete

        def add_side_effect(row):
            cache["row"] = row

        db.add = MagicMock(side_effect=add_side_effect)

        # Clear any leftover in-flight state from previous tests.
        transcript_delta._IN_FLIGHT.clear()

        with patch.object(transcript_delta, "fetch_recent_transcripts", fake_fetch), \
             patch.object(transcript_delta, "complete", fake_complete):

            async def run_both():
                return await asyncio.gather(
                    transcript_delta.compute_delta(ticker="NVDA", db=db, fmp=MagicMock()),
                    transcript_delta.compute_delta(ticker="NVDA", db=db, fmp=MagicMock()),
                )

            asyncio.run(run_both())

        self.assertEqual(
            haiku_call_count,
            1,
            "Haiku should be called once; second caller awaits the in-flight result",
        )


if __name__ == "__main__":
    unittest.main()
