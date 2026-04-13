"""Pipeline API endpoints.

POST /api/runs                    — Start a new research run
GET  /api/runs/{run_id}           — Get run state + phase outputs
POST /api/runs/{run_id}/advance   — Approve / flag / stop at an interrupt
GET  /api/runs/{run_id}/stream    — SSE: real-time phase output streaming
GET  /api/runs                    — List all runs (Research Library)
GET  /api/runs/{run_id}/report    — Full report for completed run
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.research_run import ResearchRun
from backend.app.graph.state import ResearchState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipeline"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    ticker: str
    theme_id: str


class AdvanceRunRequest(BaseModel):
    action: Literal["approve", "flag", "stop"]
    feedback: str | None = None


class RunSummary(BaseModel):
    id: str
    ticker: str
    theme_id: str
    phase: str
    status: str
    loop_count: int
    conviction_score: int | None = None
    thesis_status: str | None = None

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_to_summary(run: ResearchRun) -> dict:
    state = run.state or {}
    return {
        "id": run.id,
        "ticker": run.ticker,
        "theme_id": run.theme_id,
        "phase": run.phase,
        "status": run.status,
        "loop_count": run.loop_count,
        "conviction_score": state.get("conviction_score"),
        "thesis_status": state.get("thesis_status"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }


def _run_to_detail(run: ResearchRun) -> dict:
    state = run.state or {}
    return {
        **_run_to_summary(run),
        "phase_outputs": state.get("phase_outputs", {}),
        "scores": state.get("scores", {}),
        "human_feedback": state.get("human_feedback", {}),
        "flags": state.get("flags", []),
        "loop_context": state.get("loop_context"),
        "citations": state.get("citations", []),
        "failed_categories": _get_failed_categories(state),
    }


def _get_failed_categories(state: dict) -> list[str]:
    return [
        k for k, v in state.get("phase_outputs", {}).items()
        if isinstance(v, dict) and v.get("__type__") == "CategoryError"
    ]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/runs", status_code=201)
async def start_run(
    payload: StartRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Start a new research run. Immediately begins quick_screen phase."""
    pipeline = request.app.state.pipeline

    run = await pipeline.create_run(
        ticker=payload.ticker,
        theme_id=payload.theme_id,
        db=db,
    )

    # Load initial state and kick off quick_screen in background
    state = ResearchState.from_dict(run.state)
    import asyncio
    asyncio.create_task(pipeline._run_phase(run.id, state, db))

    return _run_to_detail(run)


@router.get("/runs")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    theme_id: str | None = None,
    limit: int = 50,
):
    """List all research runs for the Research Library."""
    query = select(ResearchRun).order_by(desc(ResearchRun.created_at)).limit(limit)
    if status:
        query = query.where(ResearchRun.status == status)
    if theme_id:
        query = query.where(ResearchRun.theme_id == theme_id)

    result = await db.execute(query)
    runs = result.scalars().all()
    return [_run_to_summary(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Get full run state including phase outputs."""
    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_detail(run)


@router.post("/runs/{run_id}/advance")
async def advance_run(
    run_id: str,
    payload: AdvanceRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Human interrupt action: approve, flag with note, or stop.
    Advances the pipeline to the next phase.
    """
    pipeline = request.app.state.pipeline

    try:
        run = await pipeline.advance(
            run_id=run_id,
            action=payload.action,
            feedback=payload.feedback,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _run_to_detail(run)


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """
    SSE endpoint for real-time phase output streaming.
    Connect before calling /advance to receive tokens and events.
    """
    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    pipeline = request.app.state.pipeline

    return StreamingResponse(
        pipeline.event_stream(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/runs/{run_id}/report")
async def get_report(run_id: str, db: AsyncSession = Depends(get_db)):
    """
    Full structured report for a completed run.
    Used by /report/[runId] page and Obsidian export.
    """
    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    state = run.state or {}
    phase_outputs = state.get("phase_outputs", {})

    def get_content(key: str) -> str:
        output = phase_outputs.get(key, {})
        return output.get("content", "") if isinstance(output, dict) else ""

    return {
        "run_id": run_id,
        "ticker": run.ticker,
        "theme_id": run.theme_id,
        "status": run.status,
        "conviction_score": state.get("conviction_score", 0),
        "thesis_status": state.get("thesis_status", "PENDING"),
        "loop_count": run.loop_count,
        "phases": {
            "quick_screen": phase_outputs.get("quick_screen", {}),
            "deep_dive": {
                "categories": {
                    k: v for k, v in phase_outputs.items()
                    if k not in ("quick_screen", "thesis", "risk", "position")
                },
                "curated_financials": state.get("curated_financials"),
            },
            "thesis": phase_outputs.get("thesis", {}),
            "risk": phase_outputs.get("risk", {}),
            "position": phase_outputs.get("position", {}),
        },
        "scores": state.get("scores", {}),
        "human_feedback": state.get("human_feedback", {}),
        "flags": state.get("flags", []),
        "citations": state.get("citations", []),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,

        # Obsidian export metadata
        "obsidian": {
            "ticker": run.ticker,
            "theme_id": run.theme_id,
            "conviction_score": state.get("conviction_score", 0),
            "thesis_status": state.get("thesis_status", "PENDING"),
            "phase_reached": run.phase,
            "date_researched": run.created_at.strftime("%Y-%m-%d") if run.created_at else "",
            "loop_count": run.loop_count,
        },
    }
