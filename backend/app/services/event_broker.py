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

        No post-terminal drain is required: subscribers close at the first
        terminal event; anything emitted after it is discarded from live
        queues on cleanup and truncated out of the replay on delivery.
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
