"""WorkspaceService — orchestrates the 5-step workspace loop. Mirrors PipelineService."""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import unit_of_work
from backend.app.models.workspace_run import WorkspaceRun
from backend.app.models.signal import Signal
from backend.app.models.kill_criterion_state import KillCriterionState
from backend.app.services import outcome_tracker
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.services.workspace_steps import run_steps_in_sequence

logger = logging.getLogger(__name__)


class WorkspaceRunInFlight(Exception):
    """A workspace run is already running for this ticker."""

    def __init__(self, *, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"workspace run {run_id} already in flight")


@dataclass
class PreflightStatus:
    """Read-only DTO describing whether a workspace run can be kicked off.

    `missing` is a list of stable string codes the frontend can map to copy:
      - "no_completed_research_run"
      - "research_run_not_completed"
      - "research_run_ticker_mismatch"
      - "no_ticker_model"
      - "unsaved_model_draft"
      - "workspace_run_in_flight"
    `in_flight_run_id` is populated when "workspace_run_in_flight" is in missing
    so the frontend can deep-link to the running report instead of starting a new one.
    """
    ok: bool
    missing: list[str] = field(default_factory=list)
    in_flight_run_id: str | None = None


class WorkspaceService:
    """Orchestrator for /workspace runs. Mirrors PipelineService."""

    def __init__(self, *, fmp: Any, edgar: Any, anthropic: Any) -> None:
        self._fmp = fmp
        self._edgar = edgar
        self._anthropic = anthropic
        self._queues: dict[str, asyncio.Queue] = {}
        self._ticker_locks: dict[str, asyncio.Lock] = {}
        self._ticker_locks_guard = asyncio.Lock()

    # ── SSE plumbing ───────────────────────────────────────────────────────────

    def _get_or_create_queue(self, run_id: str) -> asyncio.Queue:
        q = self._queues.get(run_id)
        if q is None:
            q = asyncio.Queue()
            self._queues[run_id] = q
        return q

    def _emit(self, run_id: str, event: dict) -> None:
        """Push an event to the SSE queue for this run."""
        queue = self._get_or_create_queue(run_id)
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("workspace SSE queue full for run %s; dropping event", run_id)

    async def event_stream(self, run_id: str) -> AsyncIterator[dict]:
        """Async generator yielding raw event dicts until a terminal event."""
        queue = self._get_or_create_queue(run_id)
        terminal = {"workspace_run_complete", "workspace_run_failed"}
        while True:
            evt = await queue.get()
            yield evt
            if evt.get("type") in terminal:
                # Drain any remaining queued events
                while not queue.empty():
                    yield queue.get_nowait()
                return

    # ── Per-ticker concurrency guard ───────────────────────────────────────────

    def _acquire_ticker_lock(self, ticker: str):
        """Async context manager that serializes kick_off per ticker.

        Two concurrent kick_off() calls for the same ticker would otherwise both
        pass the draft-absence check before either INSERT lands, allowing the
        second run to race the first model-version write and surface a
        (ticker, version) IntegrityError. The lock pins them to single-file
        execution within this process; horizontal scaling is not a concern
        (single-process local tool).
        """
        svc = self
        ticker = ticker.upper()

        class _LockCtx:
            async def __aenter__(self_inner):
                async with svc._ticker_locks_guard:
                    lock = svc._ticker_locks.get(ticker)
                    if lock is None:
                        lock = asyncio.Lock()
                        svc._ticker_locks[ticker] = lock
                self_inner._lock = lock
                await lock.acquire()
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                self_inner._lock.release()

        return _LockCtx()

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    async def kick_off(self, ticker: str, *, research_run_id: str | None = None) -> str:
        """Create the workspace_runs row and start the background task. Returns run_id.

        Holds a per-ticker asyncio.Lock across preflight + INSERT to prevent
        two parallel callers from both passing the draft-absent check.
        """
        async with self._acquire_ticker_lock(ticker):
            try:
                async with unit_of_work() as db:
                    in_flight = (await db.execute(
                        select(WorkspaceRun)
                        .where(WorkspaceRun.ticker == ticker, WorkspaceRun.status == "running")
                        .order_by(WorkspaceRun.created_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if in_flight is not None:
                        raise WorkspaceRunInFlight(run_id=str(in_flight.id))

                    ctx_data = await self._preflight(db, ticker, research_run_id=research_run_id)
                    run_id = str(uuid4())
                    row = WorkspaceRun(
                        id=run_id,
                        ticker=ticker,
                        parent_research_run_id=str(ctx_data["research_run"].id),
                        ticker_model_version_before=ctx_data["ticker_model"].version,
                        status="running",
                        step_outputs={},
                        citations=[],
                    )
                    db.add(row)
            except IntegrityError:
                in_flight_id = await self._find_in_flight_run_id(ticker)
                if in_flight_id is not None:
                    raise WorkspaceRunInFlight(run_id=in_flight_id)
                raise

        asyncio.create_task(
            self._run_workspace(
                run_id=run_id,
                ticker=ticker,
                db_factory=unit_of_work,
                research_run_id=str(ctx_data["research_run"].id),
            )
        )
        return run_id

    async def _find_in_flight_run_id(self, ticker: str) -> str | None:
        async with unit_of_work() as db:
            row = (await db.execute(
                select(WorkspaceRun)
                .where(WorkspaceRun.ticker == ticker, WorkspaceRun.status == "running")
                .order_by(WorkspaceRun.created_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            return str(row.id) if row is not None else None

    async def _gather_preflight_facts(
        self,
        db: AsyncSession,
        ticker: str,
        *,
        research_run_id: str | None = None,
    ) -> dict:
        """Single DB pass collecting every fact the preflight needs.

        Returns a dict of booleans + the optional in-flight run id. Callers
        decide whether to raise (kick_off path) or return a DTO (HTTP preflight).
        """
        from backend.app.models import ResearchRun, TickerModel, TickerModelDraft

        if research_run_id is not None:
            rr = (await db.execute(
                select(ResearchRun).where(ResearchRun.id == research_run_id)
            )).scalar_one_or_none()
            rr_found = rr is not None
            rr_completed = bool(rr and rr.status == "completed")
            rr_ticker_matches = bool(rr and rr.ticker == ticker)
        else:
            rr = (await db.execute(
                select(ResearchRun)
                .where(ResearchRun.ticker == ticker, ResearchRun.status == "completed")
                .order_by(ResearchRun.updated_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            rr_found = rr is not None
            rr_completed = rr_found  # filtered in the query
            rr_ticker_matches = rr_found

        tm = (await db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ticker)
            .order_by(TickerModel.version.desc())
            .limit(1)
        )).scalar_one_or_none()

        draft = (await db.execute(
            select(TickerModelDraft).where(TickerModelDraft.ticker == ticker).limit(1)
        )).scalar_one_or_none()

        in_flight = (await db.execute(
            select(WorkspaceRun)
            .where(WorkspaceRun.ticker == ticker, WorkspaceRun.status == "running")
            .order_by(WorkspaceRun.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        return {
            "research_run": rr,
            "ticker_model": tm,
            "research_run_found": rr_found,
            "research_run_completed": rr_completed,
            "research_run_ticker_matches": rr_ticker_matches,
            "ticker_model_found": tm is not None,
            "draft_present": draft is not None,
            "in_flight_run_id": str(in_flight.id) if in_flight is not None else None,
        }

    async def check_preflight(
        self,
        *,
        db: AsyncSession,
        ticker: str,
        research_run_id: str | None = None,
    ) -> PreflightStatus:
        """Non-raising preflight check for UI use."""
        facts = await self._gather_preflight_facts(db, ticker, research_run_id=research_run_id)
        missing: list[str] = []
        if not facts["research_run_found"]:
            missing.append("no_completed_research_run")
        elif not facts["research_run_completed"]:
            missing.append("research_run_not_completed")
        elif not facts["research_run_ticker_matches"]:
            missing.append("research_run_ticker_mismatch")
        if not facts["ticker_model_found"]:
            missing.append("no_ticker_model")
        if facts["draft_present"]:
            missing.append("unsaved_model_draft")
        if facts["in_flight_run_id"] is not None:
            missing.append("workspace_run_in_flight")
        return PreflightStatus(
            ok=len(missing) == 0,
            missing=missing,
            in_flight_run_id=facts["in_flight_run_id"],
        )

    async def _preflight(
        self,
        db: AsyncSession,
        ticker: str,
        *,
        research_run_id: str | None = None,
    ) -> dict:
        """Raising preflight used by kick_off / _build_context. Returns {research_run, ticker_model}."""
        facts = await self._gather_preflight_facts(db, ticker, research_run_id=research_run_id)
        if not facts["research_run_found"]:
            if research_run_id is not None:
                raise ValueError(f"research_run {research_run_id} not found")
            raise ValueError(f"no completed research_run for ticker {ticker}")
        if not facts["research_run_ticker_matches"]:
            raise ValueError(
                f"research_run {research_run_id} ticker {facts['research_run'].ticker} != requested ticker {ticker}"
            )
        if not facts["research_run_completed"]:
            raise ValueError(
                f"research_run {research_run_id} status is {facts['research_run'].status}; must be completed"
            )
        if not facts["ticker_model_found"]:
            raise ValueError(f"no ticker_model exists for ticker {ticker}; initialize one first")
        if facts["draft_present"]:
            raise ValueError(
                f"unsaved model draft exists for ticker {ticker}; save or discard it before workspace refresh"
            )
        return {"research_run": facts["research_run"], "ticker_model": facts["ticker_model"]}

    async def _build_context(
        self,
        db: AsyncSession,
        run_id: str,
        ticker: str,
        *,
        research_run_id: str | None = None,
    ) -> WorkspaceContext:
        ctx_data = await self._preflight(db, ticker, research_run_id=research_run_id)
        return WorkspaceContext(
            run_id=run_id,
            ticker=ticker,
            db=db,
            fmp=self._fmp,
            edgar=self._edgar,
            anthropic=self._anthropic,
            prior_research_run=ctx_data["research_run"],
            prior_ticker_model=ctx_data["ticker_model"],
            emit=lambda evt: self._emit(run_id, evt),
        )

    async def _persist_run(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        status: str,
        verdict: str | None,
        step_outputs: dict,
        error: str | None = None,
        version_after: int | None = None,
    ) -> None:
        await db.execute(
            update(WorkspaceRun)
            .where(WorkspaceRun.id == run_id)
            .values(
                status=status,
                verdict=verdict,
                step_outputs=step_outputs,
                error=error,
                ticker_model_version_after=version_after,
                updated_at=datetime.now(timezone.utc),
            )
        )

    async def _run_workspace(
        self,
        *,
        run_id: str,
        ticker: str,
        db_factory: Callable,
        research_run_id: str | None = None,
    ) -> None:
        emit = lambda evt: self._emit(run_id, evt)  # noqa: E731
        emit({"type": "workspace_run_start", "run_id": run_id, "ticker": ticker})
        try:
            async with db_factory() as db:
                ctx = await self._build_context(
                    db, run_id, ticker, research_run_id=research_run_id
                )
                outputs = await run_steps_in_sequence(ctx, emit)

            version_after = outputs.get("update_refresh", {}).get("version_after")
            verdict_str = outputs.get("challenge", {}).get("proposed_verdict")
            had_step_error = any(
                isinstance(v, dict) and "error" in v for v in outputs.values()
            )
            final_status = "partial" if had_step_error else "completed"

            async with unit_of_work() as write_db:
                await self._persist_run(
                    write_db, run_id,
                    status=final_status, verdict=verdict_str,
                    step_outputs=outputs, version_after=version_after,
                )

            if final_status == "completed" and verdict_str:
                # Fire-and-forget: outcome recording makes ~N+3 serial FMP
                # calls and must not block the workspace_run_complete SSE
                # emit. Inner function logs and swallows all errors.
                asyncio.create_task(self._record_workspace_outcome(
                    run_id=run_id, verdict=verdict_str, outputs=outputs,
                ))

            emit({"type": "workspace_run_complete", "verdict": verdict_str,
                  "version_after": version_after, "status": final_status})

        except asyncio.CancelledError:
            try:
                async with unit_of_work() as write_db:
                    await self._persist_run(
                        write_db, run_id, status="failed",
                        verdict=None, step_outputs={}, error="cancelled",
                    )
            finally:
                emit({"type": "workspace_run_failed", "error": "cancelled"})
            raise

        except Exception as e:  # noqa: BLE001
            logger.exception("workspace run %s failed", run_id)
            try:
                async with unit_of_work() as write_db:
                    await self._persist_run(
                        write_db, run_id, status="failed",
                        verdict=None, step_outputs={}, error=str(e),
                    )
            finally:
                emit({"type": "workspace_run_failed", "error": str(e)})

    async def _record_workspace_outcome(
        self, *, run_id: str, verdict: str, outputs: dict
    ) -> None:
        """Best-effort: record the workspace verdict in verdict_outcomes."""
        try:
            async with unit_of_work() as db:
                run = (await db.execute(
                    select(WorkspaceRun).where(WorkspaceRun.id == run_id)
                )).scalar_one_or_none()
                if run is None:
                    return

                theme_id: str | None = None
                theme_seed_tickers: list[str] | None = None
                if run.parent_research_run_id:
                    from backend.app.models.research_run import ResearchRun
                    from backend.app.models.theme import Theme
                    parent = (await db.execute(
                        select(ResearchRun).where(ResearchRun.id == run.parent_research_run_id)
                    )).scalar_one_or_none()
                    if parent and parent.theme_id:
                        theme_id = parent.theme_id
                        theme = (await db.execute(
                            select(Theme).where(Theme.id == theme_id)
                        )).scalar_one_or_none()
                        if theme and theme.seed_tickers and isinstance(theme.seed_tickers, list):
                            theme_seed_tickers = list(theme.seed_tickers)

                signals_row: dict | None = None
                if theme_id:
                    sig_rows = (await db.execute(
                        select(Signal).where(
                            Signal.ticker == run.ticker,
                            Signal.theme_id == theme_id,
                        )
                    )).scalars().all()
                    if sig_rows:
                        signals_row = {r.signal_type: r.value for r in sig_rows}

                kill_rows = []
                if run.parent_research_run_id:
                    kill_rows = (await db.execute(
                        select(KillCriterionState).where(
                            KillCriterionState.run_id == run.parent_research_run_id
                        )
                    )).scalars().all()
                kill_states = [
                    {"ordinal": r.ordinal, "state": r.status} for r in kill_rows
                ]

                model_assumptions: dict | None = None
                from backend.app.models import TickerModel
                tm = (await db.execute(
                    select(TickerModel)
                    .where(TickerModel.ticker == run.ticker)
                    .order_by(TickerModel.version.desc())
                    .limit(1)
                )).scalar_one_or_none()
                if tm and tm.state:
                    model_assumptions = (tm.state or {}).get("assumptions") or {}

                profile, _ = await self._fmp.get_company_profile(run.ticker)
                sector = (profile or {}).get("sector")

                snapshot = outcome_tracker.build_workspace_run_signal_snapshot(
                    run=run, signals_row=signals_row, kill_states=kill_states,
                    model_assumptions=model_assumptions,
                )

                await outcome_tracker.record_verdict(
                    source_type="workspace_run",
                    source_id=run_id,
                    ticker=run.ticker,
                    theme_id=theme_id,
                    theme_seed_tickers=theme_seed_tickers,
                    sector=sector,
                    verdict=verdict,
                    verdict_emitted_at=run.updated_at or datetime.now(timezone.utc),
                    signal_snapshot=snapshot,
                    fmp=self._fmp,
                    db=db,
                )
        except Exception:
            logger.exception("record_verdict failed for workspace run %s", run_id)
