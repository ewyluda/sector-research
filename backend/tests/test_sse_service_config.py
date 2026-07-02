"""Pins each service's EventBroker configuration plus one integration
behavior per service. Broker mechanics are unit-tested in
test_event_broker.py; these tests exist so a config change (terminal types,
replay policy, heartbeat) fails loudly.

Grows across the migration: pipeline (Task 2), workspace (Task 3),
prospectus (Task 4).
"""

import asyncio
import os
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.pipeline import PipelineService
from backend.app.services.prospectus_service import ProspectusService
from backend.app.services.workspace import WorkspaceService


def _make_pipeline() -> PipelineService:
    return PipelineService(fmp=MagicMock(), fred=MagicMock(), edgar=MagicMock())


class TestPipelineBrokerConfig(unittest.IsolatedAsyncioTestCase):
    def test_broker_configuration(self):
        svc = _make_pipeline()
        self.assertEqual(svc._broker.terminal_types, frozenset({"complete", "error"}))
        self.assertFalse(svc._broker.replay)          # REST hydration covers the connect window
        self.assertEqual(svc._broker.heartbeat_seconds, 30.0)
        self.assertEqual(svc._broker.queue_maxsize, 500)

    async def test_event_stream_two_concurrent_consumers_receive_sse_strings(self):
        svc = _make_pipeline()
        run_id = "run-e"
        received_1: list[str] = []
        received_2: list[str] = []

        async def consumer(collected: list[str]):
            async for line in svc.event_stream(run_id):
                collected.append(line)

        t1 = asyncio.create_task(consumer(received_1))
        t2 = asyncio.create_task(consumer(received_2))
        await asyncio.sleep(0)  # both consumers register

        svc._emit(run_id, {"type": "phase_start", "phase": "quick_screen"})
        svc._emit(run_id, {"type": "complete", "status": "completed"})

        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
        for received in (received_1, received_2):
            self.assertEqual(len(received), 2)
            self.assertTrue(received[0].startswith('data: {"type": "phase_start"'))
            self.assertTrue(received[1].startswith('data: {"type": "complete"'))
        # No stray subscriber state after terminal close
        self.assertNotIn(run_id, svc._broker._queues)


def _make_workspace() -> WorkspaceService:
    return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())


class TestWorkspaceBrokerConfig(unittest.IsolatedAsyncioTestCase):
    def test_broker_configuration(self):
        svc = _make_workspace()
        self.assertEqual(
            svc._broker.terminal_types,
            frozenset({"workspace_run_complete", "workspace_run_failed"}),
        )
        self.assertTrue(svc._broker.replay)
        self.assertIsNone(svc._broker.heartbeat_seconds)
        self.assertEqual(svc._broker.queue_maxsize, 500)

    async def test_replay_delivers_pre_subscribe_events_to_late_subscriber(self):
        svc = _make_workspace()
        run_id = "ws-a"
        # kick_off emits before the frontend connects — the load-bearing case
        svc._emit(run_id, {"type": "workspace_run_start"})
        svc._emit(run_id, {"type": "step_start", "step": "update_refresh"})
        svc._emit(run_id, {"type": "workspace_run_complete", "verdict": "healthy", "version_after": 1})

        collected: list[dict] = []
        async for evt in svc.event_stream(run_id):
            collected.append(evt)

        self.assertEqual(
            [e["type"] for e in collected],
            ["workspace_run_start", "step_start", "workspace_run_complete"],
        )
        self.assertEqual(svc._broker._queues.get(run_id, []), [])


def _make_prospectus() -> ProspectusService:
    return ProspectusService(edgar=MagicMock())


class TestProspectusBrokerConfig(unittest.IsolatedAsyncioTestCase):
    def test_broker_configuration(self):
        svc = _make_prospectus()
        self.assertEqual(
            svc._broker.terminal_types,
            frozenset({"prospectus_complete", "prospectus_failed"}),
        )
        self.assertTrue(svc._broker.replay)
        self.assertIsNone(svc._broker.heartbeat_seconds)
        self.assertEqual(svc._broker.queue_maxsize, 500)

    async def test_late_subscriber_after_terminal_gets_replay_and_exits(self):
        svc = _make_prospectus()
        rid = "pr-c"
        svc._emit(rid, {"type": "step_start", "step": "ingest"})
        svc._emit(rid, {"type": "prospectus_complete", "report_id": rid})

        collected: list[dict] = []
        async for evt in svc.event_stream(rid):
            collected.append(evt)

        self.assertEqual([e["type"] for e in collected], ["step_start", "prospectus_complete"])
        self.assertEqual(svc._broker._queues.get(rid, []), [])


if __name__ == "__main__":
    unittest.main()
