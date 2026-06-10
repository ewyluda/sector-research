"""Status board endpoints.

GET  /api/status/board                                   — fleet view
POST /api/runs/{run_id}/archive                          — hide from board
POST /api/runs/{run_id}/unarchive                        — restore
GET  /api/runs/{run_id}/kill-criteria                    — hydrate toggles
PUT  /api/runs/{run_id}/kill-criteria/{ordinal}          — flip one criterion
"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models import KillCriterionState, ResearchRun
from backend.app.services.status_board import (
    NextCatalyst as ServiceNextCatalyst,
    StatusBoardEntry as ServiceEntry,
    build_status_board,
    upsert_kill_criterion_state as _upsert_kill_criterion_state,
)

router = APIRouter()


# ── Wire-format response shapes ─────────────────────────────────────────────


class KillCriteriaSummaryOut(BaseModel):
    total: int
    triggered: int


class NextCatalystOut(BaseModel):
    description: str
    type: str | None
    expected_date: str | None
    expected_window_end: str | None
    days_until: int | None


class MaterialEventsSummaryOut(BaseModel):
    count_14d: int
    max_materiality: str
    latest_headline: str


class StatusBoardEntryOut(BaseModel):
    ticker: str
    theme_id: str
    theme_name: str
    run_id: str
    thesis_status: str
    conviction_score: int | None
    completed_at: str
    days_since_update: int
    health: str
    health_reasons: list[str]
    next_catalyst: NextCatalystOut | None
    kill_criteria_summary: KillCriteriaSummaryOut
    material_events: MaterialEventsSummaryOut | None


class StatusBoardResponseOut(BaseModel):
    entries: list[StatusBoardEntryOut]
    total: int
    generated_at: str


class KillCriterionStateOut(BaseModel):
    ordinal: int
    status: Literal["armed", "triggered"]
    flipped_at: str
    note: str | None


class KillCriterionPutBody(BaseModel):
    status: Literal["armed", "triggered"]
    note: str | None = Field(default=None, max_length=2000)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_next_catalyst(c: ServiceNextCatalyst | None) -> NextCatalystOut | None:
    if c is None:
        return None
    return NextCatalystOut(
        description=c.description,
        type=c.type,
        expected_date=c.expected_date.isoformat() if c.expected_date else None,
        expected_window_end=c.expected_window_end.isoformat() if c.expected_window_end else None,
        days_until=c.days_until,
    )


def _serialize_entry(e: ServiceEntry) -> StatusBoardEntryOut:
    return StatusBoardEntryOut(
        ticker=e.ticker,
        theme_id=e.theme_id,
        theme_name=e.theme_name,
        run_id=e.run_id,
        thesis_status=e.thesis_status,
        conviction_score=e.conviction_score,
        completed_at=e.completed_at.isoformat(),
        days_since_update=e.days_since_update,
        health=e.health,
        health_reasons=e.health_reasons,
        next_catalyst=_serialize_next_catalyst(e.next_catalyst),
        kill_criteria_summary=KillCriteriaSummaryOut(
            total=e.kill_criteria_summary.total,
            triggered=e.kill_criteria_summary.triggered,
        ),
        material_events=(
            MaterialEventsSummaryOut(
                count_14d=e.material_events.count_14d,
                max_materiality=e.material_events.max_materiality,
                latest_headline=e.material_events.latest_headline,
            )
            if e.material_events
            else None
        ),
    )


def _serialize_kc_state(s: KillCriterionState) -> KillCriterionStateOut:
    return KillCriterionStateOut(
        ordinal=s.ordinal,
        status=s.status,  # type: ignore[arg-type]
        flipped_at=s.flipped_at.isoformat(),
        note=s.note,
    )


async def _get_run_or_404(db: AsyncSession, run_id: str) -> ResearchRun:
    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/status/board", response_model=StatusBoardResponseOut)
async def get_status_board(
    theme_id: str | None = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> StatusBoardResponseOut:
    response = await build_status_board(
        db, theme_id=theme_id, include_archived=include_archived
    )
    return StatusBoardResponseOut(
        entries=[_serialize_entry(e) for e in response.entries],
        total=response.total,
        generated_at=response.generated_at.isoformat(),
    )


@router.post("/runs/{run_id}/archive", status_code=204)
async def archive_run(run_id: str, db: AsyncSession = Depends(get_db)) -> None:
    run = await _get_run_or_404(db, run_id)
    run.archived_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/runs/{run_id}/unarchive", status_code=204)
async def unarchive_run(run_id: str, db: AsyncSession = Depends(get_db)) -> None:
    run = await _get_run_or_404(db, run_id)
    run.archived_at = None
    await db.commit()


@router.get(
    "/runs/{run_id}/kill-criteria",
    response_model=list[KillCriterionStateOut],
)
async def list_kill_criterion_states(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[KillCriterionStateOut]:
    await _get_run_or_404(db, run_id)
    result = await db.execute(
        select(KillCriterionState)
        .where(KillCriterionState.run_id == run_id)
        .order_by(KillCriterionState.ordinal)
    )
    return [_serialize_kc_state(s) for s in result.scalars()]


@router.put(
    "/runs/{run_id}/kill-criteria/{ordinal}",
    response_model=KillCriterionStateOut,
)
async def upsert_kill_criterion_state_endpoint(
    run_id: str,
    ordinal: int,
    body: KillCriterionPutBody,
    db: AsyncSession = Depends(get_db),
) -> KillCriterionStateOut:
    await _get_run_or_404(db, run_id)
    await _upsert_kill_criterion_state(
        db, run_id=run_id, ordinal=ordinal, status=body.status, note=body.note
    )
    await db.commit()
    result = await db.execute(
        select(KillCriterionState).where(
            KillCriterionState.run_id == run_id,
            KillCriterionState.ordinal == ordinal,
        )
    )
    state = result.scalar_one()
    return _serialize_kc_state(state)
