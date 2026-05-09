"""WorkspaceService — orchestrates the 5-step workspace loop. Mirrors PipelineService."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session, unit_of_work
from backend.app.models.workspace_run import WorkspaceRun
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.services.workspace_steps import run_steps_in_sequence

logger = logging.getLogger(__name__)


class WorkspaceService:
    """Orchestrator for /workspace runs. Mirrors PipelineService."""

    def __init__(self, *, fmp: Any, edgar: Any, anthropic: Any) -> None:
        self._fmp = fmp
        self._edgar = edgar
        self._anthropic = anthropic
        self._queues: dict[str, asyncio.Queue] = {}

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

    # ── Run lifecycle ─────────────────────────────────────────────────────────

    async def kick_off(self, ticker: str) -> str:
        """Create the workspace_runs row and start the background task. Returns run_id."""
        async with unit_of_work() as db:
            ctx_data = await self._preflight(db, ticker)
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

        asyncio.create_task(
            self._run_workspace(run_id=run_id, ticker=ticker, db_factory=async_session)
        )
        return run_id

    async def _preflight(self, db: AsyncSession, ticker: str) -> dict:
        """Verify the ticker has a completed research_run and a ticker_models row.

        Raises ValueError on missing prerequisites — caller maps to HTTP 400.
        """
        from backend.app.models import ResearchRun, TickerModel  # local import to avoid cycles

        rr = (await db.execute(
            select(ResearchRun)
            .where(ResearchRun.ticker == ticker, ResearchRun.status == "completed")
            .order_by(ResearchRun.updated_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if rr is None:
            raise ValueError(f"no completed research_run for ticker {ticker}")

        tm = (await db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ticker)
            .order_by(TickerModel.version.desc())
            .limit(1)
        )).scalar_one_or_none()
        if tm is None:
            raise ValueError(f"no ticker_model exists for ticker {ticker}; initialize one first")

        return {"research_run": rr, "ticker_model": tm}

    async def _build_context(self, db: AsyncSession, run_id: str, ticker: str) -> WorkspaceContext:
        ctx_data = await self._preflight(db, ticker)
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
        self, *, run_id: str, ticker: str, db_factory: Callable
    ) -> None:
        emit = lambda evt: self._emit(run_id, evt)  # noqa: E731
        emit({"type": "workspace_run_start", "run_id": run_id, "ticker": ticker})
        try:
            async with db_factory() as db:
                ctx = await self._build_context(db, run_id, ticker)
                outputs = await run_steps_in_sequence(ctx, emit)

            version_after = outputs.get("update_refresh", {}).get("version_after")
            verdict_str = outputs.get("challenge", {}).get("proposed_verdict")

            async with unit_of_work() as write_db:
                await self._persist_run(
                    write_db, run_id,
                    status="completed", verdict=verdict_str,
                    step_outputs=outputs, version_after=version_after,
                )
            emit({"type": "workspace_run_complete", "verdict": verdict_str,
                  "version_after": version_after})

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
