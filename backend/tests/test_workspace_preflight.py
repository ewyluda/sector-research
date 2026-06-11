"""Tests for WorkspaceService.check_preflight() — non-raising preflight DTO."""
import asyncio
import unittest
from unittest.mock import MagicMock

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


class TestKickOffRaceGuard(unittest.TestCase):
    def test_concurrent_kick_offs_serialize_on_ticker_lock(self):
        """Two parallel kick_off() calls for the same ticker must not both pass preflight.

        We stub _preflight to record entry order and sleep, then assert the
        lock forces serial execution.
        """
        from backend.app.services.workspace import WorkspaceService
        svc = WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())
        entries: list[str] = []

        # Replace the run-lifecycle internals so we only test the lock.
        async def fake_kick(ticker: str, tag: str):
            async with svc._acquire_ticker_lock(ticker):
                entries.append(f"enter:{tag}")
                await asyncio.sleep(0.05)
                entries.append(f"exit:{tag}")

        async def run():
            await asyncio.gather(fake_kick("NVDA", "a"), fake_kick("NVDA", "b"))

        asyncio.run(run())
        # Either a fully before b or b fully before a — never interleaved.
        ordering = ",".join(entries)
        self.assertIn(ordering, {"enter:a,exit:a,enter:b,exit:b", "enter:b,exit:b,enter:a,exit:a"})

    def test_different_tickers_do_not_block(self):
        from backend.app.services.workspace import WorkspaceService
        svc = WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())
        entries: list[str] = []

        async def fake_kick(ticker: str, tag: str):
            async with svc._acquire_ticker_lock(ticker):
                entries.append(f"enter:{tag}")
                await asyncio.sleep(0.05)
                entries.append(f"exit:{tag}")

        async def run():
            await asyncio.gather(fake_kick("NVDA", "a"), fake_kick("AAPL", "b"))

        asyncio.run(run())
        # Both enters happen before either exit.
        idx_enter_a = entries.index("enter:a")
        idx_enter_b = entries.index("enter:b")
        idx_exit_a = entries.index("exit:a")
        idx_exit_b = entries.index("exit:b")
        self.assertLess(max(idx_enter_a, idx_enter_b), min(idx_exit_a, idx_exit_b))


if __name__ == "__main__":
    unittest.main()
