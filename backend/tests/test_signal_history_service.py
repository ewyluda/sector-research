"""Pins list_signal_history query shape and ordering."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.signal_history import SignalHistory
from backend.app.services.signal_history import list_signal_history


class ListSignalHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_rows_ordered_oldest_first(self):
        now = datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc)
        rows = [
            SignalHistory(
                ticker="NVDA",
                theme_id="t1",
                signal_type="velocity",
                value={"ratio": 1.0 + i * 0.1},
                computed_at=now - timedelta(days=2 - i),
            )
            for i in range(3)
        ]

        db = MagicMock()
        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = rows
        db.execute = AsyncMock(return_value=result_obj)

        out = await list_signal_history(
            db=db,
            ticker="NVDA",
            theme_id="t1",
            signal_type="velocity",
            days=90,
        )

        self.assertEqual(len(out), 3)
        # Service preserves DB order (oldest first) — sparklines plot left→right.
        self.assertEqual([row.value["ratio"] for row in out], [1.0, 1.1, 1.2])

    async def test_normalizes_ticker_to_upper(self):
        db = MagicMock()
        result_obj = MagicMock()
        result_obj.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_obj)

        await list_signal_history(
            db=db,
            ticker="nvda",
            theme_id="t1",
            signal_type="velocity",
            days=30,
        )

        # The compiled SQL should bind the upper-cased ticker.
        call_stmt = db.execute.call_args[0][0]
        compiled = str(call_stmt.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("NVDA", compiled)
        self.assertNotIn("'nvda'", compiled)


if __name__ == "__main__":
    unittest.main()
