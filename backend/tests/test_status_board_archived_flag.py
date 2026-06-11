"""Pins that StatusBoardEntry carries archived_at so the frontend can
identify archived rows without a second API call."""

import dataclasses
import os
import unittest
from datetime import datetime, timezone

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.status_board import StatusBoardEntry


class ArchivedAtFieldTests(unittest.TestCase):
    def test_field_exists_on_dataclass(self):
        """archived_at must be a declared field on StatusBoardEntry."""
        field_names = {f.name for f in dataclasses.fields(StatusBoardEntry)}
        self.assertIn("archived_at", field_names)

    def test_constructor_accepts_archived_at_none(self):
        """Default value must be None (optional field)."""
        now = datetime.now(timezone.utc)
        entry = StatusBoardEntry(
            ticker="AAPL",
            theme_id="t1",
            theme_name="Tech",
            run_id="r1",
            thesis_status="CONFIRMED",
            conviction_score=75,
            completed_at=now,
            days_since_update=5,
            health="healthy",
        )
        self.assertIsNone(entry.archived_at)

    def test_constructor_accepts_archived_at_timestamp(self):
        """Must accept a datetime value for archived entries."""
        now = datetime.now(timezone.utc)
        entry = StatusBoardEntry(
            ticker="AAPL",
            theme_id="t1",
            theme_name="Tech",
            run_id="r1",
            thesis_status="CONFIRMED",
            conviction_score=75,
            completed_at=now,
            days_since_update=5,
            health="healthy",
            archived_at=now,
        )
        self.assertEqual(entry.archived_at, now)


if __name__ == "__main__":
    unittest.main()
