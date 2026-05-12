# Tier 1.4 — Read-Through Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-through engine that surfaces peer events (earnings catalysts, completed runs) against active status-board theses by joining the existing supply-chain relationship graph (`relationships` + `competitor_landscape`). Inline UI on `/status` shows a badge per row with a dismissable event list and a lazy Haiku impact-summary button.

**Architecture:** Read-time aggregation against existing tables. One new persisted artifact: `read_through_dismissals` (run_id + event_key + dismissed_at). Backend layers — peer-event indexer (catalysts + completed runs), read-through resolver (joins peer events × thesis tickers via relationships + competitor_landscape), API endpoints (GET board read-throughs, POST dismiss, POST summary). Frontend extends `/status` with a numeric badge and inline drawer per row. Spec: `docs/superpowers/specs/2026-05-04-tier-1-4-read-through-engine-design.md`.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + PostgreSQL (backend), Next.js 16 App Router + React 19 + Tailwind v4 (frontend). No backend test framework configured per CLAUDE.md — verification is a manual smoke script for backend and lint + build + Playwright walkthrough for frontend.

**Branch:** create `feat/read-through-engine` off `feat/catalyst-calendar` (Tier 1.4 depends on Tier 2.6's status-board aggregator already merged into that branch). Rebase onto `main` after PR #20 lands.

---

## File structure

**Backend — create:**
- `backend/app/models/read_through_dismissal.py` — `ReadThroughDismissal` ORM model
- `backend/migrations/versions/<rev>_add_read_through_dismissals.py` — Alembic migration
- `backend/app/services/read_through.py` — `compute_peer_events`, `resolve_read_throughs`, `summarize_read_through` (Haiku call), plus the `PeerEvent`, `ReadThroughItem`, `RelationshipLink` dataclasses and the signal-strength rank helper
- `backend/app/api/read_through.py` — three endpoints under `/api/status/read-throughs`
- `backend/scripts/smoke_read_through.py` — manual smoke runner

**Backend — modify:**
- `backend/app/models/__init__.py` — register `ReadThroughDismissal`
- `backend/app/main.py` — register `read_through_router`

**Frontend — create:**
- `frontend/components/status/ReadThroughDrawer.tsx` — drawer rendered inline beneath a status-board row

**Frontend — modify:**
- `frontend/lib/api.ts` — add `RelationshipLink`, `ReadThroughItem`, `ReadThroughsByRun` types and a `readThroughs` API client object
- `frontend/app/status/page.tsx` — parallel-fetch read-throughs, render badges, mount drawer

---

## Task 1: Add `ReadThroughDismissal` ORM model

**Files:**
- Create: `backend/app/models/read_through_dismissal.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the ORM model**

Create `backend/app/models/read_through_dismissal.py`:

```python
"""ReadThroughDismissal — records that a peer-event read-through has been
dismissed for a specific thesis run.

Default state (not dismissed) is implicit absence; only dismissals are
persisted. Dismissals survive engine recomputation because event_key is
deterministic (e.g. "earnings:NVDA:2026-08-15", "run_complete:<uuid>").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ReadThroughDismissal(Base):
    __tablename__ = "read_through_dismissals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "event_key", name="uq_read_through_dismissals_run_event"
        ),
        Index("ix_read_through_dismissals_run_id", "run_id"),
    )
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`, add the import alongside the others (the file pattern is one import per model):

```python
from backend.app.models.read_through_dismissal import ReadThroughDismissal  # noqa: F401
```

- [ ] **Step 3: Verify imports compile**

Run: `source backend/venv/bin/activate && python -c "from backend.app.models import ReadThroughDismissal; print(ReadThroughDismissal.__tablename__)"`
Expected: `read_through_dismissals`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/read_through_dismissal.py backend/app/models/__init__.py
git commit -m "feat(read-through): add ReadThroughDismissal ORM model"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `backend/migrations/versions/<auto>_add_read_through_dismissals.py`

- [ ] **Step 1: Generate the migration**

Run:
```bash
cd backend && PYTHONPATH=.. alembic revision --autogenerate -m "add read_through_dismissals" && cd ..
```

Expected: a new file appears in `backend/migrations/versions/` whose `down_revision` is `0b7ff9421fa5` (the kill-criterion-states migration).

- [ ] **Step 2: Inspect the generated migration**

Open the new file. Confirm `op.create_table("read_through_dismissals", ...)` includes:
- `id` (UUID primary key)
- `run_id` (UUID, FK to `research_runs.id` with `ondelete='CASCADE'`)
- `event_key` (VARCHAR(255), not null)
- `dismissed_at` (TIMESTAMP WITH TIME ZONE, not null)
- `UniqueConstraint("run_id", "event_key", name="uq_read_through_dismissals_run_event")`
- `Index("ix_read_through_dismissals_run_id", "run_id")`

If any are missing or extra (autogenerate sometimes adds default-value sentinels), edit the migration body to match the model exactly.

- [ ] **Step 3: Apply the migration**

Run: `cd backend && PYTHONPATH=.. alembic upgrade head && cd ..`
Expected: `Running upgrade 0b7ff9421fa5 -> <new_rev>, add read_through_dismissals`

- [ ] **Step 4: Verify the table exists**

Run:
```bash
psql "$(python -c "from backend.app.config import get_settings; print(get_settings().database_url_sync)")" -c "\d read_through_dismissals"
```

Expected: table with the four columns + the unique constraint + the index.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/*_add_read_through_dismissals.py
git commit -m "feat(read-through): alembic migration for read_through_dismissals"
```

---

## Task 3: Peer-event indexer (`compute_peer_events`)

**Files:**
- Create: `backend/app/services/read_through.py`

- [ ] **Step 1: Create the service module skeleton**

Create `backend/app/services/read_through.py`:

```python
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
```

- [ ] **Step 2: Implement `compute_peer_events`**

Append to `backend/app/services/read_through.py`:

```python
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
```

- [ ] **Step 3: Smoke-check the indexer**

Run:
```bash
source backend/venv/bin/activate
PYTHONPATH=. python -c "
import asyncio
from datetime import datetime, timedelta, timezone
from backend.app.db import async_session
from backend.app.services.read_through import compute_peer_events

async def main():
    async with async_session() as db:
        until = datetime.now(timezone.utc)
        since = until - timedelta(days=30)
        events = await compute_peer_events(db, since, until)
        print(f'{len(events)} events')
        for e in events[:5]:
            print(e.event_key, e.peer_ticker, e.event_type, e.event_date)

asyncio.run(main())
"
```

Expected: prints a count and up to five `(event_key, ticker, type, date)` tuples. Exact count depends on local DB state; non-zero if any earnings catalysts or completed runs exist in the last 30d.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/read_through.py
git commit -m "feat(read-through): peer-event indexer (earnings + run-complete)"
```

---

## Task 4: Read-through resolver (`resolve_read_throughs`)

**Files:**
- Modify: `backend/app/services/read_through.py`

- [ ] **Step 1: Add the signal-strength rank helper**

Append to `backend/app/services/read_through.py`:

```python
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
```

- [ ] **Step 2: Implement `resolve_read_throughs`**

Append:

```python
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
    ticker_by_run: dict[str, str] = {}
    for run_id, ticker in rows:
        t = ticker.upper()
        run_id_by_ticker.setdefault(t, []).append(str(run_id))
        ticker_by_run[str(run_id)] = t

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
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/read_through.py
git commit -m "feat(read-through): resolver joins peer events x relationships + competitors"
```

---

## Task 5: Lazy Haiku impact summary (`summarize_read_through`)

**Files:**
- Modify: `backend/app/services/read_through.py`

- [ ] **Step 1: Add the new imports at the top of the file**

In `backend/app/services/read_through.py`, in the existing imports section near the top of the file, add:

```python
from backend.app.graph.llm import HAIKU, complete
from backend.app.services.relationship_context import get_counterparty_context
```

- [ ] **Step 2: Implement the summary helper**

Append to `backend/app/services/read_through.py`:

```python
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
        thesis_summary = None
        if isinstance(run.state, dict):
            structured = (
                (run.state.get("phase_outputs") or {}).get("thesis") or {}
            ).get("structured")
            if isinstance(structured, dict):
                thesis_summary = structured.get("thesis_summary")
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


def _render_counterparty_context(ctx) -> str:
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

    thesis_summary = None
    if isinstance(run.state, dict):
        structured = (
            (run.state.get("phase_outputs") or {}).get("thesis") or {}
        ).get("structured")
        if isinstance(structured, dict):
            thesis_summary = structured.get("thesis_summary")

    ctx = await get_counterparty_context(run.ticker.upper(), db)
    rendered = _render_counterparty_context(ctx)

    user = (
        f"TICKER: {run.ticker}\n"
        f"PEER_TICKER: {event.peer_ticker}\n"
        f"Thesis summary: {thesis_summary or '(none on file)'}\n"
        f"Peer event: {event.event_type} on {event.event_date.isoformat()} — "
        f"{event.payload}\n"
        f"Relationships from filings:\n{rendered}"
    )

    return await complete(system=_SUMMARY_SYSTEM, user=user, model=HAIKU, max_tokens=400)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/read_through.py
git commit -m "feat(read-through): lazy Haiku impact-summary helper"
```

---

## Task 6: API endpoints

**Files:**
- Create: `backend/app/api/read_through.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the API module**

Create `backend/app/api/read_through.py`:

```python
"""Read-through API — board-wide read-throughs, dismissal, and lazy summary."""
from __future__ import annotations

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


def _serialize_link(l: RelationshipLink) -> RelationshipLinkOut:
    return RelationshipLinkOut(
        relationship_type=l.relationship_type,
        direction=l.direction,
        verbatim_quote=l.verbatim_quote,
        magnitude_pct=l.magnitude_pct,
    )


def _serialize_item(item: ReadThroughItem) -> ReadThroughItemOut:
    return ReadThroughItemOut(
        event_key=item.event_key,
        peer_ticker=item.peer_ticker,
        event_type=item.event_type,
        event_date=item.event_date.isoformat(),
        payload=item.payload,
        links=[_serialize_link(l) for l in item.links],
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
        raise HTTPException(status_code=502, detail=f"summary generation failed: {e}")
    return SummaryOut(summary=summary)
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add the import next to the other api imports (after `from backend.app.api.status import router as status_router`):

```python
from backend.app.api.read_through import router as read_through_router
```

And add the include line next to the other `app.include_router(...)` calls:

```python
app.include_router(read_through_router, prefix="/api")
```

- [ ] **Step 3: Smoke-test the endpoints with curl**

Start the dev server: `uvicorn backend.app.main:app --reload` (in a second terminal).

Then:
```bash
curl -s 'http://localhost:8000/api/status/read-throughs' | python -m json.tool | head -20
```

Expected: a JSON object (possibly empty `{}` or with run-id keys mapped to arrays of items). HTTP 200, no errors. If `{}`, that's expected on a clean DB without recent events; the resolver test in Task 11 seeds events.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/read_through.py backend/app/main.py
git commit -m "feat(read-through): api endpoints (board, dismiss, summary)"
```

---

## Task 7: Frontend types + client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add types to lib/api.ts**

In `frontend/lib/api.ts`, near the existing status-board types (`StatusBoardEntry`, etc), add:

```typescript
export interface RelationshipLink {
  relationship_type: string;
  direction: "outbound" | "inbound";
  verbatim_quote?: string | null;
  magnitude_pct?: number | null;
}

export interface ReadThroughItem {
  event_key: string;
  peer_ticker: string;
  event_type: "earnings" | "run_complete";
  event_date: string;
  payload: Record<string, unknown>;
  links: RelationshipLink[];
}

export type ReadThroughsByRun = Record<string, ReadThroughItem[]>;
```

- [ ] **Step 2: Add the client object**

In the same file, near the existing `status` and `killCriteria` client objects, append:

```typescript
export const readThroughs = {
  async list(params?: { since?: string; until?: string }): Promise<ReadThroughsByRun> {
    const qs = new URLSearchParams();
    if (params?.since) qs.set("since", params.since);
    if (params?.until) qs.set("until", params.until);
    const url = `/api/status/read-throughs${qs.toString() ? `?${qs}` : ""}`;
    return apiFetch<ReadThroughsByRun>(url);
  },

  async dismiss(run_id: string, event_key: string): Promise<void> {
    await apiFetch<void>("/api/status/read-throughs/dismiss", {
      method: "POST",
      body: JSON.stringify({ run_id, event_key }),
    });
  },

  async summarize(run_id: string, event_key: string): Promise<{ summary: string }> {
    return apiFetch<{ summary: string }>("/api/status/read-throughs/summary", {
      method: "POST",
      body: JSON.stringify({ run_id, event_key }),
    });
  },
};
```

- [ ] **Step 3: Verify the frontend compiles**

Run: `cd frontend && npm run lint && cd ..`
Expected: lint passes (silent or only formatting noise).

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(read-through): frontend types and api client"
```

---

## Task 8: ReadThroughDrawer component

**Files:**
- Create: `frontend/components/status/ReadThroughDrawer.tsx`

- [ ] **Step 1: Create the drawer component**

Create `frontend/components/status/ReadThroughDrawer.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { ReadThroughItem } from "@/lib/api";
import { readThroughs } from "@/lib/api";

interface Props {
  runId: string;
  items: ReadThroughItem[];
  onDismissed: (eventKey: string) => void;
}

const TYPE_BADGE: Record<string, string> = {
  customer: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  supplier: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  partner: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  joint_venture: "bg-emerald-900/40 text-emerald-200 ring-emerald-700",
  competitor: "bg-amber-900/40 text-amber-200 ring-amber-700",
  licensor: "bg-slate-800 text-slate-300 ring-slate-700",
  licensee: "bg-slate-800 text-slate-300 ring-slate-700",
  distributor: "bg-slate-800 text-slate-300 ring-slate-700",
  reseller: "bg-slate-800 text-slate-300 ring-slate-700",
  other: "bg-slate-800/60 text-slate-400 ring-slate-700",
};

const EVENT_LABEL: Record<string, string> = {
  earnings: "Earnings",
  run_complete: "Run finished",
};

export function ReadThroughDrawer({ runId, items, onDismissed }: Props) {
  if (items.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-slate-500" data-print-hide="true">
        No active read-throughs.
      </div>
    );
  }

  return (
    <div className="space-y-2 px-4 py-3" data-print-hide="true">
      {items.map((item) => (
        <ReadThroughRow
          key={item.event_key}
          runId={runId}
          item={item}
          onDismissed={onDismissed}
        />
      ))}
    </div>
  );
}

interface RowProps {
  runId: string;
  item: ReadThroughItem;
  onDismissed: (eventKey: string) => void;
}

function ReadThroughRow({ runId, item, onDismissed }: RowProps) {
  const [summary, setSummary] = useState<string | null>(null);
  const [busy, setBusy] = useState<"none" | "dismiss" | "summary">("none");
  const [error, setError] = useState<string | null>(null);

  async function handleDismiss() {
    setBusy("dismiss");
    setError(null);
    try {
      await readThroughs.dismiss(runId, item.event_key);
      onDismissed(item.event_key);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dismiss failed");
      setBusy("none");
    }
  }

  async function handleSummarize() {
    setBusy("summary");
    setError(null);
    try {
      const { summary } = await readThroughs.summarize(runId, item.event_key);
      setSummary(summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Summary failed");
    } finally {
      setBusy("none");
    }
  }

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200">
            ${item.peer_ticker}
          </span>
          <span className="text-slate-300">{EVENT_LABEL[item.event_type] ?? item.event_type}</span>
          <span className="text-slate-500">·</span>
          <span className="text-slate-500">{item.event_date}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleSummarize}
            disabled={busy !== "none"}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "summary" ? "Generating…" : summary ? "Regenerate" : "Generate impact summary"}
          </button>
          <button
            onClick={handleDismiss}
            disabled={busy !== "none"}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "dismiss" ? "…" : "Dismiss"}
          </button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.links.map((l, i) => (
          <span
            key={`${l.relationship_type}:${l.direction}:${i}`}
            title={l.verbatim_quote ?? ""}
            className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ${TYPE_BADGE[l.relationship_type] ?? TYPE_BADGE.other}`}
          >
            {l.relationship_type} · {l.direction}
            {l.magnitude_pct != null ? ` · ${l.magnitude_pct.toFixed(0)}%` : ""}
          </span>
        ))}
      </div>

      {summary && (
        <div className="mt-2 rounded bg-slate-950/60 p-2 text-xs text-slate-300">
          {summary}
        </div>
      )}
      {error && (
        <div className="mt-2 text-xs text-rose-400">{error}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify lint**

Run: `cd frontend && npm run lint && cd ..`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/status/ReadThroughDrawer.tsx
git commit -m "feat(read-through): drawer component for status row"
```

---

## Task 9: Wire badge + drawer into /status page

**Files:**
- Modify: `frontend/app/status/page.tsx`

- [ ] **Step 1: Add the read-through fetch + state**

In `frontend/app/status/page.tsx`, near the existing board-fetch hook, add a parallel fetch for read-throughs. The exact location depends on how the page is currently structured — find the place that calls `status.getBoard()` and add a sibling effect:

```tsx
import { readThroughs, type ReadThroughsByRun } from "@/lib/api";
import { ReadThroughDrawer } from "@/components/status/ReadThroughDrawer";

// Inside the component, alongside existing state hooks:
const [rtByRun, setRtByRun] = useState<ReadThroughsByRun>({});
const [expanded, setExpanded] = useState<string | null>(null);

// Inside the existing polling effect (or as a parallel effect with the same
// 60s cadence and same visibility guard), also fetch read-throughs:
useEffect(() => {
  let cancelled = false;
  async function load() {
    try {
      const data = await readThroughs.list();
      if (!cancelled) setRtByRun(data);
    } catch {
      // best-effort — leave previous data on the screen
    }
  }
  load();
  const id = setInterval(load, 60_000);
  const onVis = () => {
    if (document.visibilityState === "visible") load();
  };
  document.addEventListener("visibilitychange", onVis);
  return () => {
    cancelled = true;
    clearInterval(id);
    document.removeEventListener("visibilitychange", onVis);
  };
}, []);

function handleDismissed(runId: string, eventKey: string) {
  setRtByRun((prev) => ({
    ...prev,
    [runId]: (prev[runId] ?? []).filter((it) => it.event_key !== eventKey),
  }));
}
```

- [ ] **Step 2: Render the badge + drawer per row**

In the row-render loop, add a badge button next to the existing row controls and a conditional drawer beneath the row:

```tsx
// Inside the row-render JSX, alongside existing per-row controls (e.g. archive button):
{(() => {
  const items = rtByRun[entry.run_id] ?? [];
  if (items.length === 0) return null;
  const open = expanded === entry.run_id;
  return (
    <button
      onClick={() => setExpanded(open ? null : entry.run_id)}
      className="ml-2 rounded bg-amber-900/40 px-1.5 py-0.5 text-[11px] text-amber-200 ring-1 ring-amber-700 hover:bg-amber-900/60"
      title="Read-through events"
    >
      ⟿ {items.length}
    </button>
  );
})()}
```

The current `/status` page uses CSS Grid divs (not HTML `<table>`) for rows — see the `grid grid-cols-[80px_110px_...]` className around the row map. Wrap each row + drawer in a fragment so the drawer sits directly beneath:

```tsx
{filtered.map((e) => {
  const items = rtByRun[e.run_id] ?? [];
  const isOpen = expanded === e.run_id;
  return (
    <div key={e.run_id} className="space-y-1">
      {/* existing row markup goes here, with the badge button inserted in the controls area */}
      {isOpen && items.length > 0 && (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
          <ReadThroughDrawer
            runId={e.run_id}
            items={items}
            onDismissed={(ek) => handleDismissed(e.run_id, ek)}
          />
        </div>
      )}
    </div>
  );
})}
```

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint && npm run build && cd ..
```

Expected: lint clean; build succeeds; `/status` shows up as a Static (○) route in the route table.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/status/page.tsx
git commit -m "feat(read-through): badge + inline drawer on /status rows"
```

---

## Task 10: Smoke script + manual end-to-end verification

**Files:**
- Create: `backend/scripts/smoke_read_through.py`

- [ ] **Step 1: Create the smoke script**

Create `backend/scripts/smoke_read_through.py`:

```python
"""Smoke test for the read-through engine.

Seeds a synthetic earnings catalyst against a peer ticker that has at
least one outbound or inbound relationship row to a status-board ticker,
runs the resolver, asserts the synthetic event surfaces, then cleans up.

Usage (from project root with venv active):
    PYTHONPATH=. python backend/scripts/smoke_read_through.py
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.db import async_session
from backend.app.models.catalyst import Catalyst
from backend.app.models.filing import Relationship
from backend.app.models.read_through_dismissal import ReadThroughDismissal
from backend.app.services.read_through import (
    compute_peer_events,
    resolve_read_throughs,
)
from backend.app.services.status_board import build_status_board


async def main() -> None:
    async with async_session() as db:
        # Pick the first status-board entry to target.
        board = await build_status_board(db)
        if not board.entries:
            print("SKIP: status board is empty — seed at least one completed run first.")
            return
        target = board.entries[0]
        print(f"target: {target.ticker} (run {target.run_id})")

        # Find a peer ticker that has a relationship edge to/from the target.
        # Project convention: relationships.ticker and resolved_to_ticker are
        # stored uppercase (see edgar_relationships.py / counterparty_resolver).
        target_t = target.ticker.upper()
        rel_q = (
            select(Relationship.resolved_to_ticker, Relationship.ticker)
            .where(
                (Relationship.ticker == target_t)
                | (Relationship.resolved_to_ticker == target_t)
            )
            .limit(50)
        )
        rel_rows = (await db.execute(rel_q)).all()
        peers = {
            (r.upper() if r else None) or (t.upper() if t else None)
            for r, t in rel_rows
            if (r or t)
        }
        peers.discard(None)
        peers.discard(target_t)
        if not peers:
            print(f"SKIP: no relationship rows for {target.ticker}.")
            return
        peer_ticker = next(iter(peers))
        print(f"peer: {peer_ticker}")

        # Seed a synthetic earnings catalyst on the peer.
        synthetic_run_id = str((await db.execute(
            select(Catalyst.run_id).limit(1)
        )).scalar()) or str(uuid.uuid4())  # any run_id is fine for the smoke
        synth = Catalyst(
            id=str(uuid.uuid4()),
            run_id=synthetic_run_id,
            ticker=peer_ticker,
            ordinal=999,
            timeframe="next 30d (synthetic)",
            description="SMOKE TEST earnings catalyst",
            type="earnings",
            signposts=[],
            linked_pillar=None,
            expected_date=date.today() + timedelta(days=5),
            expected_window_start=date.today() + timedelta(days=5),
            expected_window_end=date.today() + timedelta(days=7),
            date_source="smoke",
        )
        db.add(synth)
        await db.commit()
        print(f"seeded synthetic catalyst id={synth.id}")

        try:
            # Run the engine.
            now = datetime.now(timezone.utc)
            events = await compute_peer_events(db, now - timedelta(days=30), now + timedelta(days=30))
            event_keys = [e.event_key for e in events]
            expected_key = f"earnings:{peer_ticker}:{synth.expected_window_start.isoformat()}"
            assert expected_key in event_keys, f"missing synthetic key: {expected_key}"
            print(f"PASS: synthetic event present ({len(events)} total)")

            resolved = await resolve_read_throughs(db, [target.run_id], events)
            target_items = resolved.get(target.run_id, [])
            matched = [it for it in target_items if it.event_key == expected_key]
            assert matched, f"resolver did not surface synthetic event for {target.run_id}"
            print(f"PASS: resolver surfaced synthetic event with {len(matched[0].links)} link(s)")

            # Test dismissal filtering.
            dismissal = ReadThroughDismissal(
                id=str(uuid.uuid4()),
                run_id=target.run_id,
                event_key=expected_key,
            )
            db.add(dismissal)
            await db.commit()
            print("seeded dismissal")

            resolved2 = await resolve_read_throughs(db, [target.run_id], events)
            target_items2 = resolved2.get(target.run_id, [])
            still_matched = [it for it in target_items2 if it.event_key == expected_key]
            assert not still_matched, "dismissed event should be filtered out"
            print("PASS: dismissal filtered the synthetic event")

            # Cleanup dismissal.
            await db.delete(dismissal)
            await db.commit()
        finally:
            # Cleanup synthetic catalyst.
            await db.delete(synth)
            await db.commit()
            print("cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the smoke**

```bash
source backend/venv/bin/activate
PYTHONPATH=. python backend/scripts/smoke_read_through.py
```

Expected: prints `target:`, `peer:`, `seeded synthetic catalyst`, `PASS:` (×3), `cleanup complete`. If `SKIP:` appears, the local DB doesn't have the right seed data — run a normal pipeline against a ticker that has fan-out relationships first, then re-run the smoke.

- [ ] **Step 3: End-to-end browser walkthrough**

Start backend + frontend, open `http://localhost:3000/status`.

Verify:
- Page renders without console errors.
- For at least one row that has read-through events, the `⟿ N` badge appears next to the row controls.
- Clicking the badge expands the drawer beneath the row.
- The drawer shows the event header (ticker chip, event-type label, date) and relationship-type pills.
- Clicking "Generate impact summary" shows a spinner, then renders one paragraph of Haiku output.
- Clicking "Dismiss" removes that event from the drawer and decrements the badge.
- After 60s of staying on the page (or after a tab visibility flip), the read-throughs re-fetch and badges update.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/smoke_read_through.py
git commit -m "feat(read-through): smoke script and end-to-end verification"
```

---

## Task 11: Final lint, build, type-check

- [ ] **Step 1: Frontend full check**

```bash
cd frontend && npm run lint && npm run build && cd ..
```

Expected: lint clean, build succeeds, `/status` listed as `○ Static`.

- [ ] **Step 2: Backend import sanity**

```bash
source backend/venv/bin/activate
python -c "from backend.app.main import app; print('routes:', len(app.routes))"
```

Expected: prints a route count that's three higher than before this work (the three new endpoints).

- [ ] **Step 3: Confirm no orphaned imports or types**

Search for any references to `competitor` in the relationships flow that could be broken — make sure the resolver edge code only emits `relationship_type="competitor"` from `competitor_landscape`, not from `relationships`. Skim `backend/app/services/read_through.py` once and verify.

- [ ] **Step 4: Wrap-up commit (if any leftover changes)**

```bash
git status
# only commit if there's something staged
```

---

## Summary of acceptance criteria

- [ ] `read_through_dismissals` table exists with the unique constraint.
- [ ] `compute_peer_events` returns deterministic event keys for earnings catalysts and completed runs.
- [ ] `resolve_read_throughs` joins peer events × thesis tickers via both `relationships` and `competitor_landscape`, ranks by signal strength, filters dismissals.
- [ ] Three endpoints (`GET /api/status/read-throughs`, `POST /api/status/read-throughs/dismiss`, `POST /api/status/read-throughs/summary`) are reachable and return the expected shapes.
- [ ] `/status` page shows a numeric badge per row with read-throughs and an inline drawer with dismiss + lazy-summary affordances.
- [ ] Smoke script passes end-to-end (event surfaced → dismissed → filtered).
- [ ] `npm run lint` and `npm run build` are clean.
