"""Material-events endpoints.

GET  /api/events                      — classified 8-K events, filterable
POST /api/events/{event_id}/dismiss   — hide from board badge + Today
POST /api/events/scan                 — manual daily-scan trigger (202, fire-and-forget)
"""
import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.filing import Filing
from backend.app.models.material_event import MaterialEvent

logger = logging.getLogger(__name__)

router = APIRouter()


class MaterialEventOut(BaseModel):
    id: str
    ticker: str
    event_type: str
    materiality: str
    headline: str
    summary: str
    item_codes: str | None
    filing_date: str
    document_url: str | None
    dismissed_at: str | None


class EventListResponse(BaseModel):
    events: list[MaterialEventOut]
    total: int


@router.get("/events", response_model=EventListResponse)
async def list_events(
    since_days: int = Query(default=14, ge=1, le=365),
    ticker: str | None = None,
    materiality: str | None = None,  # comma-separated, e.g. "high,medium"
    include_dismissed: bool = False,
    db: AsyncSession = Depends(get_db),
) -> EventListResponse:
    cutoff = date.today() - timedelta(days=since_days)
    stmt = (
        select(MaterialEvent, Filing.primary_document_url)
        .join(Filing, Filing.id == MaterialEvent.filing_id)
        .where(MaterialEvent.filing_date >= cutoff)
    )
    if ticker:
        stmt = stmt.where(MaterialEvent.ticker == ticker.upper())
    if materiality:
        levels = [m.strip().lower() for m in materiality.split(",") if m.strip()]
        if levels:
            stmt = stmt.where(MaterialEvent.materiality.in_(levels))
    if not include_dismissed:
        stmt = stmt.where(MaterialEvent.dismissed_at.is_(None))
    stmt = stmt.order_by(MaterialEvent.filing_date.desc(), MaterialEvent.ticker)

    rows = (await db.execute(stmt)).all()
    events = [
        MaterialEventOut(
            id=str(ev.id),
            ticker=ev.ticker,
            event_type=ev.event_type,
            materiality=ev.materiality,
            headline=ev.headline,
            summary=ev.summary,
            item_codes=ev.item_codes,
            filing_date=ev.filing_date.isoformat(),
            document_url=doc_url,
            dismissed_at=ev.dismissed_at.isoformat() if ev.dismissed_at else None,
        )
        for ev, doc_url in rows
    ]
    return EventListResponse(events=events, total=len(events))


@router.post("/events/scan", status_code=202)
async def trigger_scan(request: Request) -> dict:
    """Dev/testing convenience — cron is the primary path. Fire-and-forget;
    the summary lands in the server log."""
    edgar = request.app.state.edgar
    fmp = request.app.state.fmp

    async def _run() -> None:
        from backend.app.services.material_events_scheduler import (
            run_daily_material_scan,
        )
        try:
            summary = await run_daily_material_scan(edgar=edgar, fmp=fmp)
            logger.info("manual material scan: %s", summary)
        except Exception:
            logger.exception("manual material scan crashed")

    asyncio.create_task(_run())
    return {"started": True}


@router.post("/events/{event_id}/dismiss", status_code=204)
async def dismiss_event(event_id: str, db: AsyncSession = Depends(get_db)) -> None:
    row = (
        await db.execute(select(MaterialEvent).where(MaterialEvent.id == event_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if row.dismissed_at is None:
        row.dismissed_at = datetime.now(timezone.utc)
        await db.commit()
