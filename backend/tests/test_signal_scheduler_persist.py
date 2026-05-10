"""Pins _persist_signal_set semantics: delete-old-signal then add-new-signal,
once per signal_type, all on the same `now` timestamp."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.signal import Signal
from backend.app.services.signal_scheduler import _persist_signal_set


class PersistSignalSetTests(unittest.IsolatedAsyncioTestCase):
    async def test_writes_one_signal_per_signal_type_with_shared_timestamp(self):
        added: list[object] = []
        deletes: list[object] = []

        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)

        async def fake_execute(stmt):
            deletes.append(stmt)
            return MagicMock()

        db.execute = AsyncMock(side_effect=fake_execute)

        now = datetime(2026, 5, 9, 2, 0, tzinfo=timezone.utc)
        results = {
            "velocity": {"ratio": 1.4, "direction": "accelerating"},
            "narrative": {"summary": "x"},
            "discovery": {"score": 0.05},
        }

        await _persist_signal_set(
            db=db,
            ticker="NVDA",
            theme_id="00000000-0000-0000-0000-000000000001",
            results=results,
            computed_at=now,
        )

        self.assertEqual(len(deletes), 3)
        signals = [obj for obj in added if isinstance(obj, Signal)]
        self.assertEqual(len(signals), 3)
        self.assertEqual({s.signal_type for s in signals}, {"velocity", "narrative", "discovery"})
        self.assertTrue(all(s.computed_at == now for s in signals))
        self.assertTrue(all(s.ticker == "NVDA" for s in signals))


if __name__ == "__main__":
    unittest.main()
