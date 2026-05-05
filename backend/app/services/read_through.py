"""Read-through engine.

Surfaces peer events (earnings catalysts, completed pipeline runs) against
active status-board theses, joined through the supply-chain graph
(`relationships` + `competitor_landscape`).

Layers:
- compute_peer_events: build the unified peer-event stream.
- resolve_read_throughs: join events × thesis tickers via the graph.
- summarize_read_through: lazy Haiku impact-summary for a single event.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import HAIKU, complete
from backend.app.models.catalyst import Catalyst
from backend.app.models.filing import CompetitorLandscape, Relationship
from backend.app.models.read_through_dismissal import ReadThroughDismissal
from backend.app.models.research_run import ResearchRun
from backend.app.services.relationship_context import (
    CounterpartyContext,
    get_counterparty_context,
)

logger = logging.getLogger(__name__)


# ── Public dataclasses ─────────────────────────────────────────────────────

@dataclass
class PeerEvent:
    event_key: str  # deterministic — survives recomputation
    peer_ticker: str  # always uppercased
    event_type: Literal["earnings", "run_complete"]
    event_date: date
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationshipLink:
    relationship_type: str
    direction: Literal["outbound", "inbound"]
    verbatim_quote: str | None = None
    magnitude_pct: float | None = None


@dataclass
class ReadThroughItem:
    event_key: str
    peer_ticker: str
    event_type: str
    event_date: date
    payload: dict[str, Any]
    links: list[RelationshipLink]


def _extract_thesis_summary(run: ResearchRun) -> str | None:
    """Pull thesis_summary from a ResearchRun's persisted state. Tolerates
    missing or malformed phase outputs (returns None)."""
    if not isinstance(run.state, dict):
        return None
    phase_outputs = run.state.get("phase_outputs") or {}
    thesis = phase_outputs.get("thesis") or {}
    structured = thesis.get("structured") if isinstance(thesis, dict) else None
    if isinstance(structured, dict):
        return structured.get("thesis_summary")
    return None


# ── Layer 1: peer-event indexer ────────────────────────────────────────────


async def compute_peer_events(
    db: AsyncSession,
    since: datetime,
    until: datetime,
) -> list[PeerEvent]:
    """Build the unified peer-event stream from earnings catalysts +
    completed runs in the [since, until] window.

    Note: research_runs has no explicit completed_at column. Once a run
    transitions to status='completed' its updated_at column reflects that
    completion and does not bump again (subsequent re-runs create a new
    row). updated_at is therefore the de-facto completion timestamp.
    """
    events: list[PeerEvent] = []

    since_d = since.date()
    until_d = until.date()

    # Earnings catalysts
    cat_q = (
        select(Catalyst)
        .where(Catalyst.type == "earnings")
        .where(Catalyst.expected_window_start.is_not(None))
        .where(Catalyst.expected_window_start >= since_d)
        .where(Catalyst.expected_window_start <= until_d)
    )
    cat_rows = (await db.execute(cat_q)).scalars().all()
    for c in cat_rows:
        if not c.expected_window_start:
            continue
        events.append(
            PeerEvent(
                event_key=f"earnings:{c.ticker.upper()}:{c.expected_window_start.isoformat()}",
                peer_ticker=c.ticker.upper(),
                event_type="earnings",
                event_date=c.expected_window_start,
                payload={
                    "description": c.description,
                    "type": c.type,
                    "timeframe": c.timeframe,
                    "expected_date": c.expected_date.isoformat() if c.expected_date else None,
                },
            )
        )

    # Completed runs
    run_q = (
        select(ResearchRun)
        .where(ResearchRun.status == "completed")
        .where(ResearchRun.archived_at.is_(None))
        .where(ResearchRun.updated_at >= since)
        .where(ResearchRun.updated_at <= until)
    )
    run_rows = (await db.execute(run_q)).scalars().all()
    for r in run_rows:
        thesis_summary = _extract_thesis_summary(r)
        events.append(
            PeerEvent(
                event_key=f"run_complete:{r.id}",
                peer_ticker=r.ticker.upper(),
                event_type="run_complete",
                event_date=r.updated_at.date(),
                payload={
                    "run_id": str(r.id),
                    "theme_id": str(r.theme_id),
                    "thesis_summary": thesis_summary,
                },
            )
        )

    events.sort(key=lambda e: e.event_date, reverse=True)
    return events


# ── Layer 2: read-through resolver ─────────────────────────────────────────


# Signal-strength ranks. Lower = stronger signal; ties broken by event_date desc.
_TYPE_RANK = {
    "customer": 0,
    "supplier": 0,
    "partner": 0,
    "joint_venture": 0,
    "competitor": 1,
    "licensor": 2,
    "licensee": 2,
    "distributor": 2,
    "reseller": 2,
    "other": 3,
}


def _rank(rt: str) -> int:
    return _TYPE_RANK.get(rt, 3)


async def resolve_read_throughs(
    db: AsyncSession,
    status_run_ids: list[str],
    peer_events: list[PeerEvent],
) -> dict[str, list[ReadThroughItem]]:
    """For each status-board run, return the read-through items (peer
    events with at least one relationship edge to the thesis ticker)."""
    out: dict[str, list[ReadThroughItem]] = {rid: [] for rid in status_run_ids}
    if not status_run_ids or not peer_events:
        return out

    # Resolve thesis tickers in one shot.
    runs_q = select(ResearchRun.id, ResearchRun.ticker).where(
        ResearchRun.id.in_(status_run_ids)
    )
    rows = (await db.execute(runs_q)).all()
    run_id_by_ticker: dict[str, list[str]] = {}
    for run_id, ticker in rows:
        t = ticker.upper()
        run_id_by_ticker.setdefault(t, []).append(str(run_id))

    thesis_tickers = list(run_id_by_ticker.keys())
    peer_tickers = list({e.peer_ticker for e in peer_events})
    events_by_peer: dict[str, list[PeerEvent]] = {}
    for e in peer_events:
        events_by_peer.setdefault(e.peer_ticker, []).append(e)

    # ── relationships query (non-competitor types) ────────────────────────
    rel_q = select(
        Relationship.ticker,
        Relationship.resolved_to_ticker,
        Relationship.relationship_type,
        Relationship.verbatim_quote,
        Relationship.magnitude_pct,
    ).where(
        or_(
            and_(
                Relationship.ticker.in_(thesis_tickers),
                Relationship.resolved_to_ticker.in_(peer_tickers),
            ),
            and_(
                Relationship.ticker.in_(peer_tickers),
                Relationship.resolved_to_ticker.in_(thesis_tickers),
            ),
        )
    )
    rel_rows = (await db.execute(rel_q)).all()

    # edges: list of (thesis_ticker, peer_ticker, RelationshipLink)
    edges: list[tuple[str, str, RelationshipLink]] = []
    for ticker, resolved, rtype, quote, mag in rel_rows:
        if not resolved:
            continue
        t_upper = ticker.upper()
        r_upper = resolved.upper()
        if t_upper in run_id_by_ticker and r_upper in events_by_peer:
            edges.append(
                (
                    t_upper,
                    r_upper,
                    RelationshipLink(
                        relationship_type=rtype,
                        direction="outbound",
                        verbatim_quote=quote,
                        magnitude_pct=float(mag) if mag is not None else None,
                    ),
                )
            )
        elif t_upper in events_by_peer and r_upper in run_id_by_ticker:
            edges.append(
                (
                    r_upper,
                    t_upper,
                    RelationshipLink(
                        relationship_type=rtype,
                        direction="inbound",
                        verbatim_quote=quote,
                        magnitude_pct=float(mag) if mag is not None else None,
                    ),
                )
            )

    # ── competitor_landscape query ────────────────────────────────────────
    comp_q = select(
        CompetitorLandscape.ticker, CompetitorLandscape.competitors
    ).where(
        or_(
            CompetitorLandscape.ticker.in_(thesis_tickers),
            CompetitorLandscape.ticker.in_(peer_tickers),
        )
    )
    comp_rows = (await db.execute(comp_q)).all()
    for filer_ticker, competitors in comp_rows:
        if not isinstance(competitors, list):
            continue
        filer = filer_ticker.upper()
        for entry in competitors:
            if not isinstance(entry, dict):
                continue
            resolved = entry.get("resolved_to_ticker")
            if not resolved:
                continue
            cp = resolved.upper()
            link_kwargs = dict(
                relationship_type="competitor",
                verbatim_quote=entry.get("verbatim_quote"),
                magnitude_pct=entry.get("magnitude_pct"),
            )
            if filer in run_id_by_ticker and cp in events_by_peer:
                edges.append(
                    (filer, cp, RelationshipLink(direction="outbound", **link_kwargs))
                )
            elif filer in events_by_peer and cp in run_id_by_ticker:
                edges.append(
                    (cp, filer, RelationshipLink(direction="inbound", **link_kwargs))
                )

    # ── bucket edges by (run_id, event_key) ───────────────────────────────
    items_by_key: dict[tuple[str, str], ReadThroughItem] = {}
    seen_links: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for thesis_ticker, peer_ticker, link in edges:
        for run_id in run_id_by_ticker.get(thesis_ticker, []):
            for event in events_by_peer.get(peer_ticker, []):
                key = (run_id, event.event_key)
                if key not in items_by_key:
                    items_by_key[key] = ReadThroughItem(
                        event_key=event.event_key,
                        peer_ticker=event.peer_ticker,
                        event_type=event.event_type,
                        event_date=event.event_date,
                        payload=event.payload,
                        links=[],
                    )
                    seen_links[key] = set()
                link_sig = (link.relationship_type, link.direction)
                if link_sig in seen_links[key]:
                    continue
                seen_links[key].add(link_sig)
                items_by_key[key].links.append(link)

    # ── filter dismissed ──────────────────────────────────────────────────
    if items_by_key:
        dismissed_q = select(
            ReadThroughDismissal.run_id, ReadThroughDismissal.event_key
        ).where(ReadThroughDismissal.run_id.in_([k[0] for k in items_by_key]))
        dismissed = {(str(rid), ek) for rid, ek in (await db.execute(dismissed_q)).all()}
    else:
        dismissed = set()

    # ── group, sort, return ───────────────────────────────────────────────
    for (run_id, _), item in items_by_key.items():
        if (run_id, item.event_key) in dismissed:
            continue
        # Sort links within an item by signal-strength rank.
        item.links.sort(key=lambda l: _rank(l.relationship_type))
        out.setdefault(run_id, []).append(item)

    # Sort each run's items: best edge rank first, then date desc.
    for run_id, items in out.items():
        items.sort(
            key=lambda it: (
                _rank(it.links[0].relationship_type) if it.links else 99,
                -it.event_date.toordinal(),
            )
        )

    return out


# ── Layer 3: lazy Haiku impact summary ─────────────────────────────────────


async def _lookup_event_by_key(
    db: AsyncSession, event_key: str
) -> PeerEvent | None:
    """Resolve a deterministic event_key back to its PeerEvent."""
    if event_key.startswith("earnings:"):
        try:
            _, ticker, date_str = event_key.split(":", 2)
            event_date = date.fromisoformat(date_str)
        except ValueError:
            return None
        cat_q = (
            select(Catalyst)
            .where(Catalyst.type == "earnings")
            .where(Catalyst.ticker == ticker.upper())
            .where(Catalyst.expected_window_start == event_date)
            .limit(1)
        )
        c = (await db.execute(cat_q)).scalars().first()
        if not c or not c.expected_window_start:
            return None
        return PeerEvent(
            event_key=event_key,
            peer_ticker=c.ticker.upper(),
            event_type="earnings",
            event_date=c.expected_window_start,
            payload={
                "description": c.description,
                "type": c.type,
                "timeframe": c.timeframe,
            },
        )
    if event_key.startswith("run_complete:"):
        run_id = event_key.split(":", 1)[1]
        run = (
            await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one_or_none()
        if not run:
            return None
        thesis_summary = _extract_thesis_summary(run)
        return PeerEvent(
            event_key=event_key,
            peer_ticker=run.ticker.upper(),
            event_type="run_complete",
            event_date=run.updated_at.date(),
            payload={
                "run_id": str(run.id),
                "theme_id": str(run.theme_id),
                "thesis_summary": thesis_summary,
            },
        )
    return None


def _render_counterparty_context(ctx: CounterpartyContext) -> str:
    """Render a CounterpartyContext into prompt-friendly text."""
    lines: list[str] = []
    if ctx.outbound:
        lines.append("Outbound (this thesis names them):")
        for rt, entries in ctx.outbound.items():
            for e in entries:
                anchor = f"${e.resolved_ticker}" if e.resolved_ticker else e.name
                lines.append(f"  - {anchor} — {rt}")
    if ctx.inbound:
        lines.append("Mentioned by others:")
        for rt, entries in ctx.inbound.items():
            for e in entries:
                anchor = f"${e.resolved_ticker}" if e.resolved_ticker else e.name
                lines.append(f"  - {anchor} — {rt}")
    return "\n".join(lines) if lines else "(no relationships on file)"


_SUMMARY_SYSTEM = (
    "You are a sell-side equity analyst evaluating peer-event read-through. "
    "Given a thesis on TICKER and a peer event on PEER_TICKER, produce one "
    "paragraph (<= 120 words) answering: how does this peer event affect the "
    "thesis? Cite the relationship from the counterparty context if relevant. "
    "Do not invent quantitative claims. Do not restate the event verbatim — "
    "interpret it."
)


async def summarize_read_through(
    db: AsyncSession,
    run_id: str,
    event_key: str,
) -> str:
    """Run a one-shot Haiku summary for a single (run, event) read-through."""
    run = (
        await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise ValueError(f"run not found: {run_id}")

    event = await _lookup_event_by_key(db, event_key)
    if event is None:
        raise ValueError(f"event not found for key: {event_key}")

    thesis_summary = _extract_thesis_summary(run)

    ctx = await get_counterparty_context(run.ticker.upper(), db)
    rendered = _render_counterparty_context(ctx)

    event_summary = event.payload.get("description") or event.payload.get("thesis_summary") or ""
    user = (
        f"TICKER: {run.ticker}\n"
        f"PEER_TICKER: {event.peer_ticker}\n"
        f"Thesis summary: {thesis_summary or '(none on file)'}\n"
        f"Peer event: {event.event_type} on {event.event_date.isoformat()} — {event_summary}\n"
        f"Relationships from filings:\n{rendered}"
    )

    return await complete(system=_SUMMARY_SYSTEM, user=user, model=HAIKU, max_tokens=400)
