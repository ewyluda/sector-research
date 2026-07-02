# SSE Unification (EventBroker) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three copy-pasted SSE fan-out implementations (pipeline, workspace, prospectus) with one `EventBroker` module, zero-behavior-change on the wire.

**Architecture:** A new leaf module `backend/app/services/event_broker.py` owns subscribe/emit/replay/terminal-close/heartbeat behind one class. Each orchestrator service holds a configured instance and delegates its existing `_emit()` / `event_stream()` seams to it. API routes and frontend are untouched. Spec: `docs/superpowers/specs/2026-07-01-sse-unification-design.md`.

**Tech Stack:** Python 3, asyncio, FastAPI StreamingResponse, stdlib `unittest` (NO pytest).

## Global Constraints

- **Zero wire-behavior change.** Every byte on the SSE wire must be identical for all three services. Pipeline stays no-replay; workspace/prospectus stay replay-on.
- Backend imports are absolute, rooted at project root: `from backend.app.services.event_broker import EventBroker`.
- Tests run via stdlib unittest from project root with venv active: `source backend/venv/bin/activate` then `python -m unittest backend.tests.<module> -v`. Full suite: `python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')`.
- Test files need the dummy-env preamble before importing app modules (see existing tests): `os.environ.setdefault("FMP_API_KEY", "test")` etc.
- Lint gate: `ruff check backend` from project root must stay clean.
- `EventBroker` must import nothing from any service module (leaf, like `services/universe.py`).
- The replay-snapshot + queue-registration block in `stream()` must be synchronous — no `await` between snapshot and register.
- Work on a branch: `git checkout -b refactor/sse-event-broker` (from up-to-date main, after PR #62 merges, or from the current branch head if stacking).

---

### Task 1: EventBroker module + unit tests

**Files:**
- Create: `backend/app/services/event_broker.py`
- Test: `backend/tests/test_event_broker.py`

**Interfaces:**
- Consumes: nothing (leaf module).
- Produces: `EventBroker(*, terminal_types: frozenset[str], replay: bool, queue_maxsize: int = 500, heartbeat_seconds: float | None = None, name: str = "")` with:
  - `emit(run_id: str, event: dict) -> None` (sync)
  - `stream(run_id: str) -> AsyncIterator[dict]` (async generator)
  - `sse(run_id: str) -> AsyncGenerator[str, None]` (async generator of `data: {json}\n\n` strings)
  - Internal state inspected by tests: `_replay_buffers: dict[str, list[dict]]`, `_queues: dict[str, list[asyncio.Queue]]`.
  Tasks 2–4 rely on exactly these names.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_event_broker.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_event_broker -v
```

Expected: FAIL at import time with `ModuleNotFoundError: No module named 'backend.app.services.event_broker'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/event_broker.py`:

```python
"""In-memory per-run SSE event fan-out: subscribe / emit / replay / terminal-close.

One EventBroker instance per orchestrator service (pipeline, workspace,
prospectus), configured with that service's terminal event types and replay
policy. Single home for the queue-management, QueueFull, disconnect-cleanup,
and terminal-close logic previously copy-pasted across the three services.

Replay policy:
  - replay=True (workspace, prospectus): every emitted event is appended to a
    per-run buffer; a subscriber connecting late first receives the full
    buffer, then live events. Buffers are unbounded per run and run_id keys
    are never pruned — acceptable because these runs emit a small, bounded
    number of step events and this is a single-user, process-lifetime tool.
  - replay=False (pipeline): events emitted with no subscribers are dropped.
    The pipeline frontend REST-hydrates /pipeline/[runId] on load, so events
    dropped in the connect window are recovered from persisted state. Replay
    is deliberately off: pipeline runs emit hundreds of "token" chunk events
    plus large deep_dive_start payloads, and replaying those into a
    REST-hydrated UI would double-render text.

Designated extension point (not built): if the pipeline connect-window gap
ever bites, selective replay — buffer all event types except "token" — can be
added as a should_buffer predicate on this class, paired with a frontend
check that the reducer applies replayed phase_complete events idempotently
on top of REST-hydrated state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, AsyncIterator

logger = logging.getLogger(__name__)


class EventBroker:
    """Per-run SSE fan-out with configurable replay, terminal, and heartbeat."""

    def __init__(
        self,
        *,
        terminal_types: frozenset[str],
        replay: bool,
        queue_maxsize: int = 500,
        heartbeat_seconds: float | None = None,
        name: str = "",
    ) -> None:
        self.terminal_types = terminal_types
        self.replay = replay
        self.queue_maxsize = queue_maxsize
        self.heartbeat_seconds = heartbeat_seconds
        self.name = name
        self._replay_buffers: dict[str, list[dict]] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def emit(self, run_id: str, event: dict) -> None:
        """Fan out an event to every subscriber; buffer it when replay is on.

        A full subscriber queue warns and drops the event for that subscriber
        only — it never blocks delivery to the others.
        """
        if self.replay:
            self._replay_buffers.setdefault(run_id, []).append(event)
        for q in self._queues.get(run_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "%s SSE queue full for run %s (subscriber %s); dropping event",
                    self.name or "event-broker", run_id, id(q),
                )

    async def stream(self, run_id: str) -> AsyncIterator[dict]:
        """Yield event dicts (replay first, then live) until a terminal event.

        Snapshots the replay buffer and registers the subscriber queue in one
        synchronous block — no await between the two — so no events can be
        lost between the snapshot and live delivery. With heartbeat_seconds
        set, idle periods yield {"type": "heartbeat"} instead of blocking
        forever.

        No post-terminal drain is required: emit() never fires after the
        terminal event in any service (terminal events are the last emit in
        every run path).
        """
        replay_snapshot = list(self._replay_buffers.get(run_id, []))
        q: asyncio.Queue = asyncio.Queue(maxsize=self.queue_maxsize)
        self._queues.setdefault(run_id, []).append(q)
        try:
            for evt in replay_snapshot:
                yield evt
                if evt.get("type") in self.terminal_types:
                    return
            while True:
                if self.heartbeat_seconds is not None:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=self.heartbeat_seconds)
                    except asyncio.TimeoutError:
                        yield {"type": "heartbeat"}
                        continue
                else:
                    evt = await q.get()
                yield evt
                if evt.get("type") in self.terminal_types:
                    return
        finally:
            queues = self._queues.get(run_id)
            if queues is not None:
                try:
                    queues.remove(q)
                except ValueError:
                    pass
                if not queues:
                    self._queues.pop(run_id, None)

    async def sse(self, run_id: str) -> AsyncGenerator[str, None]:
        """Wrap stream() in ``data: {json}\\n\\n`` SSE framing — the single
        SSE serializer for the app."""
        async for event in self.stream(run_id):
            yield f"data: {json.dumps(event)}\n\n"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest backend.tests.test_event_broker -v
```

Expected: all 13 tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
ruff check backend
git add backend/app/services/event_broker.py backend/tests/test_event_broker.py
git commit -m "feat: EventBroker — single SSE fan-out module (audit #1, part 1)"
```

---

### Task 2: Migrate PipelineService

**Files:**
- Modify: `backend/app/services/pipeline.py` (constructor ~line 88-95; SSE section ~lines 507-558; imports)
- Create: `backend/tests/test_sse_service_config.py`
- Modify: `backend/tests/test_sse_streams.py` (remove pipeline coverage)

**Interfaces:**
- Consumes: `EventBroker` from Task 1 (exact constructor kwargs and `emit`/`sse` methods).
- Produces: `PipelineService._broker: EventBroker`; `PipelineService._emit(run_id, event)` and `event_stream(run_id)` keep their existing signatures (all ~9 `_emit` call sites and `api/pipeline.py:273-276` unchanged). `subscribe`/`unsubscribe`/`_streams` are DELETED.

- [ ] **Step 1: Write the failing config-pin + integration tests**

Create `backend/tests/test_sse_service_config.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m unittest backend.tests.test_sse_service_config -v
```

Expected: FAIL — `AttributeError: 'PipelineService' object has no attribute '_broker'`.

- [ ] **Step 3: Migrate the service**

In `backend/app/services/pipeline.py`:

3a. Add the import (with the other `backend.app.services` imports near the top):

```python
from backend.app.services.event_broker import EventBroker
```

3b. Remove the now-unused `import json` line (json is used only by the old `event_stream`; verify with a grep before deleting: `grep -n "json\." backend/app/services/pipeline.py` must show no remaining uses).

3c. In `__init__`, replace:

```python
        # Active SSE subscriber queues keyed by run_id.  Multiple subscribers
        # (e.g. two browser tabs) are each given their own queue; fan-out
        # delivers every event to all of them independently.
        self._streams: dict[str, list[asyncio.Queue]] = {}
```

with:

```python
        # SSE fan-out. replay=False: events emitted before any subscriber are
        # dropped — acceptable because the frontend REST-hydrates
        # /pipeline/[runId] on load, so events dropped in the connect window
        # are recovered from persisted state (and pipeline runs emit hundreds
        # of "token" chunks that must not replay into a hydrated UI).
        self._broker = EventBroker(
            terminal_types=frozenset({"complete", "error"}),
            replay=False,
            heartbeat_seconds=30.0,
            name="pipeline",
        )
```

3d. Replace the entire SSE section (the `_emit`, `subscribe`, `unsubscribe`, and `event_stream` methods, currently ~lines 509-558) with:

```python
    def _emit(self, run_id: str, event: dict) -> None:
        """Fan out an event to every connected SSE client for this run."""
        self._broker.emit(run_id, event)

    def event_stream(self, run_id: str) -> AsyncGenerator[str, None]:
        """SSE-framed event stream for the FastAPI StreamingResponse."""
        return self._broker.sse(run_id)
```

Note the signature change from `async def` to `def`: both return an async generator when called, so `api/pipeline.py:273-276` (`StreamingResponse(pipeline.event_stream(run_id), ...)`) is unchanged.

- [ ] **Step 4: Remove the migrated pipeline coverage from test_sse_streams.py**

In `backend/tests/test_sse_streams.py`, delete (their behaviors now live in `test_event_broker.py` + `test_sse_service_config.py`):
- the `TestPipelineSSE` class (all 5 tests),
- the `test_pipeline_cancelled_consumer_removes_subscriber` method inside `TestCancellationCleanup`,
- the `_make_pipeline` helper and the `from backend.app.services.pipeline import PipelineService` import,
- the `Pipeline:` block (criteria 1-4) from the module docstring.

- [ ] **Step 5: Run the affected suites**

```bash
python -m unittest backend.tests.test_event_broker backend.tests.test_sse_service_config backend.tests.test_sse_streams -v
```

Expected: all PASS (sse_streams now runs only workspace + prospectus tests).

- [ ] **Step 6: Run the full backend suite + lint**

```bash
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
ruff check backend
```

Expected: suite green (any other test touching `svc._streams`/`subscribe` would surface here), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/pipeline.py backend/tests/test_sse_service_config.py backend/tests/test_sse_streams.py
git commit -m "refactor: PipelineService SSE via EventBroker (replay off, 30s heartbeat)"
```

---

### Task 3: Migrate WorkspaceService

**Files:**
- Modify: `backend/app/services/workspace.py` (constructor ~lines 121-129; SSE section ~lines 133-189)
- Modify: `backend/tests/test_sse_service_config.py` (append workspace tests)
- Modify: `backend/tests/test_sse_streams.py` (remove workspace coverage)

**Interfaces:**
- Consumes: `EventBroker` (Task 1).
- Produces: `WorkspaceService._broker: EventBroker`; `_emit(run_id, event)` and `event_stream(run_id) -> AsyncIterator[dict]` keep their signatures (`api/workspace.py:74-86` unchanged — the route still json-dumps/frames raw dicts). `_replay`/`_queues` are DELETED. `_ticker_locks` + `_ticker_locks_guard` stay untouched.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_sse_service_config.py` (add the import next to the pipeline one):

```python
from backend.app.services.workspace import WorkspaceService


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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m unittest backend.tests.test_sse_service_config -v
```

Expected: workspace tests FAIL with `AttributeError: 'WorkspaceService' object has no attribute '_broker'`; pipeline tests still PASS.

- [ ] **Step 3: Migrate the service**

In `backend/app/services/workspace.py`:

3a. Add the import:

```python
from backend.app.services.event_broker import EventBroker
```

3b. In `__init__`, replace the SSE state block (the long comment plus `self._replay` / `self._queues` lines, ~121-129) with:

```python
        # SSE fan-out with replay: events emitted by kick_off() before the
        # frontend connects are delivered to every (including late)
        # subscriber. See services/event_broker.py for the policy docs.
        self._broker = EventBroker(
            terminal_types=frozenset({"workspace_run_complete", "workspace_run_failed"}),
            replay=True,
            name="workspace",
        )
```

Keep `self._ticker_locks` / `self._ticker_locks_guard` exactly as they are.

3c. Replace the whole `── SSE plumbing ──` section (the `_emit` and `event_stream` methods, ~lines 133-189) with:

```python
    # ── SSE plumbing ───────────────────────────────────────────────────────────

    def _emit(self, run_id: str, event: dict) -> None:
        """Fan out an event (replay-buffered) to every subscriber for this run."""
        self._broker.emit(run_id, event)

    def event_stream(self, run_id: str) -> AsyncIterator[dict]:
        """Raw event-dict stream (replay first, then live) until a terminal event."""
        return self._broker.stream(run_id)
```

(`AsyncIterator` is already imported in this file.)

- [ ] **Step 4: Remove the migrated workspace coverage from test_sse_streams.py**

In `backend/tests/test_sse_streams.py`, delete:
- the `TestWorkspaceSSE` class (3 tests),
- the now-empty `TestCancellationCleanup` class (its one remaining method `test_workspace_cancelled_consumer_removes_subscriber` is covered by `test_event_broker.py::TestFanOut::test_cancelled_consumer_removes_subscriber`),
- the `_make_workspace` helper and the `from backend.app.services.workspace import WorkspaceService` import,
- the `Workspace:` block (criteria 5-7) from the module docstring.

- [ ] **Step 5: Run the affected suites**

```bash
python -m unittest backend.tests.test_event_broker backend.tests.test_sse_service_config backend.tests.test_sse_streams -v
```

Expected: all PASS (sse_streams now runs only prospectus tests).

- [ ] **Step 6: Run the full backend suite + lint**

```bash
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
ruff check backend
```

Expected: green + clean. (Workspace has other test files — `test_sse_streams` was not the only consumer of the service; the full run catches any test poking `_replay`/`_queues`.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/workspace.py backend/tests/test_sse_service_config.py backend/tests/test_sse_streams.py
git commit -m "refactor: WorkspaceService SSE via EventBroker (replay on)"
```

---

### Task 4: Migrate ProspectusService, delete test_sse_streams.py

**Files:**
- Modify: `backend/app/services/prospectus_service.py` (constructor ~lines 50-61; SSE section ~lines 63-118; `TERMINAL_EVENTS` constant at line 46)
- Modify: `backend/tests/test_sse_service_config.py` (append prospectus tests)
- Delete: `backend/tests/test_sse_streams.py`

**Interfaces:**
- Consumes: `EventBroker` (Task 1).
- Produces: `ProspectusService._broker: EventBroker`; `_emit(rid, evt)` and `event_stream(rid) -> AsyncIterator[dict]` keep their signatures (`api/prospectus.py:59-70` unchanged). `_replay`/`_queues` DELETED. The module-level `TERMINAL_EVENTS` constant stays (it is the config source fed to the broker).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_sse_service_config.py`:

```python
from backend.app.services.prospectus_service import ProspectusService


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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m unittest backend.tests.test_sse_service_config -v
```

Expected: prospectus tests FAIL with `AttributeError: 'ProspectusService' object has no attribute '_broker'`; pipeline + workspace tests still PASS.

- [ ] **Step 3: Migrate the service**

In `backend/app/services/prospectus_service.py`:

3a. Add the import:

```python
from backend.app.services.event_broker import EventBroker
```

3b. In `__init__`, replace the SSE state block (comment + `self._replay` / `self._queues`, ~lines 53-61) with:

```python
        # SSE fan-out with replay: late subscribers get the full event
        # history. See services/event_broker.py for the policy docs.
        self._broker = EventBroker(
            terminal_types=frozenset(TERMINAL_EVENTS),
            replay=True,
            name="prospectus",
        )
```

3c. Replace the whole `── SSE plumbing ──` section (the `_emit` and `event_stream` methods, ~lines 63-118) with:

```python
    # ── SSE plumbing ──────────────────────────────────────────────────────────

    def _emit(self, rid: str, evt: dict) -> None:
        """Fan out an event (replay-buffered) to every subscriber for this report."""
        self._broker.emit(rid, evt)

    def event_stream(self, rid: str) -> AsyncIterator[dict]:
        """Raw event-dict stream (replay first, then live) until a terminal event."""
        return self._broker.stream(rid)
```

(`AsyncIterator` is already imported in this file. If `asyncio` is now unused in this module, remove its import — check with `grep -n "asyncio\." backend/app/services/prospectus_service.py` first; `_run_pipeline` is started via `asyncio.create_task` so it likely stays.)

- [ ] **Step 4: Delete test_sse_streams.py**

```bash
git rm backend/tests/test_sse_streams.py
```

Its remaining prospectus coverage (criteria 8-11) is now in `test_event_broker.py` (mechanics) + `test_sse_service_config.py` (wiring).

- [ ] **Step 5: Run the affected suites**

```bash
python -m unittest backend.tests.test_event_broker backend.tests.test_sse_service_config -v
```

Expected: all PASS.

- [ ] **Step 6: Run the full backend suite + lint**

```bash
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
ruff check backend
```

Expected: green + clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/prospectus_service.py backend/tests/test_sse_service_config.py
git commit -m "refactor: ProspectusService SSE via EventBroker; retire test_sse_streams"
```

---

### Task 5: Docs, full gates, live smoke

**Files:**
- Modify: `CLAUDE.md` (Streaming section ~line 213; Workspace loop bullet ~line 286; Prospectus paragraph ~line 320)
- No code changes.

**Interfaces:**
- Consumes: the migrated services from Tasks 2-4.
- Produces: nothing downstream — this is the verification + documentation gate.

- [ ] **Step 1: Update CLAUDE.md**

1a. Replace the Streaming section paragraph:

OLD:
> `services/pipeline.py::PipelineService` holds an in-memory `dict[run_id, list[asyncio.Queue]]` for SSE subscribers (fan-out: each browser tab gets its own queue). Events are pushed with `_emit()` and consumed via `event_stream()` which `GET /api/runs/{id}/stream` wraps in a `StreamingResponse`. Event types live as a discriminated union in `frontend/lib/api/pipeline.ts::SSEEvent` — keep the Python `_emit` calls and the TS union in sync.

NEW:
> SSE fan-out lives in one module: `services/event_broker.py::EventBroker` (emit / replay / terminal-close / heartbeat behind one class; per-subscriber queues bounded at 500, QueueFull drops for that subscriber only). Each orchestrator holds a configured instance and delegates its `_emit()` / `event_stream()`: **pipeline** (terminal `complete`/`error`, replay **off** — pre-subscribe events drop by design because `/pipeline/[runId]` REST-hydrates and pipeline runs emit hundreds of `token` chunks that must not replay into a hydrated UI; 30s heartbeat; `event_stream` yields SSE-framed strings via `broker.sse()`), **workspace** (`workspace_run_complete`/`_failed`, replay on) and **prospectus** (`prospectus_complete`/`_failed`, replay on) — both yield raw dicts via `broker.stream()`; their API routes do the SSE framing. `GET /api/runs/{id}/stream` wraps pipeline's in a `StreamingResponse`. Event types live as a discriminated union in `frontend/lib/api/pipeline.ts::SSEEvent` — keep the Python `_emit` calls and the TS union in sync. Selective replay for pipeline (buffer all but `token`) is the documented extension point in the module — do not add replay wholesale.

1b. In the Workspace loop section, replace:

OLD:
> Mirrors `PipelineService` — fan-out `dict[run_id, list[asyncio.Queue]]` SSE plumbing plus a per-run replay buffer (`dict[run_id, list[dict]]`) so events emitted before the frontend connects are delivered to every (including late) subscriber via a full replay on `event_stream()` entry, `WorkspaceRunInFlight` guard against duplicate starts per ticker.

NEW:
> SSE via a replay-on `EventBroker` (see Streaming) so events emitted before the frontend connects are delivered to every (including late) subscriber via a full replay on `event_stream()` entry, `WorkspaceRunInFlight` guard against duplicate starts per ticker.

1c. In the Prospectus pipeline section, replace the phrase:

OLD:
> with in-memory SSE fan-out + a per-run replay buffer (same pattern as `WorkspaceService`: late subscribers get a full replay) and per-step session+commit

NEW:
> with SSE via a replay-on `EventBroker` (same pattern as `WorkspaceService`: late subscribers get a full replay) and per-step session+commit

- [ ] **Step 2: Run every gate**

```bash
# backend
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
ruff check backend
# frontend (untouched, but run per spec)
cd frontend && npm run typecheck && npm run lint && npm test && cd ..
```

Expected: everything green.

- [ ] **Step 3: Live smoke — heartbeat + SSE framing (no LLM cost)**

Start the backend against the test DB (background):

```bash
source backend/venv/bin/activate
DATABASE_URL="postgresql+asyncpg://ericwyluda@localhost:5432/sector_research_test" \
  uvicorn backend.app.main:app --port 8000
```

Then (use 127.0.0.1, not localhost — Docker can steal IPv6 localhost:8000):

```bash
curl -sN --max-time 65 http://127.0.0.1:8000/api/runs/smoke-nonexistent/stream
```

Expected output: exactly two lines of `data: {"type": "heartbeat"}` (at ~30s and ~60s), then curl times out. This proves the broker's `sse()` framing + heartbeat live on the real route.

- [ ] **Step 4: Live smoke — workspace replay + two-tab fan-out (costs a few LLM calls)**

Pick a ticker with a completed research run on the test DB (any row on `/status`). Kick off and immediately attach two subscribers:

```bash
RUN_ID=$(curl -s -X POST "http://127.0.0.1:8000/api/workspace/NVDA/runs" | python3 -c "import sys,json;print(json.load(sys.stdin)['run_id'])")
sleep 3   # let kick_off emit its early events BEFORE we connect — this is the replay test
curl -sN "http://127.0.0.1:8000/api/workspace/runs/$RUN_ID/stream" > /tmp/tab1.txt &
curl -sN "http://127.0.0.1:8000/api/workspace/runs/$RUN_ID/stream" > /tmp/tab2.txt &
wait
diff /tmp/tab1.txt /tmp/tab2.txt && echo "TABS IDENTICAL"
head -3 /tmp/tab1.txt
```

Expected: both files start with the replayed `workspace_run_start` + early `step_start` events (emitted before we connected), end with `workspace_run_complete` (or `workspace_run_failed` — either proves terminal close), and are identical (`TABS IDENTICAL`). Substitute NVDA with any ticker that has a completed run if the 409/400 preflight rejects it. Stop uvicorn afterwards.

- [ ] **Step 5: Commit docs**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md streaming section — EventBroker unification"
```

- [ ] **Step 6: Finish the branch**

Use superpowers:finishing-a-development-branch — push, open a PR titled "refactor: unify SSE fan-out behind EventBroker (audit #1)", verify CI green.

---

## Self-review notes (done at plan-writing time)

- **Spec coverage:** module + config table (Task 1-4), zero-wire-change policy (framing pin test + no route/frontend edits), test migration incl. deletion of `test_sse_streams.py` (Tasks 2-4), config pins (Tasks 2-4), wire-format pin (Task 1), docs + live smoke (Task 5). Extension point documented in the module docstring (Task 1). ✓
- **Type consistency:** `terminal_types: frozenset[str]`, `_replay_buffers`, `_queues`, `emit/stream/sse` used identically across all tasks. ✓
- **Known naming choice:** broker uses `_replay_buffers` (not `_replay`) to avoid colliding with the `replay: bool` policy attribute.
