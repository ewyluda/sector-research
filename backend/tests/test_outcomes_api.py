"""Tests for backend.app.api.outcomes."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from uuid import uuid4

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


class TestGetBySource(unittest.TestCase):
    def test_get_by_source_returns_outcome(self):
        from backend.app.main import app

        source_id = str(uuid4())
        outcome_payload = {
            "id": str(uuid4()),
            "source_type": "workspace_run",
            "source_id": source_id,
            "ticker": "NVDA",
            "theme_id": None,
            "verdict": "healthy",
            "verdict_emitted_at": "2026-01-02T22:00:00+00:00",
            "entry_price_at": "2026-01-05",
            "entry_price": "850.00",
            "sector_etf_ticker": None,
            "superseded_at": None,
            "closed_at": None,
            "realized_ticker_return_pct": None,
            "realized_spy_excess_pct": None,
            "realized_sector_excess_pct": None,
            "realized_theme_basket_excess_pct": None,
            "snapshots": [],
            "theme_basket_constituents": None,
            "signal_snapshot": None,
        }

        with patch(
            "backend.app.api.outcomes._get_outcome_by_source",
            new=AsyncMock(return_value=outcome_payload),
        ):
            client = TestClient(app)
            r = client.get(f"/api/outcomes/by-source/workspace_run/{source_id}")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")

    def test_get_by_source_404_when_missing(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._get_outcome_by_source",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app)
            r = client.get(f"/api/outcomes/by-source/research_run/{uuid4()}")
            self.assertEqual(r.status_code, 404)


class TestListOutcomes(unittest.TestCase):
    def test_list_returns_200_empty(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._query_outcomes",
            new=AsyncMock(return_value=[]),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), [])

    def test_list_with_filters_passes_through(self):
        from backend.app.main import app

        source_id = str(uuid4())
        payload = {
            "id": str(uuid4()),
            "source_type": "research_run",
            "source_id": source_id,
            "ticker": "MSFT",
            "theme_id": None,
            "verdict": "completed",
            "verdict_emitted_at": "2026-02-01T10:00:00+00:00",
            "entry_price_at": "2026-02-03",
            "entry_price": "400.00",
            "sector_etf_ticker": "XLK",
            "superseded_at": None,
            "closed_at": None,
            "realized_ticker_return_pct": None,
            "realized_spy_excess_pct": None,
            "realized_sector_excess_pct": None,
            "realized_theme_basket_excess_pct": None,
            "snapshots": [],
            "theme_basket_constituents": None,
            "signal_snapshot": None,
        }

        with patch(
            "backend.app.api.outcomes._query_outcomes",
            new=AsyncMock(return_value=[payload]),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes?verdict=completed&source_type=research_run&limit=50")
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["ticker"], "MSFT")


if __name__ == "__main__":
    unittest.main()
