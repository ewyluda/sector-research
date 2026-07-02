"""Unit tests for the EventBroker SSE fan-out module.

Covers the behaviors previously pinned per-service by test_sse_streams.py
(M1.4), now tested once against the shared module: multi-subscriber fan-out,
unsubscribe/dict cleanup, QueueFull drop isolation, terminal-event close,
replay on/off policy, replay->live handoff continuity, heartbeat emission,
SSE framing, and disconnect (cancellation) cleanup.
"""

import asyncio
import contextlib
import unittest

from backend.app.services.event_broker import EventBroker


def _broker(**overrides) -> EventBroker:
    kwargs = dict(
        terminal_types=frozenset({"complete", "error"}),
        replay=False,
        name="test",
    )
    kwargs.update(overrides)
    return EventBroker(**kwargs)


class TestFanOut(unittest.IsolatedAsyncioTestCase):
    async def test_two_subscribers_both_receive_all_events(self):
        broker = _broker()
        run_id = "run-a"
        received_1: list[dict] = []
        received_2: list[dict] = []

        async def consume(collected: list[dict]):
            async for evt in broker.stream(run_id):
                collected.append(evt)

        t1 = asyncio.create_task(consume(received_1))
        t2 = asyncio.create_task(consume(received_2))
        await asyncio.sleep(0)  # let both consumers register

        # Live queues must honor the configured bound (default 500)
        for q in broker._queues[run_id]:
            self.assertEqual(q.maxsize, 500)

        broker.emit(run_id, {"type": "phase_start", "phase": "quick_screen"})
        broker.emit(run_id, {"type": "complete", "status": "completed"})

        await asyncio.wait_for(asyncio.gather(t1, t2), timeout=2.0)
        for received in (received_1, received_2):
            self.assertEqual([e["type"] for e in received], ["phase_start", "complete"])
        # Terminal close cleaned up the run's queue list entirely
        self.assertNotIn(run_id, broker._queues)

    async def test_emit_no_subscribers_is_noop(self):
        broker = _broker()
        broker.emit("nonexistent-run", {"type": "complete"})  # must not raise

    async def test_full_queue_does_not_block_other_subscriber(self):
        broker = _broker()
        run_id = "run-d"
        q_full: asyncio.Queue = asyncio.Queue(maxsize=1)
        q_full.put_nowait({"type": "filler"})
        q_ok: asyncio.Queue = asyncio.Queue(maxsize=500)
        broker._queues[run_id] = [q_full, q_ok]

        broker.emit(run_id, {"type": "phase_start", "phase": "deep_dive"})

        self.assertEqual(q_ok.get_nowait()["type"], "phase_start")
        self.assertEqual(q_full.qsize(), 1)  # dropped for the full queue, no error

    async def test_cancelled_consumer_removes_subscriber(self):
        broker = _broker()
        run_id = "run-cancel"

        async def consume():
            async for _evt in broker.stream(run_id):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)  # consumer registers, blocks on queue.get()
        self.assertIn(run_id, broker._queues)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self.assertNotIn(run_id, broker._queues)

    async def test_cancelled_sse_consumer_removes_subscriber(self):
        """Cancellation must propagate through sse()'s nested generator into
        stream()'s finally block — the pipeline's actual wire path."""
        broker = _broker()
        run_id = "run-sse-cancel"

        async def consume():
            async for _line in broker.sse(run_id):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)  # consumer registers, blocks on queue.get()
        self.assertIn(run_id, broker._queues)

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self.assertNotIn(run_id, broker._queues)

    async def test_one_cancelled_consumer_leaves_other_active(self):
        broker = _broker()
        run_id = "run-two"
        received: list[dict] = []

        async def consume(collected: list[dict]):
            async for evt in broker.stream(run_id):
                collected.append(evt)

        t_dead = asyncio.create_task(consume([]))
        t_live = asyncio.create_task(consume(received))
        await asyncio.sleep(0)
        self.assertEqual(len(broker._queues[run_id]), 2)

        t_dead.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t_dead
        self.assertEqual(len(broker._queues[run_id]), 1)

        broker.emit(run_id, {"type": "complete", "status": "completed"})
        await asyncio.wait_for(t_live, timeout=2.0)
        self.assertEqual([e["type"] for e in received], ["complete"])


class TestReplayPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_replay_off_drops_pre_subscribe_events(self):
        broker = _broker(replay=False)
        run_id = "off-a"
        broker.emit(run_id, {"type": "phase_start", "phase": "quick_screen"})
        self.assertEqual(broker._replay_buffers, {})

        collected: list[dict] = []

        async def consume():
            async for evt in broker.stream(run_id):
                collected.append(evt)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        broker.emit(run_id, {"type": "complete", "status": "completed"})
        await asyncio.wait_for(task, timeout=2.0)
        # Only the live event arrived; the pre-subscribe one is gone
        self.assertEqual([e["type"] for e in collected], ["complete"])

    async def test_replay_on_delivers_pre_subscribe_events(self):
        broker = _broker(replay=True, terminal_types=frozenset({"done"}))
        run_id = "on-a"
        broker.emit(run_id, {"type": "start"})
        broker.emit(run_id, {"type": "step", "step": "one"})
        broker.emit(run_id, {"type": "done"})

        collected: list[dict] = []
        async for evt in broker.stream(run_id):
            collected.append(evt)

        self.assertEqual([e["type"] for e in collected], ["start", "step", "done"])
        # Terminal inside the replay closed the stream and cleaned up
        self.assertNotIn(run_id, broker._queues)

    async def test_no_gap_between_replay_and_live(self):
        """Events emitted before subscribe arrive via replay, events after via
        the live queue — in order, no duplicates, no gaps."""
        broker = _broker(replay=True, terminal_types=frozenset({"done"}))
        run_id = "on-b"
        broker.emit(run_id, {"type": "start"})

        collected: list[dict] = []

        async def consume():
            async for evt in broker.stream(run_id):
                collected.append(evt)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)  # replay of "start" consumed; now blocked on live queue
        broker.emit(run_id, {"type": "step", "step": "two"})
        broker.emit(run_id, {"type": "done"})
        await asyncio.wait_for(task, timeout=2.0)
        self.assertEqual([e["type"] for e in collected], ["start", "step", "done"])

    async def test_two_late_subscribers_after_terminal_both_get_full_replay(self):
        broker = _broker(replay=True, terminal_types=frozenset({"done"}))
        run_id = "on-c"
        broker.emit(run_id, {"type": "start"})
        broker.emit(run_id, {"type": "done"})

        for _ in range(2):
            collected: list[dict] = []
            async for evt in broker.stream(run_id):
                collected.append(evt)
            self.assertEqual([e["type"] for e in collected], ["start", "done"])


class TestHeartbeat(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_emitted_on_idle(self):
        broker = _broker(heartbeat_seconds=0.05)
        collected: list[dict] = []

        async def consume():
            async for evt in broker.stream("hb-run"):
                collected.append(evt)
                if evt["type"] == "heartbeat":
                    return

        await asyncio.wait_for(consume(), timeout=2.0)
        self.assertEqual(collected[0]["type"], "heartbeat")

    async def test_no_heartbeat_when_disabled(self):
        broker = _broker(heartbeat_seconds=None)
        run_id = "hb-off"
        collected: list[dict] = []

        async def consume():
            async for evt in broker.stream(run_id):
                collected.append(evt)

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.15)  # longer than the other test's heartbeat interval
        broker.emit(run_id, {"type": "complete", "status": "completed"})
        await asyncio.wait_for(task, timeout=2.0)
        self.assertEqual([e["type"] for e in collected], ["complete"])


class TestSseFraming(unittest.IsolatedAsyncioTestCase):
    async def test_sse_framing_matches_legacy_format(self):
        """Byte-exact pin of the `data: {json}\\n\\n` framing the pipeline
        route has always served (json.dumps default separators)."""
        broker = _broker(replay=True)
        run_id = "sse-a"
        broker.emit(run_id, {"type": "phase_start", "phase": "quick_screen"})
        broker.emit(run_id, {"type": "complete", "status": "completed"})

        lines: list[str] = []
        async for line in broker.sse(run_id):
            lines.append(line)

        self.assertEqual(lines[0], 'data: {"type": "phase_start", "phase": "quick_screen"}\n\n')
        self.assertEqual(lines[1], 'data: {"type": "complete", "status": "completed"}\n\n')

    async def test_sse_heartbeat_framing_matches_legacy_literal(self):
        """The old pipeline code yielded a hand-written heartbeat string;
        json.dumps must produce the identical bytes."""
        broker = _broker(heartbeat_seconds=0.05)
        first_line = None
        async for line in broker.sse("sse-hb"):
            first_line = line
            break
        self.assertEqual(first_line, 'data: {"type": "heartbeat"}\n\n')


if __name__ == "__main__":
    unittest.main()
