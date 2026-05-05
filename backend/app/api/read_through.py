"""Read-through API — board-wide read-throughs, dismissal, and lazy summary."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.read_through_dismissal import ReadThroughDismissal
from backend.app.services.read_through import (
    PeerEvent,
    ReadThroughItem,
    RelationshipLink,
    compute_peer_events,
    resolve_read_throughs,
    summarize_read_through,
)
from backend.app.services.status_board import build_status_board

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic response models ───────────────────────────────────────────────


class RelationshipLinkOut(BaseModel):
    relationship_type: str
    direction: str
    verbatim_quote: str | None = None
    magnitude_pct: float | None = None


class ReadThroughItemOut(BaseModel):
    event_key: str
    peer_ticker: str
    event_type: str
    event_date: str  # ISO
    payload: dict[str, Any]
    links: list[RelationshipLinkOut]


class DismissBody(BaseModel):
    run_id: str
    event_key: str


class SummaryBody(BaseModel):
    run_id: str
    event_key: str


class SummaryOut(BaseModel):
    summary: str


def _serialize_link(link: RelationshipLink) -> RelationshipLinkOut:
    return RelationshipLinkOut(
        relationship_type=link.relationship_type,
        direction=link.direction,
        verbatim_quote=link.verbatim_quote,
        magnitude_pct=link.magnitude_pct,
    )


def _serialize_item(item: ReadThroughItem) -> ReadThroughItemOut:
    return ReadThroughItemOut(
        event_key=item.event_key,
        peer_ticker=item.peer_ticker,
        event_type=item.event_type,
        event_date=item.event_date.isoformat(),
        payload=item.payload,
        links=[_serialize_link(link) for link in item.links],
    )


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/status/read-throughs")
async def get_read_throughs(
    since: datetime | None = None,
    until: datetime | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ReadThroughItemOut]]:
    now = datetime.now(timezone.utc)
    if until is None:
        until = now
    if since is None:
        since = until - timedelta(days=30)

    board = await build_status_board(db)
    if not board.entries:
        return {}

    run_ids = [e.run_id for e in board.entries]
    events = await compute_peer_events(db, since, until)
    resolved = await resolve_read_throughs(db, run_ids, events)
    return {
        run_id: [_serialize_item(it) for it in items]
        for run_id, items in resolved.items()
        if items
    }


@router.post("/status/read-throughs/dismiss", status_code=204)
async def dismiss_read_through(
    body: DismissBody,
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = (
        pg_insert(ReadThroughDismissal)
        .values(run_id=body.run_id, event_key=body.event_key)
        .on_conflict_do_nothing(constraint="uq_read_through_dismissals_run_event")
    )
    await db.execute(stmt)
    await db.commit()


@router.post("/status/read-throughs/summary", response_model=SummaryOut)
async def summarize(
    body: SummaryBody,
    db: AsyncSession = Depends(get_db),
) -> SummaryOut:
    try:
        summary = await summarize_read_through(db, body.run_id, body.event_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("read_through.summary_failed", extra={"run_id": body.run_id, "event_key": body.event_key})
        raise HTTPException(status_code=502, detail=f"summary generation failed: {e}")
    return SummaryOut(summary=summary)
