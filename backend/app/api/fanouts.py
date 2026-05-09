"""Fan-out endpoints — theme-scoped and ticker-scoped relationship population.

Kicks off `FanoutService` background work and exposes polling-style
status reads. Instantiation of the service lives in main.py lifespan;
this module only dispatches to it via request.app.state.fanout.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.ticker import Ticker, TickerPath

router = APIRouter(tags=["fanouts"])


@router.post("/themes/{theme_id}/relationships/fanout", status_code=202)
async def start_theme_fanout(
    theme_id: str,
    request: Request,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kick off a theme-scoped fan-out. Returns the initial status payload
    (including fanout_id) so the client can start polling immediately."""
    fanout = request.app.state.fanout
    try:
        status = await fanout.start_theme(theme_id, db=db, force=force)
    except ValueError as exc:
        # Mirrors pipeline.py's ValueError → 404 mapping.
        raise HTTPException(status_code=404, detail=str(exc))
    return status.to_dict()


@router.post("/tickers/{ticker}/relationships/fanout", status_code=202)
async def start_ticker_fanout(
    request: Request,
    force: bool = Query(default=False),
    ticker: Ticker = Depends(TickerPath),
) -> dict:
    """Kick off a single-ticker fan-out."""
    fanout = request.app.state.fanout
    status = fanout.start_ticker(ticker, force=force)
    return status.to_dict()


@router.get("/fanouts/{fanout_id}")
async def get_fanout(fanout_id: str, request: Request) -> dict:
    fanout = request.app.state.fanout
    status = fanout.get(fanout_id)
    if status is None:
        raise HTTPException(status_code=404, detail="fanout not found")
    return status.to_dict()
