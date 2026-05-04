"""GET /api/catalysts and GET /api/catalysts/{id}.

Returns proximity-bucketed catalysts from the latest completed thesis
run per ticker. Same endpoint serves both the fleet view (no ticker
filter) and the per-ticker view inside /pipeline/[runId].
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.catalyst import Catalyst

router = APIRouter()


class CatalystRow(BaseModel):
    id: str                         # SQLAlchemy stores as UUID(as_uuid=False) → str
    run_id: str
    ticker: str
    ordinal: int
    timeframe: str
    description: str
    type: str | None
    signposts: list[str]
    linked_pillar: str | None
    expected_date: date | None
    expected_window_start: date | None
    expected_window_end: date | None
    date_source: str
    created_at: datetime

    @classmethod
    def from_orm_row(cls, row: Catalyst) -> "CatalystRow":
        return cls(
            id=row.id,
            run_id=row.run_id,
            ticker=row.ticker,
            ordinal=row.ordinal,
            timeframe=row.timeframe,
            description=row.description,
            type=row.type,
            signposts=list(row.signposts or []),
            linked_pillar=row.linked_pillar,
            expected_date=row.expected_date,
            expected_window_start=row.expected_window_start,
            expected_window_end=row.expected_window_end,
            date_source=row.date_source,
            created_at=row.created_at,
        )


class CatalystBuckets(BaseModel):
    this_week: list[CatalystRow]
    next_30d: list[CatalystRow]
    next_90d: list[CatalystRow]
    later: list[CatalystRow]
    untimed: list[CatalystRow]


class CatalystListResponse(BaseModel):
    buckets: CatalystBuckets
    total: int


def _bucket(row: CatalystRow, today: date) -> str:
    if row.expected_date is None:
        return "untimed"
    days = (row.expected_date - today).days
    if days < 0:
        return "passed"  # filtered out before bucketing
    if days <= 7:
        return "this_week"
    if days <= 30:
        return "next_30d"
    if days <= 90:
        return "next_90d"
    return "later"


@router.get("/catalysts", response_model=CatalystListResponse)
async def list_catalysts(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> CatalystListResponse:
    """Catalysts from the latest completed thesis run per ticker.

    If `ticker` is supplied, restricts to that ticker.
    """
    today = datetime.now(timezone.utc).date()

    # Latest completed-thesis run per ticker. We treat a run as having
    # completed thesis-construction if state.phase_outputs.thesis.structured
    # exists and is non-null (matches what the upsert path needs to fire).
    # `phase_outputs` is a key inside the JSONB `state` column, not a
    # top-level column.
    #
    # Note: asyncpg can't infer the type of a parameter used only in
    # `:ticker IS NULL OR c.ticker = :ticker`, so we conditionally append
    # the filter clause and only bind :ticker when needed.
    where_clause = ""
    params: dict[str, str] = {}
    if ticker is not None:
        where_clause = "WHERE c.ticker = :ticker"
        params["ticker"] = ticker

    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (ticker) id, ticker, created_at
            FROM research_runs
            WHERE state->'phase_outputs'->'thesis'->'structured' IS NOT NULL
            ORDER BY ticker, created_at DESC
        )
        SELECT c.*
        FROM catalysts c
        JOIN latest l ON c.run_id = l.id
        {where_clause}
        ORDER BY
            (c.expected_date IS NULL),
            c.expected_date NULLS LAST,
            c.ticker,
            c.ordinal
    """
    result = await db.execute(text(sql), params)
    rows = result.mappings().all()

    catalysts: list[CatalystRow] = []
    for row in rows:
        catalysts.append(CatalystRow(
            id=row["id"],
            run_id=row["run_id"],
            ticker=row["ticker"],
            ordinal=row["ordinal"],
            timeframe=row["timeframe"],
            description=row["description"],
            type=row["type"],
            signposts=row["signposts"] or [],
            linked_pillar=row["linked_pillar"],
            expected_date=row["expected_date"],
            expected_window_start=row["expected_window_start"],
            expected_window_end=row["expected_window_end"],
            date_source=row["date_source"],
            created_at=row["created_at"],
        ))

    buckets: dict[str, list[CatalystRow]] = {
        "this_week": [], "next_30d": [], "next_90d": [], "later": [], "untimed": []
    }
    for r in catalysts:
        b = _bucket(r, today)
        if b == "passed":
            continue
        buckets[b].append(r)

    return CatalystListResponse(
        buckets=CatalystBuckets(**buckets),
        total=sum(len(v) for v in buckets.values()),
    )


@router.get("/catalysts/{catalyst_id}", response_model=CatalystRow)
async def get_catalyst(
    catalyst_id: str,
    db: AsyncSession = Depends(get_db),
) -> CatalystRow:
    row = await db.get(Catalyst, catalyst_id)
    if row is None:
        raise HTTPException(status_code=404, detail="catalyst not found")
    return CatalystRow.from_orm_row(row)
