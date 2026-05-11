"""GET /api/transcripts/delta/{ticker}/latest, GET /history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select

from backend.app.db import async_session
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.models.transcript_delta import TranscriptDelta
from backend.app.models.transcript_delta_schemas import TranscriptDeltaRead

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


def _orm_to_dict(row: TranscriptDelta) -> dict:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "transcripts_window": row.transcripts_window,
        "axes": row.axes,
        "computed_at": row.computed_at,
    }


async def _fetch_latest(*, ticker: str, db) -> dict | None:
    row = (await db.execute(
        select(TranscriptDelta)
        .where(TranscriptDelta.ticker == ticker)
        .order_by(TranscriptDelta.computed_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    return _orm_to_dict(row)


async def _fetch_history(*, ticker: str, db) -> list[dict]:
    rows = (await db.execute(
        select(TranscriptDelta)
        .where(TranscriptDelta.ticker == ticker)
        .order_by(TranscriptDelta.computed_at.asc())
    )).scalars().all()
    return [_orm_to_dict(r) for r in rows]


@router.get("/delta/{ticker}/latest")
async def get_latest(ticker: Ticker = Depends(TickerPath)) -> Response:
    async with async_session() as db:
        payload = await _fetch_latest(ticker=ticker, db=db)
    if payload is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(
        content=TranscriptDeltaRead.model_validate(payload).model_dump_json(),
        media_type="application/json",
    )


@router.get("/delta/{ticker}/history", response_model=list[TranscriptDeltaRead])
async def get_history(ticker: Ticker = Depends(TickerPath)) -> list[dict]:
    async with async_session() as db:
        return await _fetch_history(ticker=ticker, db=db)
