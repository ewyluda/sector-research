"""Workspace API — kick off and monitor workspace loop runs."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.models.workspace_run import WorkspaceRun
from backend.app.services.workspace import WorkspaceService, WorkspaceRunInFlight

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def get_workspace_service(request: Request) -> WorkspaceService:
    svc = getattr(request.app.state, "workspace", None)
    if svc is None:
        raise HTTPException(status_code=500, detail="workspace service not initialized")
    return svc


@router.post("/{ticker}/runs", status_code=202)
async def kick_off_workspace(
    ticker: Ticker = Depends(TickerPath),
    research_run_id: str | None = None,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    try:
        run_id = await svc.kick_off(ticker=ticker, research_run_id=research_run_id)
    except WorkspaceRunInFlight as e:
        raise HTTPException(
            status_code=409,
            detail={"run_id": e.run_id, "message": "workspace run already in flight for this ticker"},
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"run_id": run_id}


@router.get("/runs/{run_id}")
async def get_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(WorkspaceRun).where(WorkspaceRun.id == str(run_id))
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="workspace run not found")
    return _serialize_run(row)


@router.get("/{ticker}/preflight")
async def preflight(
    ticker: Ticker = Depends(TickerPath),
    research_run_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    svc: WorkspaceService = Depends(get_workspace_service),
):
    status = await svc.check_preflight(db=db, ticker=ticker, research_run_id=research_run_id)
    return {
        "ok": status.ok,
        "missing": status.missing,
        "in_flight_run_id": status.in_flight_run_id,
    }


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: UUID,
    svc: WorkspaceService = Depends(get_workspace_service),
):
    async def gen():
        try:
            async for evt in svc.event_stream(str(run_id)):
                yield f"data: {json.dumps(evt)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{ticker}/history")
async def history_for_ticker(
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
    limit: int = 30,
):
    rows = (await db.execute(
        select(WorkspaceRun)
        .where(WorkspaceRun.ticker == ticker)
        .order_by(WorkspaceRun.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_serialize_run(r) for r in rows]


@router.get("/recent")
async def recent_runs(db: AsyncSession = Depends(get_db), limit: int = 30):
    rows = (await db.execute(
        select(WorkspaceRun)
        .order_by(WorkspaceRun.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_serialize_run(r) for r in rows]


def _serialize_run(r: WorkspaceRun) -> dict:
    return {
        "id": str(r.id),
        "ticker": r.ticker,
        "parent_research_run_id": (
            str(r.parent_research_run_id) if r.parent_research_run_id else None
        ),
        "ticker_model_version_before": r.ticker_model_version_before,
        "ticker_model_version_after": r.ticker_model_version_after,
        "status": r.status,
        "verdict": r.verdict,
        "step_outputs": r.step_outputs,
        "citations": r.citations,
        "error": r.error,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
