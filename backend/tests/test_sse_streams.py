"""Tests for SSE multi-subscriber fan-out in PipelineService, WorkspaceService,
and ProspectusService.

Acceptance criteria (M1.4):
  Pipeline:
    1. Two subscribers both receive an emitted event.
    2. Unsubscribing one queue leaves the other receiving events; dict entry
       cleaned up when the last subscriber unsubscribes.
    3. Emit with zero subscribers is a no-op (no error, event dropped).
    4. A full-queue subscriber does not prevent delivery to the other.
  Workspace:
    5. Events emitted before any subscriber are replayed to a late subscriber,
       then live events follow.
    6. Two concurrent event_stream consumers each receive ALL events including
       the terminal one.
    7. A subscriber connecting after the terminal event was emitted gets the
       full replay and terminates.
  Prospectus (A2 parity):
    8. Two concurrent consumers each receive ALL events including the terminal one.
    9. Events emitted before any subscriber are replayed to a late subscriber.
   10. Subscriber connecting after the terminal event gets the full replay and exits.
   11. Cancellation cleanup removes the subscriber queue from the internal dict.
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


def _make_workspace() -> WorkspaceService:
    return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())


def _make_prospectus() -> ProspectusService:
    return ProspectusService(edgar=MagicMock())


class TestPipelineSSE(unittest.IsolatedAsyncioTestCase):
    # ── 1. Two subscribers both receive an emitted event ──────────────────────

    async def test_two_subscribers_both_receive_event(self):
        svc = _make_pipeline()
        run_id = "run-a"
        q1 = svc.subscribe(run_id)
        q2 = svc.subscribe(run_id)

        svc._emit(run_id, {"type": "phase_start", "phase": "quick_screen"})

        evt1 = q1.get_nowait()
        evt2 = q2.get_nowait()
        self.assertEqual(evt1["type"], "phase_start")
        self.assertEqual(evt2["type"], "phase_start")

    # ── 2. Unsubscribing one leaves the other; dict cleaned up when empty ─────

    async def test_unsubscribe_one_leaves_other_active(self):
        svc = _make_pipeline()
        run_id = "run-b"
        q1 = svc.subscribe(run_id)
        q2 = svc.subscribe(run_id)

        svc.unsubscribe(run_id, q1)
        # q1 should no longer be in the list
        self.assertNotIn(q1, svc._streams.get(run_id, []))
        # q2 still present
        self.assertIn(q2, svc._streams[run_id])

        svc._emit(run_id, {"type": "heartbeat"})
        evt = q2.get_nowait()
        self.assertEqual(evt["type"], "heartbeat")
        # q1's queue is empty
        self.assertTrue(q1.empty())

    async def test_last_unsubscribe_removes_dict_entry(self):
        svc = _make_pipeline()
        run_id = "run-c"
        q = svc.subscribe(run_id)
        self.assertIn(run_id, svc._streams)

        svc.unsubscribe(run_id, q)
        self.assertNotIn(run_id, svc._streams)

    # ── 3. Emit with zero subscribers is a no-op ──────────────────────────────

    async def test_emit_no_subscribers_is_noop(self):
        svc = _make_pipeline()
        # Should not raise
        svc._emit("nonexistent-run", {"type": "complete"})

    # ── 4. Full-queue subscriber does not block the other ─────────────────────

    async def test_full_queue_does_not_block_other_subscriber(self):
        svc = _make_pipeline()
        run_id = "run-d"
        q_full = svc.subscribe(run_id)
        q_ok = svc.subscribe(run_id)

        # Fill q_full to capacity
        for _ in range(500):
            q_full.put_nowait({"type": "filler"})

        # Emit one more — q_full is full, but q_ok should still receive it
        svc._emit(run_id, {"type": "phase_start", "phase": "deep_dive"})

        # q_ok received it
        evt = q_ok.get_nowait()
        self.assertEqual(evt["type"], "phase_start")
        # q_full is still at capacity (last event was dropped, no error raised)
        self.assertEqual(q_full.qsize(), 500)

    # ── event_stream integration: two tabs stream same run independently ──────

    async def test_event_stream_two_concurrent_consumers(self):
        svc = _make_pipeline()
        run_id = "run-e"

        received_1: list[str] = []
        received_2: list[str] = []

        async def consumer(collected: list[str]):
            async for line in svc.event_stream(run_id):
                collected.append(line)

        t1 = asyncio.create_task(consumer(received_1))
        t2 = asyncio.create_task(consumer(received_2))
        # Yield so both tasks enter event_stream and subscribe
        await asyncio.sleep(0)

        svc._emit(run_id, {"type": "phase_start", "phase": "quick_screen"})
        svc._emit(run_id, {"type": "complete", "status": "completed"})

        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)

        # Both consumers saw both events
        self.assertEqual(len(received_1), 2)
        self.assertEqual(len(received_2), 2)
        # Neither left a stray entry in _streams after termination
        self.assertNotIn(run_id, svc._streams)


class TestWorkspaceSSE(unittest.IsolatedAsyncioTestCase):
    # ── 5. Pre-subscribe events are replayed to a late subscriber ─────────────

    async def test_replay_buffer_delivers_events_to_late_subscriber(self):
        svc = _make_workspace()
        run_id = "ws-a"

        # Events emitted before any subscriber exists
        svc._emit(run_id, {"type": "workspace_run_start"})
        svc._emit(run_id, {"type": "step_start", "step": "update_refresh"})

        collected: list[dict] = []
        async def consume_two():
            async for evt in svc.event_stream(run_id):
                collected.append(evt)
                if len(collected) >= 2:
                    return  # stop after replayed events (no terminal yet)

        await asyncio.wait_for(consume_two(), timeout=2.0)
        self.assertEqual(collected[0]["type"], "workspace_run_start")
        self.assertEqual(collected[1]["type"], "step_start")

    # ── 6. Two concurrent consumers each receive ALL events incl. terminal ────

    async def test_two_concurrent_consumers_each_receive_all_events(self):
        svc = _make_workspace()
        run_id = "ws-b"

        received_a: list[dict] = []
        received_b: list[dict] = []

        async def consume(collected: list[dict]):
            async for evt in svc.event_stream(run_id):
                collected.append(evt)

        t_a = asyncio.create_task(consume(received_a))
        t_b = asyncio.create_task(consume(received_b))
        # Let both tasks enter event_stream and subscribe
        await asyncio.sleep(0)

        svc._emit(run_id, {"type": "step_start", "step": "research"})
        svc._emit(run_id, {"type": "workspace_run_complete", "verdict": "healthy", "version_after": 2})

        await asyncio.wait_for(asyncio.gather(t_a, t_b), timeout=2.0)

        for received in (received_a, received_b):
            types = [e["type"] for e in received]
            self.assertIn("step_start", types)
            self.assertIn("workspace_run_complete", types)

    # ── 7. Subscriber after terminal gets full replay and terminates ──────────

    async def test_late_subscriber_after_terminal_gets_replay_and_exits(self):
        svc = _make_workspace()
        run_id = "ws-c"

        # Emit all events including terminal before any subscriber
        svc._emit(run_id, {"type": "workspace_run_start"})
        svc._emit(run_id, {"type": "step_start", "step": "update_refresh"})
        svc._emit(run_id, {"type": "workspace_run_complete", "verdict": "healthy", "version_after": 1})

        collected: list[dict] = []
        async for evt in svc.event_stream(run_id):
            collected.append(evt)

        # Should have received the full replay and terminated
        types = [e["type"] for e in collected]
        self.assertEqual(types[0], "workspace_run_start")
        self.assertIn("workspace_run_complete", types)
        # Subscriber cleaned up after exit
        self.assertEqual(svc._queues.get(run_id, []), [])


class TestProspectusSSE(unittest.IsolatedAsyncioTestCase):
    # ── 8. Two concurrent consumers each receive ALL events incl. terminal ────

    async def test_two_concurrent_consumers_each_receive_all_events(self):
        svc = _make_prospectus()
        rid = "pr-a"

        received_a: list[dict] = []
        received_b: list[dict] = []

        async def consume(collected: list[dict]):
            async for evt in svc.event_stream(rid):
                collected.append(evt)

        t_a = asyncio.create_task(consume(received_a))
        t_b = asyncio.create_task(consume(received_b))
        # Let both tasks enter event_stream and subscribe
        await asyncio.sleep(0)

        svc._emit(rid, {"type": "step_start", "step": "ingest"})
        svc._emit(rid, {"type": "prospectus_complete", "report_id": rid})

        await asyncio.wait_for(asyncio.gather(t_a, t_b), timeout=2.0)

        for received in (received_a, received_b):
            types = [e["type"] for e in received]
            self.assertIn("step_start", types)
            self.assertIn("prospectus_complete", types)

    # ── 9. Pre-subscribe events are replayed to a late subscriber ─────────────

    async def test_replay_buffer_delivers_events_to_late_subscriber(self):
        svc = _make_prospectus()
        rid = "pr-b"

        # Events emitted before any subscriber exists
        svc._emit(rid, {"type": "step_start", "step": "ingest"})
        svc._emit(rid, {"type": "step_complete", "step": "ingest"})

        collected: list[dict] = []

        async def consume_two():
            async for evt in svc.event_stream(rid):
                collected.append(evt)
                if len(collected) >= 2:
                    return  # stop after replayed events (no terminal yet)

        await asyncio.wait_for(consume_two(), timeout=2.0)
        self.assertEqual(collected[0]["type"], "step_start")
        self.assertEqual(collected[1]["type"], "step_complete")

    # ── 10. Late subscriber after terminal gets full replay and exits ─────────

    async def test_late_subscriber_after_terminal_gets_replay_and_exits(self):
        svc = _make_prospectus()
        rid = "pr-c"

        # Emit all events including terminal before any subscriber
        svc._emit(rid, {"type": "step_start", "step": "ingest"})
        svc._emit(rid, {"type": "prospectus_complete", "report_id": rid})

        collected: list[dict] = []
        async for evt in svc.event_stream(rid):
            collected.append(evt)

        types = [e["type"] for e in collected]
        self.assertEqual(types[0], "step_start")
        self.assertIn("prospectus_complete", types)
        # Subscriber cleaned up after exit
        self.assertEqual(svc._queues.get(rid, []), [])

    # ── 11. Cancellation removes subscriber queue ─────────────────────────────

    async def test_cancelled_consumer_removes_subscriber(self):
        import contextlib
        svc = _make_prospectus()
        rid = "pr-cancel"

        async def consume():
            async for _evt in svc.event_stream(rid):
                pass

        task = asyncio.create_task(consume())
        # Yield so the task enters event_stream, snapshots the (empty) replay
        # buffer, and registers its queue before blocking on queue.get().
        await asyncio.sleep(0)
        self.assertIn(rid, svc._queues)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # The generator's finally block must have run and cleaned up.
        self.assertNotIn(rid, svc._queues)


class TestCancellationCleanup(unittest.IsolatedAsyncioTestCase):
    """Pinning that client disconnect (CancelledError through the generator's
    finally) removes the subscriber queue from the service's internal dict."""

    # ── Pipeline cancellation ─────────────────────────────────────────────────

    async def test_pipeline_cancelled_consumer_removes_subscriber(self):
        """Cancelling a task consuming pipeline event_stream removes subscriber queue."""
        import contextlib
        svc = _make_pipeline()
        run_id = "run-cancel"

        async def consume():
            async for _line in svc.event_stream(run_id):
                pass

        task = asyncio.create_task(consume())
        # Yield so the task enters event_stream and registers its queue.
        await asyncio.sleep(0)
        # At this point the task is blocked inside wait_for(queue.get()).
        self.assertIn(run_id, svc._streams)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # The generator's finally block must have run and cleaned up.
        self.assertNotIn(run_id, svc._streams)

    # ── Workspace cancellation ────────────────────────────────────────────────

    async def test_workspace_cancelled_consumer_removes_subscriber(self):
        """Cancelling a task consuming workspace event_stream removes subscriber queue."""
        import contextlib
        svc = _make_workspace()
        run_id = "ws-cancel"

        async def consume():
            async for _evt in svc.event_stream(run_id):
                pass

        task = asyncio.create_task(consume())
        # Yield so the task enters event_stream, snapshots the (empty) replay
        # buffer, and registers its queue before blocking on queue.get().
        await asyncio.sleep(0)
        self.assertIn(run_id, svc._queues)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # The generator's finally block must have run and cleaned up.
        self.assertNotIn(run_id, svc._queues)


if __name__ == "__main__":
    unittest.main()
