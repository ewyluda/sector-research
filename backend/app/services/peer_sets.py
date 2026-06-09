"""Peer-set persistence + seeding, and the shared peer derivation used by
both the peers API and workspace step 5 (differentiation).

Seeding priority: filing-extracted competitors (competitor_landscape,
resolved tickers only) first, then FMP stock-peers to fill remaining
slots, capped at PEER_CAP. Zero-source seeds persist an empty row so we
don't re-derive on every visit.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filing import CompetitorLandscape
from backend.app.models.peer_set import PeerSet
from backend.app.models.ticker import normalize_ticker

log = logging.getLogger(__name__)

PEER_CAP = 8          # auto-seed size
MAX_PEERS = 12        # hard cap on a curated set (matches /compare cap)


async def resolved_competitor_peers(
    ticker: str, db: AsyncSession, cap: int = PEER_CAP
) -> list[str]:
    """Resolved competitor tickers from competitor_landscape. De-duped,
    capped, excludes the focus ticker. (Moved from
    workspace_steps._fetch_resolved_peers, which now delegates here.)"""
    focus = ticker.upper()
    rows = (await db.execute(
        select(CompetitorLandscape).where(CompetitorLandscape.ticker == focus)
    )).scalars().all()

    seen: set[str] = set()
    peers: list[str] = []
    for row in rows:
        for c in (row.competitors or []):
            t = (c.get("resolved_to_ticker") or "").upper()
            if t and t != focus and t not in seen:
                seen.add(t)
                peers.append(t)
                if len(peers) >= cap:
                    return peers
    return peers


async def get_or_seed_peer_set(
    ticker: str, db: AsyncSession, fmp
) -> tuple[list[str], bool]:
    """Return (peers, seeded). Seeds on first call for a ticker. Writes
    without committing — the caller owns the session and must commit."""
    focus = ticker.upper()
    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is not None:
        return list(row.peers or []), False

    peers = await resolved_competitor_peers(focus, db, cap=PEER_CAP)
    if len(peers) < PEER_CAP:
        try:
            fmp_peers, _ = await fmp.get_stock_peers(focus)
        except Exception:  # noqa: BLE001 — seed-time best effort
            log.warning("stock-peers fetch failed during seed for %s", focus)
            fmp_peers = []
        seen = set(peers)
        for t in fmp_peers:
            if t and t != focus and t not in seen:
                seen.add(t)
                peers.append(t)
                if len(peers) >= PEER_CAP:
                    break

    # NOTE: no ON CONFLICT handling — two concurrent seeds for the same
    # ticker would make the second commit raise IntegrityError on the PK.
    # Acceptable for a single-user tool: the row exists afterwards and a
    # retry returns it via the hit path.
    db.add(PeerSet(ticker=focus, peers=peers))
    return peers, True


async def update_peer_set(
    ticker: str, peers: list[str], db: AsyncSession
) -> list[str]:
    """Replace the persisted peer list. Normalizes + de-dupes, drops the
    set's own ticker, allows [] (clears). Raises ValueError on an invalid
    ticker or an over-cap list (API maps both to 400). Writes without
    committing — the caller owns the session and must commit."""
    focus = ticker.upper()
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in peers:
        t = normalize_ticker(raw)  # raises ValueError on garbage
        if t != focus and t not in seen:
            seen.add(t)
            cleaned.append(t)
    if len(cleaned) > MAX_PEERS:
        raise ValueError(f"peer set capped at {MAX_PEERS} tickers")

    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is None:
        db.add(PeerSet(ticker=focus, peers=cleaned))
    else:
        row.peers = cleaned
    return cleaned


async def peers_for_ticker(
    ticker: str, db: AsyncSession, cap: int = PEER_CAP
) -> list[str]:
    """Peer list for downstream consumers (workspace step 5): the curated
    set when present and non-empty, else filing-derived competitors."""
    focus = ticker.upper()
    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is not None and row.peers:
        return list(row.peers)[:cap]
    return await resolved_competitor_peers(focus, db, cap=cap)
