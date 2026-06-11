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

    def test_list_accepts_nested_dict_signal_snapshot(self):
        """Regression: signal_snapshot.signals_row holds CompanySignalCard sub-dicts
        (velocity/discovery/narrative/fundamental), not scalars. Pre-fix the schema
        declared dict[str, float | None] which rejected every persisted row with a
        ResponseValidationError → 500."""
        from backend.app.main import app

        nested_signal_snapshot = {
            "signals_row": {
                "velocity": {
                    "ratio": 1.0,
                    "count_7d": 99,
                    "direction": "stable",
                    "count_30d_approx": 396,
                },
                "discovery": {
                    "score": 1.0206,
                    "is_seed": True,
                    "raw_score": 1.0206,
                    "boost_applied": 1.0,
                },
                "narrative": {
                    "summary": None,
                    "post_count": 50,
                    "post_texts": ["sample post text"],
                },
                "fundamental": {"score": 0.85},
            },
            "deep_dive_scores": {"business_quality": 92, "growth_earnings": 88},
            "workspace_step_verdicts": {"update_refresh": "healthy"},
            "kill_criterion_state": [
                {"ordinal": 1, "armed": True, "triggered": False, "label": "PE > 50"},
            ],
            "model_assumptions": {"discount_rate": 0.09, "terminal_multiple": 12.0},
        }

        payload = {
            "id": str(uuid4()),
            "source_type": "research_run",
            "source_id": str(uuid4()),
            "ticker": "NVDA",
            "theme_id": None,
            "verdict": "completed",
            "verdict_emitted_at": "2026-04-15T10:00:00+00:00",
            "entry_price_at": "2026-04-16",
            "entry_price": "850.00",
            "sector_etf_ticker": "XLK",
            "superseded_at": None,
            "closed_at": None,
            "realized_ticker_return_pct": None,
            "realized_spy_excess_pct": None,
            "realized_sector_excess_pct": None,
            "realized_theme_basket_excess_pct": None,
            "snapshots": [],
            "theme_basket_constituents": None,
            "signal_snapshot": nested_signal_snapshot,
        }

        with patch(
            "backend.app.api.outcomes._query_outcomes",
            new=AsyncMock(return_value=[payload]),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes?limit=10")
            self.assertEqual(r.status_code, 200, msg=r.text)
            data = r.json()
            self.assertEqual(len(data), 1)
            # signal_snapshot should round-trip with nested dicts intact
            sigs = data[0]["signal_snapshot"]["signals_row"]
            self.assertEqual(sigs["velocity"]["count_7d"], 99)
            self.assertEqual(sigs["narrative"]["post_count"], 50)


class TestSummary(unittest.TestCase):
    def _empty_summary(self, **overrides) -> dict:
        base = {
            "window": "90d", "snapshot_offset": "3m", "benchmark": "spy", "source_type": "all",
            "overall": {"n": 0, "mean_return_pct": None, "mean_excess_pct": None,
                        "win_rate": None, "median_excess_pct": None},
            "by_verdict": {},
            "by_theme": [],
            "by_signal_bucket": {},
            "populated_offsets": [],
        }
        base.update(overrides)
        return base

    def test_summary_empty_window_returns_zero_filled(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._compute_summary",
            new=AsyncMock(return_value=self._empty_summary()),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["overall"]["n"], 0)

    def test_summary_filters_pass_through(self):
        from backend.app.main import app

        captured = {}

        async def _stub(*, theme_id, window, snapshot_offset, benchmark, source_type, db):
            captured.update({
                "theme_id": theme_id, "window": window, "snapshot_offset": snapshot_offset,
                "benchmark": benchmark, "source_type": source_type,
            })
            return {
                "window": window, "snapshot_offset": snapshot_offset, "benchmark": benchmark,
                "source_type": source_type,
                "overall": {"n": 0, "mean_return_pct": None, "mean_excess_pct": None,
                            "win_rate": None, "median_excess_pct": None},
                "by_verdict": {}, "by_theme": [], "by_signal_bucket": {},
                "populated_offsets": [],
            }

        with patch("backend.app.api.outcomes._compute_summary", new=_stub):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary?window=30d&snapshot_offset=1m&benchmark=sector&source_type=workspace_run&theme_id=abc")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(captured["window"], "30d")
            self.assertEqual(captured["benchmark"], "sector")
            self.assertEqual(captured["source_type"], "workspace_run")

    def test_populated_offsets_present_in_response(self):
        """populated_offsets is serialized in the summary response."""
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._compute_summary",
            new=AsyncMock(return_value=self._empty_summary(populated_offsets=["1d", "1w"])),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["populated_offsets"], ["1d", "1w"])

    def test_populated_offsets_empty_when_no_snapshots(self):
        """populated_offsets is [] when there are no snapshot rows at all."""
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._compute_summary",
            new=AsyncMock(return_value=self._empty_summary(populated_offsets=[])),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["populated_offsets"], [])


class TestComputeSummaryPopulatedOffsets(unittest.TestCase):
    """Unit tests for the _compute_summary populated_offsets logic.

    Uses MagicMock stubs for the DB session — no real database required.
    _compute_summary issues three async execute() calls in order:
      1. distinct offset query → scalars().all() returns the simulated offset list
      2. main rollup query → all() returns []
      3. per-theme rollup query → all() returns []
    """

    def test_populated_offsets_subset_returned(self):
        """Mock DB returns ['1d', '1w'] from the distinct query → same list in result."""
        from unittest.mock import AsyncMock, MagicMock

        # Simulate the distinct() query returning {"1d", "1w"}
        mock_db = MagicMock()
        pop_result = MagicMock()
        pop_result.scalars.return_value.all.return_value = ["1d", "1w"]

        main_result = MagicMock()
        main_result.all.return_value = []

        theme_result = MagicMock()
        theme_result.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[pop_result, main_result, theme_result])

        import asyncio
        from backend.app.api.outcomes import _compute_summary

        result = asyncio.run(_compute_summary(
            theme_id=None,
            window="all",
            snapshot_offset="1d",
            benchmark="spy",
            source_type="all",
            db=mock_db,
        ))

        # Order preserved: 1d before 1w (following _ALL_OFFSETS order)
        self.assertEqual(result["populated_offsets"], ["1d", "1w"])

    def test_populated_offsets_empty_when_no_snapshots(self):
        """Mock DB returns [] from the distinct query → populated_offsets = []."""
        from unittest.mock import AsyncMock, MagicMock

        mock_db = MagicMock()
        pop_result = MagicMock()
        pop_result.scalars.return_value.all.return_value = []

        main_result = MagicMock()
        main_result.all.return_value = []

        # No theme-lookup query: distinct_ids is empty when main_result is empty.
        mock_db.execute = AsyncMock(side_effect=[pop_result, main_result])

        import asyncio
        from backend.app.api.outcomes import _compute_summary

        result = asyncio.run(_compute_summary(
            theme_id=None,
            window="all",
            snapshot_offset="1d",
            benchmark="spy",
            source_type="all",
            db=mock_db,
        ))

        self.assertEqual(result["populated_offsets"], [])


class TestQuartileBuckets(unittest.TestCase):
    def test_quartile_buckets_balanced(self):
        from backend.app.api.outcomes import _quartile_buckets
        # 8 outcomes with signal 1..8 and excess matching signal
        values = [(float(i), float(i)) for i in range(1, 9)]
        buckets = _quartile_buckets(values)
        by_key = {b.bucket: b for b in buckets}
        self.assertEqual(by_key["0-25th"].n, 2)
        self.assertEqual(by_key["25-50th"].n, 2)
        self.assertEqual(by_key["50-75th"].n, 2)
        self.assertEqual(by_key["75-100th"].n, 2)
        self.assertGreater(by_key["75-100th"].mean_excess_pct, by_key["0-25th"].mean_excess_pct)

    def test_quartile_buckets_includes_null(self):
        from backend.app.api.outcomes import _quartile_buckets
        values = [(None, 5.0), (1.0, 0.0), (2.0, 1.0)]
        buckets = _quartile_buckets(values)
        by_key = {b.bucket: b for b in buckets}
        self.assertEqual(by_key["null"].n, 1)


if __name__ == "__main__":
    unittest.main()
