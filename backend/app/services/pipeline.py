"""Pipeline service — manages run lifecycle and state persistence.

Responsibilities:
  - Create new research runs
  - Advance runs through the graph on user approval
  - Persist ResearchState to PostgreSQL after every phase transition
  - Stream phase output tokens to connected SSE clients
  - Enforce the 2-loop cap
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.clients.fred import FREDClient
from backend.app.graph import nodes
from backend.app.graph.pipeline import make_graph
from backend.app.graph.state import ResearchState
from backend.app.models.research_run import ResearchRun

logger = logging.getLogger(__name__)

# ── Phase display metadata ────────────────────────────────────────────────────

PHASE_META = {
    "quick_screen":       {"label": "Quick Screen",        "phase_num": 1},
    "deep_dive":          {"label": "Deep Dive",           "phase_num": 3},
    "thesis_construction":{"label": "Thesis Construction", "phase_num": 4},
    "risk_stress_test":   {"label": "Risk Stress-Test",    "phase_num": 5},
    "position_monitor":   {"label": "Position Monitor",    "phase_num": 6},
    "completed":          {"label": "Complete",            "phase_num": 6},
}

# Phase names don't always match their storage keys in state.phase_outputs.
# The nodes use short keys ("thesis", "risk", "position") but the pipeline
# uses full phase names ("thesis_construction", "risk_stress_test", etc.).
# This mapping is used by _run_phase to find the correct phase_output dict
# when emitting interrupt events.
PHASE_OUTPUT_KEYS: dict[str, str] = {
    "thesis_construction": "thesis",
    "risk_stress_test":    "risk",
    "position_monitor":    "position",
}


class PipelineService:
    """Manages research run lifecycle."""

    def __init__(self, fmp: FMPClient, fred: FREDClient | None = None) -> None:
        self._fmp = fmp
        self._fred = fred
        self._graph = make_graph(fmp)
        # Active SSE queues keyed by run_id
        self._streams: dict[str, asyncio.Queue] = {}

    # ── Run creation ──────────────────────────────────────────────────────────

    async def create_run(
        self,
        ticker: str,
        theme_id: str,
        db: AsyncSession,
    ) -> ResearchRun:
        """Create a new research run and persist initial state."""
        run_id = str(uuid.uuid4())
        state = ResearchState(
            ticker=ticker.upper(),
            theme_id=theme_id,
            run_id=run_id,
        )

        run = ResearchRun(
            id=run_id,
            ticker=ticker.upper(),
            theme_id=theme_id,
            phase="quick_screen",
            status="in_progress",
            state=state.to_dict(),
            loop_count=0,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        logger.info("Created run %s for %s", run_id, ticker)
        return run

    # ── Run advancement ───────────────────────────────────────────────────────

    async def advance(
        self,
        run_id: str,
        action: str,  # "approve" | "flag" | "stop"
        feedback: str | None,
        db: AsyncSession,
    ) -> ResearchRun:
        """
        Advance a paused run based on human action.
        - approve: run the next phase
        - flag:    record note and advance
        - stop:    archive as watchlist or pass
        """
        result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        state = ResearchState.from_dict(run.state)

        if action == "stop":
            state.status = "watchlist"
            if feedback:
                state.human_feedback[state.phase] = feedback
            run.status = "watchlist"
            run.state = state.to_dict()
            await db.commit()
            logger.info("Run %s stopped by user at phase %s", run_id, state.phase)
            return run

        # Record feedback/flag
        if feedback:
            state.human_feedback[state.phase] = feedback
        if action == "flag" and feedback:
            state.flags.append(f"{state.phase}: {feedback}")

        # Resume — advance to next phase
        state.status = "in_progress"
        next_phase = self._next_phase(state)
        state.phase = next_phase
        run.phase = next_phase
        run.status = "in_progress"
        run.loop_count = state.loop_count
        run.state = state.to_dict()
        await db.commit()

        # Run the next phase in background
        asyncio.create_task(self._run_phase(run_id, state, db))
        return run

    def _next_phase(self, state: ResearchState) -> str:
        """Determine next phase based on current phase and state."""
        phase_sequence = {
            "quick_screen": "deep_dive",
            "deep_dive": "thesis_construction",
            "thesis_construction": "risk_stress_test",
            "risk_stress_test": (
                "deep_dive" if (state.loop_context and state.loop_count <= 2)
                else "completed"
            ),
        }
        return phase_sequence.get(state.phase, "completed")

    async def _run_phase(
        self, run_id: str, state: ResearchState, db: AsyncSession
    ) -> None:
        """Execute phases in a loop, auto-advancing while status is in_progress."""
        while state.status == "in_progress":
            phase = state.phase
            self._emit(run_id, {"type": "phase_start", "phase": phase,
                                 "label": PHASE_META.get(phase, {}).get("label", phase)})

            try:
                if phase == "quick_screen":
                    state = await nodes.node_quick_screen(state, self._fmp)
                elif phase == "deep_dive":
                    state = await self._run_deep_dive_with_streaming(state, run_id)
                elif phase == "thesis_construction":
                    state = await nodes.node_thesis_construction(state)
                elif phase == "risk_stress_test":
                    state = await nodes.node_risk_stress_test(state)
                elif phase == "position_monitor":
                    state = await nodes.node_position_monitor(state)

                # Persist state after phase execution
                async with db.begin():
                    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                    run = result.scalar_one_or_none()
                    if run:
                        run.state = state.to_dict()
                        run.phase = state.phase
                        run.status = state.status
                        run.loop_count = state.loop_count

                # Emit phase_complete event
                output_key = PHASE_OUTPUT_KEYS.get(phase, phase)
                phase_output = state.phase_outputs.get(output_key, {})
                self._emit(run_id, {
                    "type": "phase_complete",
                    "phase": phase,
                    "output": phase_output,
                    "conviction_score": state.conviction_score,
                })

                # If still in_progress, advance to next phase
                if state.status == "in_progress":
                    next_phase = self._next_phase(state)
                    if next_phase == "completed":
                        state.status = "completed"
                        state.phase = "completed"
                    else:
                        state.phase = next_phase

                    # Persist the phase advance
                    async with db.begin():
                        result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                        run = result.scalar_one_or_none()
                        if run:
                            run.state = state.to_dict()
                            run.phase = state.phase
                            run.status = state.status
                            run.loop_count = state.loop_count

            except Exception as e:
                logger.error("Phase %s failed for run %s: %s", phase, run_id, e)
                self._emit(run_id, {"type": "error", "phase": phase, "message": str(e)})
                break

        # After the loop: emit complete if we finished successfully
        if state.status in ("completed", "watchlist", "pass"):
            self._emit(run_id, {"type": "complete", "status": state.status,
                                 "conviction_score": state.conviction_score,
                                 "thesis_status": state.thesis_status})

    async def _run_deep_dive_with_streaming(
        self, state: ResearchState, run_id: str
    ) -> ResearchState:
        """Deep dive with per-category progress events."""
        categories = (
            state.loop_context.get("categories", [])
            if state.loop_context else None
        )
        state = await nodes.node_deep_dive(state, self._fmp, self._fred)

        # Emit start event with curated financials (available after node runs)
        self._emit(run_id, {
            "type": "deep_dive_start",
            "categories": categories or ["all 9 categories"],
            "loop_count": state.loop_count,
            "loop_context": state.loop_context,
            "curated_financials": state.curated_financials,
            "transcript_analysis": state.transcript_analysis,
        })

        # Emit per-category results
        for cat, result in state.get_deep_dive_results().items():
            from backend.app.graph.state import CategoryResult, CategoryError
            if isinstance(result, CategoryResult):
                self._emit(run_id, {
                    "type": "category_complete",
                    "category": cat,
                    "score": result.score,
                    "key_findings": result.key_findings,
                    "structured": result.structured,
                })
            else:
                self._emit(run_id, {
                    "type": "category_error",
                    "category": cat,
                    "reason": result.reason,
                })
        return state

    async def _run_with_streaming(
        self, state: ResearchState, node_fn, run_id: str, output_key: str
    ) -> ResearchState:
        """Run a node and emit its output content as a stream event."""
        state = await node_fn(state)
        output = state.phase_outputs.get(output_key, {})
        if isinstance(output, dict) and "content" in output:
            # Simulate token streaming from the completed content
            content = output["content"]
            chunk_size = 50
            for i in range(0, len(content), chunk_size):
                self._emit(run_id, {
                    "type": "token",
                    "text": content[i:i + chunk_size],
                })
                await asyncio.sleep(0.01)
        return state

    # ── SSE streaming ─────────────────────────────────────────────────────────

    def _emit(self, run_id: str, event: dict) -> None:
        """Push an event to all connected SSE clients for this run."""
        if run_id in self._streams:
            try:
                self._streams[run_id].put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for run %s", run_id)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        """Register an SSE client for a run. Returns the event queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._streams[run_id] = q
        return q

    def unsubscribe(self, run_id: str) -> None:
        self._streams.pop(run_id, None)

    async def event_stream(self, run_id: str) -> AsyncGenerator[str, None]:
        """Async generator for FastAPI SSE response."""
        queue = self.subscribe(run_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event.get("type") in ("complete", "error"):
                        break
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"heartbeat\"}\n\n"
        finally:
            self.unsubscribe(run_id)

    # ── Querying ──────────────────────────────────────────────────────────────

    async def get_run_state(self, run_id: str, db: AsyncSession) -> ResearchState | None:
        result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            return None
        return ResearchState.from_dict(run.state)
