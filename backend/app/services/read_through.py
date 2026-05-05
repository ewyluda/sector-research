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

from backend.app.models.catalyst import Catalyst
from backend.app.models.filing import CompetitorLandscape, Relationship
from backend.app.models.read_through_dismissal import ReadThroughDismissal
from backend.app.models.research_run import ResearchRun

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
        thesis_summary = None
        if isinstance(r.state, dict):
            phase_outputs = r.state.get("phase_outputs") or {}
            thesis = phase_outputs.get("thesis") or {}
            structured = thesis.get("structured") if isinstance(thesis, dict) else None
            if isinstance(structured, dict):
                thesis_summary = structured.get("thesis_summary")
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
