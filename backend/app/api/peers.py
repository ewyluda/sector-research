"""Peer-set CRUD + peer-comparison tables.

ROUTE ORDERING MATTERS: the literal /compare route is declared BEFORE the
/{ticker} routes. "compare" itself parses as a valid ticker symbol
("COMPARE"), so if /{ticker} were declared first it would silently swallow
/compare requests and return a peer set for ticker COMPARE. Pinned by
test_peers_api.CompareRouteTests.test_compare_not_shadowed_by_ticker_route.

Session ownership: peer_sets service functions write without committing;
the handlers here commit after any write (seed or update).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.peer_comp import PeerCompTable, PeerError
from backend.app.models.ticker import Ticker, TickerPath, normalize_ticker
from backend.app.services.peer_comp import build_peer_comp_table
from backend.app.services.peer_sets import get_or_seed_peer_set, update_peer_set

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/peers", tags=["peers"])

MAX_COMPARE_PEERS = 12  # matches peer_sets.MAX_PEERS; focus ticker rides on top


class PeersPayload(BaseModel):
    peers: list[str]


class PeerSetResponse(BaseModel):
    ticker: str
    peers: list[str]
    seeded: bool = False


class PeerCompResponse(BaseModel):
    table: PeerCompTable | None
    errors: list[PeerError]


async def _build_table(focus: str, peers: list[str], fmp) -> PeerCompResponse:
    try:
        table, errors = await build_peer_comp_table(
            focus_ticker=focus, peer_tickers=peers, fmp=fmp
        )
    except Exception as e:  # noqa: BLE001 — focus-ticker fetch failure
        logger.exception("peer-comp build failed for %s", focus)
        raise HTTPException(
            status_code=502, detail=f"failed to fetch data for {focus}: {e}"
        )
    return PeerCompResponse(table=table, errors=errors)


async def _commit_seed(db: AsyncSession) -> None:
    """Commit a seed write, tolerating the concurrent-first-visit race: if
    another request seeded the same ticker first, the PK collision rolls
    back and the locally computed peers are still the right response."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()


@router.get("/compare")
async def compare(
    request: Request,
    tickers: str = Query(
        ..., description="Comma-separated tickers; first is the default focus."
    ),
    focus: str | None = Query(
        None, description="Focus ticker; defaults to the first in tickers."
    ),
) -> PeerCompResponse:
    try:
        parsed = [normalize_ticker(t) for t in tickers.split(",") if t.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not parsed:
        raise HTTPException(
            status_code=400, detail="tickers must contain at least one symbol"
        )
    seen: set[str] = set()
    parsed = [t for t in parsed if not (t in seen or seen.add(t))]
    try:
        focus_t = normalize_ticker(focus) if focus else parsed[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if focus_t not in parsed:
        raise HTTPException(status_code=400, detail="focus must be one of tickers")
    peers = [t for t in parsed if t != focus_t]
    # Cap counts PEERS (focus excluded) so a full 12-peer curated set plus
    # its focus ticker — the "Open in compare →" deep link — stays valid.
    if len(peers) > MAX_COMPARE_PEERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"at most {MAX_COMPARE_PEERS} peers per comparison"
                " (plus the focus ticker)"
            ),
        )
    return await _build_table(focus_t, peers, request.app.state.fmp)


@router.get("/{ticker}")
async def get_peer_set(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerSetResponse:
    peers, seeded = await get_or_seed_peer_set(ticker, db, request.app.state.fmp)
    if seeded:
        await _commit_seed(db)
    return PeerSetResponse(ticker=ticker, peers=peers, seeded=seeded)


@router.put("/{ticker}")
async def put_peer_set(
    payload: PeersPayload,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerSetResponse:
    try:
        peers = await update_peer_set(ticker, payload.peers, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return PeerSetResponse(ticker=ticker, peers=peers)


@router.get("/{ticker}/comp")
async def peer_comp(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerCompResponse:
    peers, seeded = await get_or_seed_peer_set(ticker, db, request.app.state.fmp)
    if seeded:
        await _commit_seed(db)
    if not peers:
        return PeerCompResponse(table=None, errors=[])
    return await _build_table(ticker, peers, request.app.state.fmp)
