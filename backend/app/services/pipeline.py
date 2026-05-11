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
from typing import Any, AsyncGenerator


def _coerce_to_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.clients.fmp import FMPClient
from backend.app.clients.fred import FREDClient
from backend.app.graph import nodes
from backend.app.graph.pipeline import make_graph
from backend.app.graph.state import ResearchState
from backend.app.db import async_session, unit_of_work
from backend.app.services import outcome_tracker
from backend.app.models.research_run import ResearchRun
from backend.app.models.signal import Signal
from backend.app.services import edgar_ingest, edgar_sections_ingest
from backend.app.services.relationship_context import (
    CounterpartyContext,
    get_counterparty_context,
)
from backend.app.services.run_timestamps import mark_terminal_completed_at
from backend.app.graph.deep_dive_routing import EDGAR_ROUTING, FILING_EXCERPT_ROUTING

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

    def __init__(
        self,
        fmp: FMPClient,
        fred: FREDClient | None = None,
        edgar: EdgarClient | None = None,
    ) -> None:
        self._fmp = fmp
        self._fred = fred
        self._edgar = edgar
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
            "deep_dive": "targeted_followup",
            "targeted_followup": "thesis_construction",
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
                    state = await self._run_deep_dive_with_streaming(state, run_id, db)
                elif phase == "targeted_followup":
                    state = await nodes.node_targeted_followup(state)
                elif phase == "thesis_construction":
                    state = await nodes.node_thesis_construction(state)
                elif phase == "risk_stress_test":
                    state = await nodes.node_risk_stress_test(state)
                elif phase == "position_monitor":
                    state = await nodes.node_position_monitor(state)

                if state.status in ("completed", "watchlist", "pass"):
                    mark_terminal_completed_at(state)
                    await self._record_terminal_outcome(run_id=run_id, state=state)

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
                state.status = "error"
                try:
                    async with db.begin():
                        result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                        run = result.scalar_one_or_none()
                        if run:
                            run.state = state.to_dict()
                            run.phase = state.phase
                            run.status = "error"
                except Exception:
                    logger.error("Failed to persist error state for run %s", run_id)
                self._emit(run_id, {"type": "error", "phase": phase, "message": str(e)})
                break

        # After the loop: emit terminal event
        if state.status in ("completed", "watchlist", "pass"):
            self._emit(run_id, {"type": "complete", "status": state.status,
                                 "conviction_score": state.conviction_score,
                                 "thesis_status": state.thesis_status})
        elif state.status == "error":
            self._emit(run_id, {"type": "complete", "status": "error",
                                 "phase": state.phase,
                                 "conviction_score": state.conviction_score,
                                 "thesis_status": state.thesis_status})

    async def _record_terminal_outcome(self, *, run_id: str, state: Any) -> None:
        """Best-effort: record the verdict in verdict_outcomes. Errors logged, never propagated."""
        try:
            async with unit_of_work() as db:
                signals_row: dict | None = None
                if state.theme_id:
                    sig_rows = (await db.execute(
                        select(Signal).where(
                            Signal.ticker == state.ticker,
                            Signal.theme_id == state.theme_id,
                        )
                    )).scalars().all()
                    if sig_rows:
                        signals_row = {r.signal_type: r.value for r in sig_rows}

                theme_seed_tickers: list[str] | None = None
                if state.theme_id:
                    from backend.app.models.theme import Theme
                    theme = (await db.execute(
                        select(Theme).where(Theme.id == state.theme_id)
                    )).scalar_one_or_none()
                    if theme and theme.seed_tickers:
                        if isinstance(theme.seed_tickers, list):
                            theme_seed_tickers = list(theme.seed_tickers)

                profile, _ = await self._fmp.get_profile(state.ticker)
                sector = (profile or {}).get("sector")

                snapshot = outcome_tracker.build_research_run_signal_snapshot(
                    state=state, signals_row=signals_row, kill_states=[],
                )

                await outcome_tracker.record_verdict(
                    source_type="research_run",
                    source_id=run_id,
                    ticker=state.ticker,
                    theme_id=state.theme_id,
                    theme_seed_tickers=theme_seed_tickers,
                    sector=sector,
                    verdict=state.status,
                    verdict_emitted_at=_coerce_to_datetime(state.completed_at) or datetime.now(timezone.utc),
                    signal_snapshot=snapshot,
                    fmp=self._fmp,
                    db=db,
                )
        except Exception:
            logger.exception("record_verdict failed for run %s", run_id)

    async def _fetch_filing_sections(self, ticker: str) -> dict:
        """Return {section_key: {...}} for the most recent ingested sections.

        Read-only. Phase A ingest is not triggered here — sections land in the
        DB via manual POST /api/filings/ingest/{ticker}. If nothing has been
        ingested yet for this ticker, returns {} and the deep-dive prompts
        render without filing excerpts.

        Uses a dedicated session so intra-phase SQL doesn't autobegin a
        transaction on the phase-level session (see `_fetch_edgar_facts`).
        """
        all_keys: set[str] = set()
        for keys in FILING_EXCERPT_ROUTING.values():
            all_keys.update(keys)
        async with async_session() as s:
            try:
                return await edgar_sections_ingest.get_latest_sections_by_keys(
                    ticker, all_keys, s
                )
            except Exception as e:
                logger.warning("[%s] Filing-section fetch failed: %s", ticker, e)
                return {}

    async def _fetch_counterparty_context(self, ticker: str) -> CounterpartyContext:
        """Return a CounterpartyContext for the deep-dive prompt.

        Read-only: queries the relationships table (populated by the
        Phase B extractor + on-demand fan-out). Uses a dedicated
        session, same rationale as `_fetch_filing_sections`.

        Returns an empty context if nothing has been extracted for this
        ticker yet — the prompt renderer will then no-op the slot.
        """
        async with async_session() as s:
            try:
                return await get_counterparty_context(ticker, s)
            except Exception as e:
                logger.warning("[%s] Counterparty-context fetch failed: %s", ticker, e)
                return CounterpartyContext()

    async def _fetch_edgar_facts(self, ticker: str) -> tuple[dict, list]:
        """Ingest (best-effort) + return ({concept: [fact,...]}, citations).

        Uses a dedicated session so intra-phase SQL doesn't autobegin a
        transaction on the phase-level `db` session (which would collide with
        the `async with db.begin():` persist block in `_run_phase`).

        Citations identify the SEC endpoints used so the caller can persist
        them onto ResearchState and surface them in the Library citation panel.
        If the EDGAR client is unavailable or ingestion fails, returns ({}, []).
        """
        if self._edgar is None:
            return {}, []

        citations: list = []
        async with async_session() as s:
            # Ingest is best-effort — log and continue on any failure so EDGAR
            # outages don't break the pipeline.
            try:
                _summary, citations = await edgar_ingest.ingest_ticker_facts(ticker, s, self._edgar)
                await s.commit()
            except Exception as e:
                await s.rollback()
                logger.warning("[%s] EDGAR ingest failed: %s", ticker, e)

            all_concepts: set[str] = set()
            for cs in EDGAR_ROUTING.values():
                all_concepts.update(cs)
            try:
                facts = await edgar_ingest.get_recent_facts_by_concept(ticker, all_concepts, s)
                return facts, citations
            except Exception as e:
                logger.warning("[%s] EDGAR fact fetch failed: %s", ticker, e)
                return {}, citations

    async def _fetch_signals(self, ticker: str, theme_id: str) -> dict:
        """Return latest {signal_type: value} dict for a ticker+theme.

        Uses a dedicated session (see `_fetch_edgar_facts` for why). Empty
        dict when no signals exist (e.g., daily refresh hasn't run yet).
        """
        async with async_session() as s:
            result = await s.execute(
                select(Signal).where(
                    Signal.ticker == ticker,
                    Signal.theme_id == theme_id,
                )
            )
            rows = result.scalars().all()
            return {row.signal_type: row.value for row in rows}

    async def _run_deep_dive_with_streaming(
        self, state: ResearchState, run_id: str, db: AsyncSession
    ) -> ResearchState:
        """Deep dive with per-category progress events."""
        categories = (
            state.loop_context.get("categories", [])
            if state.loop_context else None
        )
        # Intra-phase SQL must NOT run on `db` — that session is reserved
        # for the post-phase `async with db.begin():` persist block in
        # _run_phase. Executing SQL on `db` here would autobegin a
        # transaction and collide with that block. Use fresh sessions.
        signals = await self._fetch_signals(state.ticker, state.theme_id)
        edgar_facts, edgar_citations = await self._fetch_edgar_facts(state.ticker)
        filing_sections = await self._fetch_filing_sections(state.ticker)
        counterparty_context = await self._fetch_counterparty_context(state.ticker)
        # Persist SEC source citations so they appear in the Library citation
        # panel alongside FMP / FRED / X.
        from backend.app.graph.state import StateCitation
        for cit in edgar_citations:
            state.add_citation(StateCitation.from_citation(cit))
        state = await nodes.node_deep_dive(
            state, self._fmp, self._fred, signals, edgar_facts, filing_sections,
            counterparty_context=counterparty_context,
        )

        # Emit start event with curated financials (available after node runs)
        self._emit(run_id, {
            "type": "deep_dive_start",
            "categories": categories or ["all 9 categories"],
            "loop_count": state.loop_count,
            "loop_context": state.loop_context,
            "curated_financials": state.curated_financials,
            "transcript_analysis": state.transcript_analysis,
            "edgar_facts": edgar_facts,
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
