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


class TestPreflightModelRelaxation(unittest.TestCase):
    """no_ticker_model must be a warning, not a blocker."""

    def _make_service(self):
        return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())

    def _facts(self, **overrides):
        base = {
            "research_run_found": True,
            "research_run_completed": True,
            "research_run_ticker_matches": True,
            "ticker_model_found": False,
            "draft_present": False,
            "in_flight_run_id": None,
            "research_run": object(),
            "ticker_model": None,
        }
        base.update(overrides)
        return base

    def test_no_ticker_model_is_warning_not_blocker(self):
        """ticker_model_found=False with all else fine → ok=True, warnings=['no_ticker_model']."""
        svc = self._make_service()
        facts = self._facts()  # ticker_model_found=False by default

        async def fake_gather(db, ticker, research_run_id=None):
            return facts

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertTrue(result.ok)
        self.assertEqual(result.missing, [])
        self.assertEqual(result.warnings, ["no_ticker_model"])

    def test_preflight_does_not_raise_on_missing_model(self):
        """_preflight with ticker_model_found=False must return dict with ticker_model=None."""
        svc = self._make_service()
        facts = self._facts()

        async def fake_gather(db, ticker, research_run_id=None):
            return facts

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]

        async def run():
            return await svc._preflight(db=MagicMock(), ticker="NVDA")

        result = asyncio.run(run())
        self.assertIsNone(result["ticker_model"])

    def test_unsaved_draft_still_blocks(self):
        """draft_present=True must still produce ok=False with 'unsaved_model_draft' in missing."""
        svc = self._make_service()
        facts = self._facts(draft_present=True)

        async def fake_gather(db, ticker, research_run_id=None):
            return facts

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("unsaved_model_draft", result.missing)

    def test_no_warnings_when_model_present(self):
        """ticker_model_found=True → warnings == []."""
        svc = self._make_service()
        facts = self._facts(ticker_model_found=True, ticker_model=object())

        async def fake_gather(db, ticker, research_run_id=None):
            return facts

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertEqual(result.warnings, [])


class TestKickOffModellessRun(unittest.TestCase):
    """kick_off must not crash and must write version_before=0 when no model exists."""

    def _make_service(self):
        return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())

    def test_kick_off_sets_version_before_zero_when_no_model(self):
        """_preflight returning ticker_model=None must produce version_before=0 on the run row."""
        import backend.app.services.workspace as ws_mod
        from unittest.mock import AsyncMock, patch

        svc = self._make_service()

        # Fake research_run with just enough attrs for kick_off to proceed.
        fake_rr = MagicMock()
        fake_rr.id = "rr-001"

        # _preflight returns None for ticker_model — the scenario under test.
        async def fake_preflight(db, ticker, research_run_id=None):
            return {"research_run": fake_rr, "ticker_model": None}

        svc._preflight = fake_preflight  # type: ignore[assignment]

        captured_rows: list = []

        # Minimal async DB session: execute returns a result with no in-flight row,
        # add() captures the WorkspaceRun so we can inspect it.
        mock_db = MagicMock()
        mock_db.add = lambda row: captured_rows.append(row)
        no_row_result = MagicMock()
        no_row_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=no_row_result)

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_uow():
            yield mock_db

        async def run():
            with patch.object(ws_mod, "unit_of_work", fake_uow):
                # Patch asyncio.create_task so the background _run_workspace
                # never fires (it would fail without a real DB).
                with patch("asyncio.create_task", side_effect=lambda coro: coro.close()):
                    return await svc.kick_off("NVDA")

        asyncio.run(run())

        self.assertEqual(len(captured_rows), 1)
        row = captured_rows[0]
        self.assertEqual(row.ticker_model_version_before, 0,
                         "version_before must be 0 when no model exists at kick-off")


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
