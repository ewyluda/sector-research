"""Pipeline API endpoints.

POST /api/runs                    — Start a new research run
GET  /api/runs/{run_id}           — Get run state + phase outputs
POST /api/runs/{run_id}/advance   — Approve / flag / stop at an interrupt
GET  /api/runs/{run_id}/stream    — SSE: real-time phase output streaming
GET  /api/runs                    — List all runs (Research Library)
GET  /api/runs/{run_id}/report    — Full report for completed run
"""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.research_run import ResearchRun
from backend.app.models.signal import Signal
from backend.app.graph.state import ResearchState
from backend.app.models.theme import Theme
from backend.app.services.data_gaps import compute_data_gaps, aggregate_data_gaps

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
    theme_name: str | None = None
    phase: str
    status: str
    loop_count: int
    conviction_score: int | None = None
    thesis_status: str | None = None
    gap_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_to_summary(run: ResearchRun, theme_name: str | None = None) -> dict:
    state = run.state or {}
    return {
        "id": run.id,
        "ticker": run.ticker,
        "theme_id": run.theme_id,
        "theme_name": theme_name,
        "phase": run.phase,
        "status": run.status,
        "loop_count": run.loop_count,
        "conviction_score": state.get("conviction_score"),
        "thesis_status": state.get("thesis_status"),
        "gap_count": len(compute_data_gaps(state)),
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
    asyncio.create_task(pipeline._run_phase(run.id, state, db))

    return _run_to_detail(run)


@router.get("/runs")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    theme_id: str | None = None,
    ticker: str | None = None,
    search: str | None = None,
    limit: int = 50,
):
    """List all research runs for the Research Library."""
    query = (
        select(ResearchRun, Theme.name.label("theme_name"))
        .outerjoin(Theme, ResearchRun.theme_id == Theme.id)
        .order_by(desc(ResearchRun.created_at))
        .limit(limit)
    )
    if status:
        query = query.where(ResearchRun.status == status)
    if theme_id:
        query = query.where(ResearchRun.theme_id == theme_id)
    if ticker:
        query = query.where(func.lower(ResearchRun.ticker) == ticker.lower())
    elif search:
        escaped = search.replace("%", r"\%").replace("_", r"\_")
        query = query.where(ResearchRun.ticker.ilike(f"%{escaped}%", escape="\\"))

    result = await db.execute(query)
    rows = result.all()
    return [_run_to_summary(run, theme_name=tn) for run, tn in rows]


@router.get("/runs/data-gaps")
async def get_data_gaps(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    theme_id: str | None = None,
    ticker: str | None = None,
):
    """Aggregate data gaps across all runs, ranked by frequency."""
    query = select(ResearchRun)
    if status:
        query = query.where(ResearchRun.status == status)
    if theme_id:
        query = query.where(ResearchRun.theme_id == theme_id)
    if ticker:
        query = query.where(func.lower(ResearchRun.ticker) == ticker.lower())

    result = await db.execute(query)
    runs_list = [
        (run.ticker, run.state or {}) for run in result.scalars().all()
    ]

    return aggregate_data_gaps(runs_list)


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
    On completed runs, approve triggers position monitor.
    """
    pipeline = request.app.state.pipeline

    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # If run is completed and action is approve, trigger position monitor
    if run.status == "completed" and payload.action == "approve":
        state = ResearchState.from_dict(run.state)
        state.status = "in_progress"
        state.phase = "position_monitor"
        run.phase = "position_monitor"
        run.status = "in_progress"
        run.state = state.to_dict()
        await db.commit()
        asyncio.create_task(pipeline._run_phase(run.id, state, db))
        return _run_to_detail(run)

    # Reject advance on non-advanceable states
    if run.status in ("error", "in_progress"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot advance run in '{run.status}' state",
        )

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

    # Fetch EDGAR XBRL facts for this ticker (Tier 3 v1 data)
    from backend.app.models.filing import XBRLFact
    edgar_result = await db.execute(
        select(XBRLFact)
        .where(XBRLFact.ticker == run.ticker.upper())
        .order_by(XBRLFact.period_end.desc())
    )
    edgar_facts: dict[str, list[dict]] = {}
    for row in edgar_result.scalars().all():
        bucket = edgar_facts.setdefault(row.concept, [])
        if len(bucket) >= 12:
            continue
        bucket.append({
            "value": float(row.value),
            "unit": row.unit,
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "fiscal_year": row.fiscal_year,
            "fiscal_period": row.fiscal_period,
        })

    # Fetch X signal velocity for this ticker+theme
    x_signal_velocity = None
    sig_result = await db.execute(
        select(Signal).where(
            Signal.ticker == run.ticker,
            Signal.theme_id == run.theme_id,
            Signal.signal_type == "velocity",
        )
    )
    sig = sig_result.scalar_one_or_none()
    if sig:
        val = sig.value or {}
        x_signal_velocity = {
            "ratio": val.get("ratio"),
            "count_7d": val.get("count_7d"),
            "count_30d_approx": val.get("count_30d_approx"),
            "direction": val.get("direction"),
            "is_stale": sig.is_stale,
            "computed_at": sig.computed_at.isoformat() if sig.computed_at else None,
        }

    # Tier 2.6: kill-criterion state hydration for the report-page toggle UI.
    from backend.app.models import KillCriterionState
    kc_result = await db.execute(
        select(KillCriterionState)
        .where(KillCriterionState.run_id == run_id)
        .order_by(KillCriterionState.ordinal)
    )
    kill_criterion_states = [
        {
            "ordinal": s.ordinal,
            "status": s.status,
            "flipped_at": s.flipped_at.isoformat(),
            "note": s.note,
        }
        for s in kc_result.scalars()
    ]

    # Tier 1.2: question-log rows linked to this run via either created_run_id
    # or resolved_run_id (so resurfaced answers from prior runs show up too).
    from backend.app.models.question import Question
    from backend.app.api.questions import _serialize as _serialize_question
    from sqlalchemy import or_
    q_result = await db.execute(
        select(Question)
        .where(or_(Question.created_run_id == run_id, Question.resolved_run_id == run_id))
        .order_by(Question.priority.asc(), Question.created_at.desc())
    )
    questions_payload = [_serialize_question(q).model_dump() for q in q_result.scalars().all()]

    return {
        "run_id": run_id,
        "ticker": run.ticker,
        "theme_id": run.theme_id,
        "status": run.status,
        "conviction_score": state.get("conviction_score", 0),
        "thesis_status": state.get("thesis_status", "PENDING"),
        "loop_count": run.loop_count,
        "x_signal_velocity": x_signal_velocity,
        "kill_criterion_states": kill_criterion_states,
        "questions": questions_payload,
        "phases": {
            "quick_screen": phase_outputs.get("quick_screen", {}),
            "deep_dive": {
                "categories": {
                    k: v for k, v in phase_outputs.items()
                    if k not in ("quick_screen", "thesis", "risk", "position")
                },
                "curated_financials": state.get("curated_financials"),
                "transcript_analysis": state.get("transcript_analysis"),
                "edgar_facts": edgar_facts,
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
