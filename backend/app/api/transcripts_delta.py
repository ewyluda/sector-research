"""GET /api/transcripts/delta/{ticker}/latest, GET /history, POST /delta/{ticker}."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from backend.app.db import async_session, unit_of_work
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.models.transcript_delta import TranscriptDelta
from backend.app.models.transcript_delta_schemas import TranscriptDeltaRead
from backend.app.services import transcript_delta

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


@router.post("/delta/{ticker}", response_model=TranscriptDeltaRead)
async def post_compute(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    force: bool = False,
) -> dict:
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        try:
            row = await transcript_delta.compute_delta(
                ticker=ticker, db=db, fmp=fmp, force=force,
            )
        except transcript_delta.InsufficientTranscriptsError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return _orm_to_dict(row)
