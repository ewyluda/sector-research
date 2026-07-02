"""Tests for SSE multi-subscriber fan-out in PipelineService, WorkspaceService,
and ProspectusService.

Acceptance criteria (M1.4):
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

from backend.app.services.prospectus_service import ProspectusService


def _make_prospectus() -> ProspectusService:
    return ProspectusService(edgar=MagicMock())


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


if __name__ == "__main__":
    unittest.main()
