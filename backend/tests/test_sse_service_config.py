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


if __name__ == "__main__":
    unittest.main()
