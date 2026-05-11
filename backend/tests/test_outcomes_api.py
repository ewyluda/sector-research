"""Tests for backend.app.api.outcomes."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestBackfillEndpoint(unittest.TestCase):
    def test_post_backfill_returns_202(self):
        from backend.app.main import app

        mock_summary = MagicMock()
        mock_summary.outcomes_created = 3
        mock_summary.outcomes_existed = 10
        mock_summary.snapshots_inserted = 8
        mock_summary.errors = []
        mock_summary.model_dump = lambda: {
            "outcomes_created": 3,
            "outcomes_existed": 10,
            "snapshots_inserted": 8,
            "errors": [],
        }

        app.state.fmp = MagicMock()
        with patch(
            "backend.app.api.outcomes.outcome_tracker.backfill_from_history",
            new=AsyncMock(return_value=mock_summary),
        ):
            client = TestClient(app)
            r = client.post("/api/outcomes/backfill")
            self.assertEqual(r.status_code, 202)
            body = r.json()
            self.assertEqual(body["outcomes_created"], 3)


if __name__ == "__main__":
    unittest.main()
