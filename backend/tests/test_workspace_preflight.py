"""Tests for WorkspaceService.check_preflight() — non-raising preflight DTO."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.workspace import WorkspaceService, PreflightStatus


class TestCheckPreflight(unittest.TestCase):
    def _make_service(self):
        return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())

    def test_returns_ok_when_all_prereqs_met(self):
        # Stub the underlying DB-touching helper used by check_preflight().
        # We do this at the service level — replace _gather_preflight_facts to
        # return the shape check_preflight maps from.
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]

        async def run():
            return await svc.check_preflight(db=MagicMock(), ticker="NVDA")

        result = asyncio.run(run())
        self.assertIsInstance(result, PreflightStatus)
        self.assertTrue(result.ok)
        self.assertEqual(result.missing, [])
        self.assertIsNone(result.in_flight_run_id)

    def test_reports_missing_research_run(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": False,
                "research_run_completed": False,
                "research_run_ticker_matches": False,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("no_completed_research_run", result.missing)

    def test_reports_unsaved_draft(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": True,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("unsaved_model_draft", result.missing)

    def test_reports_in_flight_run(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": "abc-123",
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("workspace_run_in_flight", result.missing)
        self.assertEqual(result.in_flight_run_id, "abc-123")


if __name__ == "__main__":
    unittest.main()
