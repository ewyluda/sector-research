"""Tests for WorkspaceService skeleton — SSE event ordering and stream yielding."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.exc import IntegrityError
from backend.app.services.workspace import WorkspaceService
from backend.app.services.workspace import WorkspaceRunInFlight


class TestWorkspaceServiceSkeleton(unittest.IsolatedAsyncioTestCase):
    async def test_preflight_rejects_unsaved_model_draft(self):
        service = WorkspaceService(
            fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        )

        rr = MagicMock()
        rr.id = "rr-1"
        rr.ticker = "NVDA"
        rr.status = "completed"
        tm = MagicMock()
        tm.version = 4
        draft = MagicMock()

        def result(value):
            r = MagicMock()
            r.scalar_one_or_none.return_value = value
            return r

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[result(rr), result(tm), result(draft)])

        with self.assertRaisesRegex(ValueError, "unsaved model draft"):
            await service._preflight(db, "NVDA", research_run_id="rr-1")

    async def test_kick_off_maps_running_unique_violation_to_409_signal(self):
        service = WorkspaceService(
            fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        )
        db = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=db)
        cm.__aexit__ = AsyncMock(
            side_effect=IntegrityError(
                "insert into workspace_runs", {}, Exception("duplicate running ticker")
            )
        )

        rr = MagicMock()
        rr.id = "rr-1"
        tm = MagicMock()
        tm.version = 1

        with patch("backend.app.services.workspace.unit_of_work", return_value=cm), \
             patch.object(service, "_preflight", new=AsyncMock(return_value={
                 "research_run": rr,
                 "ticker_model": tm,
             })), \
             patch.object(
                 service, "_find_in_flight_run_id",
                 new=AsyncMock(return_value="existing-run"),
             ):
            with self.assertRaises(WorkspaceRunInFlight) as ctx:
                await service.kick_off("NVDA")

        self.assertEqual(ctx.exception.run_id, "existing-run")

    async def test_run_emits_start_and_complete(self):
        service = WorkspaceService(
            fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        )

        events: list[dict] = []

        stub_outputs = {
            "update_refresh": {"version_before": 1, "version_after": 2,
                               "changed_cells": [], "new_filings": [],
                               "summary": "stub"},
            "research": {"highlights": [], "new_open_questions": [], "summary": "stub"},
            "validation": {"implied_drivers": [], "implied_irr": None,
                           "sensitivity_grids": [], "thesis_vs_priced_in": [],
                           "current_price": 0.0, "citation_ids": []},
            "challenge": {"stress_test_summary": "stub",
                          "kill_criterion_writes": [], "catalyst_updates": [],
                          "proposed_verdict": "healthy"},
            "differentiation": {"peer_comp": None, "read_throughs": [],
                                 "per_peer_errors": []},
        }

        with patch("backend.app.services.workspace.run_steps_in_sequence",
                   new=AsyncMock(return_value=stub_outputs)):
            run_id = "test-run-1"
            queue = service._get_or_create_queue(run_id)

            async def consume():
                while True:
                    evt = await queue.get()
                    events.append(evt)
                    if evt.get("type") in ("workspace_run_complete", "workspace_run_failed"):
                        return

            consumer = asyncio.create_task(consume())

            # db_factory must return an async context manager (like async_session does)
            mock_db = MagicMock()
            mock_db_cm = MagicMock()
            mock_db_cm.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db_cm.__aexit__ = AsyncMock(return_value=False)
            mock_db_factory = MagicMock(return_value=mock_db_cm)

            # unit_of_work() is used for the final persist; patch it to avoid real DB
            mock_uow_db = MagicMock()
            mock_uow_cm = MagicMock()
            mock_uow_cm.__aenter__ = AsyncMock(return_value=mock_uow_db)
            mock_uow_cm.__aexit__ = AsyncMock(return_value=False)

            with patch.object(service, "_build_context", new=AsyncMock(return_value=MagicMock())), \
                 patch.object(service, "_persist_run", new=AsyncMock()), \
                 patch("backend.app.services.workspace.unit_of_work", return_value=mock_uow_cm):
                await service._run_workspace(
                    run_id=run_id, ticker="NVDA",
                    db_factory=mock_db_factory,
                )

            await asyncio.wait_for(consumer, timeout=2.0)

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "workspace_run_start")
        self.assertEqual(events[-1]["type"], "workspace_run_complete")

    async def test_run_marks_partial_when_a_step_records_error(self):
        service = WorkspaceService(
            fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        )

        # One step recorded an error → final status should be "partial".
        stub_outputs = {
            "update_refresh": {"version_before": 1, "version_after": 2,
                               "changed_cells": [], "new_filings": [],
                               "summary": "stub"},
            "research": {"error": "haiku timed out"},  # ← step-level error
            "validation": {"implied_drivers": [], "implied_irr": None,
                           "sensitivity_grids": [], "thesis_vs_priced_in": [],
                           "current_price": 0.0, "citation_ids": []},
            "challenge": {"stress_test_summary": "stub",
                          "kill_criterion_writes": [], "catalyst_updates": [],
                          "proposed_verdict": "healthy"},
            "differentiation": {"peer_comp": None, "read_throughs": [],
                                 "per_peer_errors": []},
        }

        persist_calls: list[dict] = []

        async def fake_persist(*_args, **kwargs):
            persist_calls.append(kwargs)

        with patch("backend.app.services.workspace.run_steps_in_sequence",
                   new=AsyncMock(return_value=stub_outputs)):
            run_id = "test-run-partial"
            mock_db = MagicMock()
            mock_db_cm = MagicMock()
            mock_db_cm.__aenter__ = AsyncMock(return_value=mock_db)
            mock_db_cm.__aexit__ = AsyncMock(return_value=False)
            mock_db_factory = MagicMock(return_value=mock_db_cm)

            mock_uow_db = MagicMock()
            mock_uow_cm = MagicMock()
            mock_uow_cm.__aenter__ = AsyncMock(return_value=mock_uow_db)
            mock_uow_cm.__aexit__ = AsyncMock(return_value=False)

            with patch.object(service, "_build_context", new=AsyncMock(return_value=MagicMock())), \
                 patch.object(service, "_persist_run", new=AsyncMock(side_effect=fake_persist)), \
                 patch("backend.app.services.workspace.unit_of_work", return_value=mock_uow_cm):
                await service._run_workspace(
                    run_id=run_id, ticker="NVDA",
                    db_factory=mock_db_factory,
                )

        self.assertEqual(len(persist_calls), 1)
        self.assertEqual(persist_calls[0]["status"], "partial")

    async def test_event_stream_yields_until_complete(self):
        service = WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())
        run_id = "stream-test"
        service._emit(run_id, {"type": "step_start", "step": "update_refresh"})
        service._emit(run_id, {"type": "workspace_run_complete", "verdict": "healthy", "version_after": 2})

        collected: list[dict] = []
        async for evt in service.event_stream(run_id):
            collected.append(evt)

        types = [e["type"] for e in collected]
        self.assertIn("step_start", types)
        self.assertIn("workspace_run_complete", types)
