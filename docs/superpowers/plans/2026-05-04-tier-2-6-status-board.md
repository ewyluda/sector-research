# Tier 2.6 — Live Thesis Status Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `/status` page that aggregates active theses (latest completed run per ticker/theme) into a compact row table with health badges (Healthy/Imminent/Stale/Triggered/Broken), nearest-catalyst proximity, kill-criteria summary, and an archive escape hatch — plus a kill-criterion toggle on the existing report page that drives the Triggered state.

**Architecture:** Read-time aggregation, no caching, no scheduler. Two persistent additions: a `kill_criterion_states` table (one row per criterion-per-run that has been flipped from default `armed`) and a nullable `archived_at` column on `research_runs`. Backend service computes health from manual flags (kill criterion `triggered`, `thesis_status == BROKEN`) plus auto heuristics (`stale` if no run in 90d, `imminent` if catalyst within 30d). Frontend polls `/api/status/board` every 60s while the tab is visible and renders a compact row table. Spec: `docs/superpowers/specs/2026-05-04-tier-2-6-status-board-design.md`.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + PostgreSQL (backend), Next.js 16 App Router + React 19 + Tailwind v4 (frontend). No test framework configured per CLAUDE.md — verification is manual smoke (curl) for backend and lint + build + Playwright walkthrough for frontend.

**Branch:** create `feat/status-board` off `main` after Tier 1.3 (PR #20) merges. If PR #20 is still open, branch off `feat/catalyst-calendar` instead so you inherit the catalyst rows the board depends on; rebase onto `main` after the merge.

---

## File structure

**Backend — create:**
- `backend/app/models/kill_criterion_state.py` — `KillCriterionState` ORM model
- `backend/app/migrations/versions/<rev>_add_kill_criterion_states_and_archived_at.py` — Alembic migration
- `backend/app/services/status_board.py` — board aggregator + health resolver + nearest-catalyst helper consumer
- `backend/app/api/status.py` — `GET /api/status/board`, archive/unarchive POSTs, kill-criteria GET/PUT

**Backend — modify:**
- `backend/app/models/__init__.py` — register `KillCriterionState`
- `backend/app/models/research_run.py` — add `archived_at` column
- `backend/app/api/catalysts.py` — extract `nearest_catalyst()` helper (called by `services/status_board.py`); existing `_bucket` continues to use it
- `backend/app/api/pipeline.py` — extend `get_report` to include `kill_criterion_states` array
- `backend/app/main.py` — register `status_router`

**Frontend — create:**
- `frontend/app/status/page.tsx` — the status board page (compact row layout, polling, filter bar)

**Frontend — modify:**
- `frontend/lib/api.ts` — add `Health`, `NextCatalyst`, `KillCriteriaSummary`, `StatusBoardEntry`, `StatusBoardResponse`, `KillCriterionStateOut` types and `status`, `killCriteria` API client objects
- `frontend/components/Nav.tsx` — add `Status` link
- `frontend/components/ThesisCard.tsx` — extend `KillCriteriaSection` to render an `Armed`/`Triggered` toggle per criterion that PUTs to the new endpoint

---

## Task 1: Add `KillCriterionState` ORM model

**Files:**
- Create: `backend/app/models/kill_criterion_state.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the ORM model**

Create `backend/app/models/kill_criterion_state.py`:

```python
"""KillCriterionState — manual flag for one kill criterion in one run.

Default state (`armed`) is implicit absence; only deviations are
persisted. Re-running a thesis produces a new run with no state rows;
state is per-run, not carried forward (matches Catalyst convention).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class KillCriterionState(Base):
    __tablename__ = "kill_criterion_states"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "armed" | "triggered"
    flipped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_kill_criterion_state_run_ordinal"),
    )
```

- [ ] **Step 2: Register in models package**

Edit `backend/app/models/__init__.py`. Add this import alphabetically near the existing model imports:

```python
from backend.app.models.kill_criterion_state import KillCriterionState
```

- [ ] **Step 3: Verify import resolves**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "from backend.app.models import KillCriterionState; print(KillCriterionState.__tablename__)"`

Expected: `kill_criterion_states`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/kill_criterion_state.py backend/app/models/__init__.py
git commit -m "feat(status-board): add KillCriterionState ORM model"
```

---

## Task 2: Add `archived_at` column to `ResearchRun`

**Files:**
- Modify: `backend/app/models/research_run.py`

- [ ] **Step 1: Add the column**

Edit `backend/app/models/research_run.py`. After the `loop_count` column declaration (last line of the class), add:

```python
    # Status board: archive gesture. Null = on the board, non-null = archived.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=None
    )
```

Update the imports at the top of the file. Replace:

```python
from sqlalchemy import ForeignKey, Integer, String
```

with:

```python
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
```

- [ ] **Step 2: Verify the model still imports**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "from backend.app.models import ResearchRun; print(ResearchRun.__table__.columns.keys())"`

Expected output includes `archived_at`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/research_run.py
git commit -m "feat(status-board): add archived_at column to ResearchRun"
```

---

## Task 3: Create Alembic migration

**Files:**
- Create: `backend/migrations/versions/<auto>_add_kill_criterion_states_and_archived_at.py`

- [ ] **Step 1: Generate the migration skeleton**

Run from project root:

```bash
cd /Users/ericwyluda/Development/projects/sector-research && \
  source backend/venv/bin/activate && \
  cd backend && \
  PYTHONPATH=.. alembic revision -m "add_kill_criterion_states_and_archived_at"
```

Expected: a new file printed at `backend/migrations/versions/<rev>_add_kill_criterion_states_and_archived_at.py`. Note the revision id — you'll need it.

- [ ] **Step 2: Replace the migration body**

Replace the file's `upgrade()` and `downgrade()` with the explicit definitions below. Do NOT use `--autogenerate`; the existing catalysts migration was missing a `drop_table` in its downgrade (memory note 3398), and we want this one written by hand.

Confirm the `down_revision` field at the top still equals `'27ee955f03d8'` (the catalysts revision — the previous head). If not, set it to the actual current head shown by `alembic heads` and update accordingly.

```python
"""add kill_criterion_states table and archived_at on research_runs

Revision ID: <use generated rev id>
Revises: 27ee955f03d8
Create Date: <auto>
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '<use generated rev id>'
down_revision: Union[str, None] = '27ee955f03d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kill_criterion_states',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('flipped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['research_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'ordinal', name='uq_kill_criterion_state_run_ordinal'),
    )
    op.create_index(
        'ix_kill_criterion_states_run_id',
        'kill_criterion_states',
        ['run_id'],
        unique=False,
    )

    op.add_column(
        'research_runs',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_research_runs_archived_at',
        'research_runs',
        ['archived_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_research_runs_archived_at', table_name='research_runs')
    op.drop_column('research_runs', 'archived_at')
    op.drop_index('ix_kill_criterion_states_run_id', table_name='kill_criterion_states')
    op.drop_table('kill_criterion_states')
```

- [ ] **Step 3: Apply the migration**

Run from project root:

```bash
cd /Users/ericwyluda/Development/projects/sector-research && \
  source backend/venv/bin/activate && \
  cd backend && alembic upgrade head
```

Expected: log line `Running upgrade 27ee955f03d8 -> <rev>, add_kill_criterion_states_and_archived_at`.

- [ ] **Step 4: Verify schema landed**

Run:

```bash
cd /Users/ericwyluda/Development/projects/sector-research && \
  source backend/venv/bin/activate && \
  python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from backend.app.config import get_settings

async def main():
    eng = create_async_engine(get_settings().database_url)
    async with eng.connect() as c:
        r = await c.execute(text(\"select column_name from information_schema.columns where table_name='kill_criterion_states' order by ordinal_position\"))
        print('kill_criterion_states cols:', [row[0] for row in r])
        r = await c.execute(text(\"select column_name from information_schema.columns where table_name='research_runs' and column_name='archived_at'\"))
        print('archived_at:', r.scalar())
asyncio.run(main())
"
```

Expected: lists the 6 columns and `archived_at` appears.

- [ ] **Step 5: Verify downgrade works (then re-upgrade)**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend && \
  source ../backend/venv/bin/activate && \
  alembic downgrade -1 && \
  alembic upgrade head
```

Expected: downgrade message references the new revision; upgrade re-applies cleanly without error.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*add_kill_criterion_states_and_archived_at.py
git commit -m "feat(status-board): alembic migration — kill_criterion_states + archived_at"
```

---

## Task 4: Extract `nearest_catalyst()` helper from `_bucket`

**Files:**
- Modify: `backend/app/api/catalysts.py`

The status board needs to pick exactly one catalyst per run for the "Next catalyst" column. The bucketing logic in `_bucket` already encodes proximity rules; pull a small helper alongside it so both call sites stay in sync.

- [ ] **Step 1: Add the helper above `_bucket`**

Edit `backend/app/api/catalysts.py`. Just above the existing `def _bucket(...)` (currently around line 71), add:

```python
def nearest_catalyst(rows: list[CatalystRow], today: date) -> CatalystRow | None:
    """Pick the most-imminent still-relevant catalyst from a run's rows.

    Tie-break order:
      1. expected_date >= today, ascending by expected_date
      2. windowed catalysts whose expected_window_end >= today,
         ascending by expected_window_end
      3. first undated catalyst by ordinal (so the row always has
         something to show)
    """
    upcoming = [r for r in rows if r.expected_date is not None and r.expected_date >= today]
    if upcoming:
        upcoming.sort(key=lambda r: r.expected_date)
        return upcoming[0]

    open_window = [
        r for r in rows
        if r.expected_window_end is not None and r.expected_window_end >= today
    ]
    if open_window:
        open_window.sort(key=lambda r: r.expected_window_end)
        return open_window[0]

    undated = [r for r in rows if r.expected_date is None]
    if undated:
        undated.sort(key=lambda r: r.ordinal)
        return undated[0]

    return None
```

- [ ] **Step 2: Verify import works**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "from backend.app.api.catalysts import nearest_catalyst; print(nearest_catalyst.__doc__.splitlines()[0])"`

Expected: `Pick the most-imminent still-relevant catalyst from a run's rows.`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/catalysts.py
git commit -m "refactor(catalysts): extract nearest_catalyst helper for status board"
```

---

## Task 5: Create `services/status_board.py` aggregator

**Files:**
- Create: `backend/app/services/status_board.py`

- [ ] **Step 1: Create the service**

Create `backend/app/services/status_board.py`:

```python
"""Status board aggregator.

Read-time aggregation, no caching. Pulls the latest completed run per
(ticker, theme), joins with catalysts and kill_criterion_states, and
returns one StatusBoardEntry per active thesis with computed health.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.catalysts import CatalystRow, nearest_catalyst
from backend.app.models import Catalyst, KillCriterionState, ResearchRun, Theme

logger = logging.getLogger(__name__)

STALE_DAYS = 90
IMMINENT_DAYS = 30

_HEALTH_SEVERITY = {
    "broken": 4,
    "triggered": 3,
    "stale": 2,
    "imminent": 1,
    "healthy": 0,
}


@dataclass
class KillCriteriaSummary:
    total: int
    triggered: int


@dataclass
class NextCatalyst:
    description: str
    type: str | None
    expected_date: date | None
    expected_window_end: date | None
    days_until: int | None


@dataclass
class StatusBoardEntry:
    ticker: str
    theme_id: str
    theme_name: str
    run_id: str
    thesis_status: str
    conviction_score: int | None
    completed_at: datetime
    days_since_update: int
    health: str
    health_reasons: list[str] = field(default_factory=list)
    next_catalyst: NextCatalyst | None = None
    kill_criteria_summary: KillCriteriaSummary = field(
        default_factory=lambda: KillCriteriaSummary(0, 0)
    )


@dataclass
class StatusBoardResponse:
    entries: list[StatusBoardEntry]
    total: int
    generated_at: datetime


def _to_catalyst_row(c: Catalyst) -> CatalystRow:
    return CatalystRow(
        id=str(c.id),
        run_id=str(c.run_id),
        ticker=c.ticker,
        ordinal=c.ordinal,
        timeframe=c.timeframe,
        description=c.description,
        type=c.type,
        signposts=c.signposts or [],
        linked_pillar=c.linked_pillar,
        expected_date=c.expected_date,
        expected_window_start=c.expected_window_start,
        expected_window_end=c.expected_window_end,
        date_source=c.date_source,
        created_at=c.created_at,
    )


def _build_next_catalyst(rows: list[CatalystRow], today: date) -> NextCatalyst | None:
    chosen = nearest_catalyst(rows, today)
    if chosen is None:
        return None
    if chosen.expected_date is not None:
        days = (chosen.expected_date - today).days
    elif chosen.expected_window_end is not None:
        days = (chosen.expected_window_end - today).days
    else:
        days = None
    return NextCatalyst(
        description=chosen.description,
        type=chosen.type,
        expected_date=chosen.expected_date,
        expected_window_end=chosen.expected_window_end,
        days_until=days,
    )


def _resolve_health(
    thesis_status: str,
    triggered_count: int,
    days_since_update: int,
    next_cat: NextCatalyst | None,
) -> tuple[str, list[str]]:
    """Return (health, reasons). Reasons accumulate every condition that fired."""
    reasons: list[str] = []

    if thesis_status == "BROKEN":
        reasons.append("Thesis marked BROKEN")
    if triggered_count > 0:
        reasons.append(
            f"{triggered_count} kill criteri{'on' if triggered_count == 1 else 'a'} triggered"
        )
    if days_since_update > STALE_DAYS:
        reasons.append(f"No re-run in {days_since_update}d")
    if (
        next_cat is not None
        and next_cat.days_until is not None
        and 0 <= next_cat.days_until <= IMMINENT_DAYS
    ):
        reasons.append(f"Catalyst in {next_cat.days_until}d")
    elif (
        next_cat is not None
        and next_cat.days_until is not None
        and next_cat.days_until < 0
        and next_cat.expected_window_end is not None
    ):
        # window already started but not ended
        reasons.append("Catalyst window in progress")

    if thesis_status == "BROKEN":
        return "broken", reasons
    if triggered_count > 0:
        return "triggered", reasons
    if days_since_update > STALE_DAYS:
        return "stale", reasons
    if (
        next_cat is not None
        and next_cat.days_until is not None
        and next_cat.days_until <= IMMINENT_DAYS
        and (
            next_cat.expected_window_end is None
            or next_cat.expected_window_end >= datetime.now(timezone.utc).date()
        )
    ):
        return "imminent", reasons
    return "healthy", reasons


async def build_status_board(
    db: AsyncSession,
    *,
    theme_id: str | None = None,
    include_archived: bool = False,
) -> StatusBoardResponse:
    """Compute the fleet view from current DB state."""
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)

    # Latest completed/watchlist run per (ticker, theme_id) that isn't archived.
    # Use DISTINCT ON for the per-pair latest selection.
    from sqlalchemy import text

    where_archived = "" if include_archived else "AND r.archived_at IS NULL"
    where_theme = "AND r.theme_id = :theme_id" if theme_id else ""
    params: dict[str, str] = {}
    if theme_id:
        params["theme_id"] = theme_id

    sql = f"""
        SELECT DISTINCT ON (r.ticker, r.theme_id)
            r.id, r.ticker, r.theme_id, r.status, r.state, r.updated_at, r.created_at
        FROM research_runs r
        WHERE r.status IN ('completed', 'watchlist')
          {where_archived}
          {where_theme}
        ORDER BY r.ticker, r.theme_id, r.updated_at DESC
    """
    result = await db.execute(text(sql), params)
    run_rows = result.mappings().all()

    if not run_rows:
        return StatusBoardResponse(entries=[], total=0, generated_at=now)

    run_ids = [str(row["id"]) for row in run_rows]
    theme_ids = list({str(row["theme_id"]) for row in run_rows})

    # Theme name lookup
    theme_result = await db.execute(select(Theme).where(Theme.id.in_(theme_ids)))
    themes_by_id = {t.id: t.name for t in theme_result.scalars()}

    # All catalysts for these runs
    cat_result = await db.execute(select(Catalyst).where(Catalyst.run_id.in_(run_ids)))
    catalysts_by_run: dict[str, list[CatalystRow]] = {}
    for c in cat_result.scalars():
        catalysts_by_run.setdefault(str(c.run_id), []).append(_to_catalyst_row(c))

    # All kill-criterion states for these runs
    kc_result = await db.execute(
        select(KillCriterionState).where(KillCriterionState.run_id.in_(run_ids))
    )
    kc_by_run: dict[str, list[KillCriterionState]] = {}
    for s in kc_result.scalars():
        kc_by_run.setdefault(str(s.run_id), []).append(s)

    entries: list[StatusBoardEntry] = []
    for row in run_rows:
        run_id = str(row["id"])
        state = row["state"] or {}
        phase_outputs = state.get("phase_outputs", {}) if isinstance(state, dict) else {}
        thesis = phase_outputs.get("thesis") or {}
        structured = thesis.get("structured") if isinstance(thesis, dict) else None
        if not isinstance(structured, dict):
            logger.warning(
                "status_board.skip_run",
                extra={"run_id": run_id, "reason": "no thesis structured output"},
            )
            continue

        kill_criteria = structured.get("kill_criteria") or []
        thesis_status = state.get("thesis_status") or "PENDING"
        conviction_score = state.get("conviction_score")
        completed_at = row["updated_at"] or row["created_at"]
        days_since_update = (now - completed_at).days

        rows_for_run = catalysts_by_run.get(run_id, [])
        next_cat = _build_next_catalyst(rows_for_run, today)

        kc_total = len(kill_criteria)
        kc_triggered = sum(
            1
            for s in kc_by_run.get(run_id, [])
            if s.status == "triggered" and 0 <= s.ordinal < kc_total
        )

        health, reasons = _resolve_health(
            thesis_status, kc_triggered, days_since_update, next_cat
        )

        entries.append(
            StatusBoardEntry(
                ticker=row["ticker"],
                theme_id=str(row["theme_id"]),
                theme_name=themes_by_id.get(str(row["theme_id"]), ""),
                run_id=run_id,
                thesis_status=thesis_status,
                conviction_score=conviction_score,
                completed_at=completed_at,
                days_since_update=days_since_update,
                health=health,
                health_reasons=reasons,
                next_catalyst=next_cat,
                kill_criteria_summary=KillCriteriaSummary(
                    total=kc_total, triggered=kc_triggered
                ),
            )
        )

    entries.sort(
        key=lambda e: (
            -_HEALTH_SEVERITY[e.health],
            e.next_catalyst.days_until if e.next_catalyst and e.next_catalyst.days_until is not None else 1_000_000,
            -int(e.completed_at.timestamp()),
        )
    )

    return StatusBoardResponse(entries=entries, total=len(entries), generated_at=now)
```

- [ ] **Step 2: Verify it imports**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "from backend.app.services.status_board import build_status_board, STALE_DAYS, IMMINENT_DAYS; print(STALE_DAYS, IMMINENT_DAYS)"`

Expected: `90 30`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/status_board.py
git commit -m "feat(status-board): aggregator service with health resolver"
```

---

## Task 6: Create `api/status.py` with all endpoints

**Files:**
- Create: `backend/app/api/status.py`

- [ ] **Step 1: Create the router file**

Create `backend/app/api/status.py`:

```python
"""Status board endpoints.

GET  /api/status/board                                   — fleet view
POST /api/runs/{run_id}/archive                          — hide from board
POST /api/runs/{run_id}/unarchive                        — restore
GET  /api/runs/{run_id}/kill-criteria                    — hydrate toggles
PUT  /api/runs/{run_id}/kill-criteria/{ordinal}          — flip one criterion
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models import KillCriterionState, ResearchRun
from backend.app.services.status_board import (
    NextCatalyst as ServiceNextCatalyst,
    StatusBoardEntry as ServiceEntry,
    build_status_board,
)

router = APIRouter()


# ── Wire-format response shapes ─────────────────────────────────────────────


class KillCriteriaSummaryOut(BaseModel):
    total: int
    triggered: int


class NextCatalystOut(BaseModel):
    description: str
    type: str | None
    expected_date: str | None
    expected_window_end: str | None
    days_until: int | None


class StatusBoardEntryOut(BaseModel):
    ticker: str
    theme_id: str
    theme_name: str
    run_id: str
    thesis_status: str
    conviction_score: int | None
    completed_at: str
    days_since_update: int
    health: str
    health_reasons: list[str]
    next_catalyst: NextCatalystOut | None
    kill_criteria_summary: KillCriteriaSummaryOut


class StatusBoardResponseOut(BaseModel):
    entries: list[StatusBoardEntryOut]
    total: int
    generated_at: str


class KillCriterionStateOut(BaseModel):
    ordinal: int
    status: Literal["armed", "triggered"]
    flipped_at: str
    note: str | None


class KillCriterionPutBody(BaseModel):
    status: Literal["armed", "triggered"]
    note: str | None = Field(default=None, max_length=2000)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _serialize_next_catalyst(c: ServiceNextCatalyst | None) -> NextCatalystOut | None:
    if c is None:
        return None
    return NextCatalystOut(
        description=c.description,
        type=c.type,
        expected_date=c.expected_date.isoformat() if c.expected_date else None,
        expected_window_end=c.expected_window_end.isoformat() if c.expected_window_end else None,
        days_until=c.days_until,
    )


def _serialize_entry(e: ServiceEntry) -> StatusBoardEntryOut:
    return StatusBoardEntryOut(
        ticker=e.ticker,
        theme_id=e.theme_id,
        theme_name=e.theme_name,
        run_id=e.run_id,
        thesis_status=e.thesis_status,
        conviction_score=e.conviction_score,
        completed_at=e.completed_at.isoformat(),
        days_since_update=e.days_since_update,
        health=e.health,
        health_reasons=e.health_reasons,
        next_catalyst=_serialize_next_catalyst(e.next_catalyst),
        kill_criteria_summary=KillCriteriaSummaryOut(
            total=e.kill_criteria_summary.total,
            triggered=e.kill_criteria_summary.triggered,
        ),
    )


def _serialize_kc_state(s: KillCriterionState) -> KillCriterionStateOut:
    return KillCriterionStateOut(
        ordinal=s.ordinal,
        status=s.status,  # type: ignore[arg-type]
        flipped_at=s.flipped_at.isoformat(),
        note=s.note,
    )


async def _get_run_or_404(db: AsyncSession, run_id: str) -> ResearchRun:
    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/status/board", response_model=StatusBoardResponseOut)
async def get_status_board(
    theme_id: str | None = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
) -> StatusBoardResponseOut:
    response = await build_status_board(
        db, theme_id=theme_id, include_archived=include_archived
    )
    return StatusBoardResponseOut(
        entries=[_serialize_entry(e) for e in response.entries],
        total=response.total,
        generated_at=response.generated_at.isoformat(),
    )


@router.post("/runs/{run_id}/archive", status_code=204)
async def archive_run(run_id: str, db: AsyncSession = Depends(get_db)) -> None:
    run = await _get_run_or_404(db, run_id)
    run.archived_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/runs/{run_id}/unarchive", status_code=204)
async def unarchive_run(run_id: str, db: AsyncSession = Depends(get_db)) -> None:
    run = await _get_run_or_404(db, run_id)
    run.archived_at = None
    await db.commit()


@router.get(
    "/runs/{run_id}/kill-criteria",
    response_model=list[KillCriterionStateOut],
)
async def list_kill_criterion_states(
    run_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[KillCriterionStateOut]:
    await _get_run_or_404(db, run_id)
    result = await db.execute(
        select(KillCriterionState)
        .where(KillCriterionState.run_id == run_id)
        .order_by(KillCriterionState.ordinal)
    )
    return [_serialize_kc_state(s) for s in result.scalars()]


@router.put(
    "/runs/{run_id}/kill-criteria/{ordinal}",
    response_model=KillCriterionStateOut,
)
async def upsert_kill_criterion_state(
    run_id: str,
    ordinal: int,
    body: KillCriterionPutBody,
    db: AsyncSession = Depends(get_db),
) -> KillCriterionStateOut:
    await _get_run_or_404(db, run_id)
    result = await db.execute(
        select(KillCriterionState).where(
            KillCriterionState.run_id == run_id,
            KillCriterionState.ordinal == ordinal,
        )
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = KillCriterionState(
            run_id=run_id,
            ordinal=ordinal,
            status=body.status,
            note=body.note,
            flipped_at=datetime.now(timezone.utc),
        )
        db.add(state)
    else:
        state.status = body.status
        state.note = body.note
        state.flipped_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(state)
    return _serialize_kc_state(state)
```

- [ ] **Step 2: Verify it imports**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "from backend.app.api.status import router; print([r.path for r in router.routes])"`

Expected: a list of 5 paths matching the docstring.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/status.py
git commit -m "feat(status-board): api endpoints for board, archive, kill-criteria flags"
```

---

## Task 7: Register status router and extend report payload

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/pipeline.py`

- [ ] **Step 1: Register the router**

Edit `backend/app/main.py`. Add the import alongside the other api imports (around line 20):

```python
from backend.app.api.status import router as status_router
```

Then register it after the existing `app.include_router(catalysts_router, ...)` line:

```python
app.include_router(status_router, prefix="/api")
```

- [ ] **Step 2: Extend the report payload**

Edit `backend/app/api/pipeline.py`. Locate the `get_report` function (around line 267). After the `x_signal_velocity` block but before the `return {` block, add:

```python
    # Tier 2.6: kill-criterion state hydration for the report-page toggle UI.
    from backend.app.models import KillCriterionState
    kc_result = await db.execute(
        select(KillCriterionState)
        .where(KillCriterionState.run_id == run_id)
        .order_by(KillCriterionState.ordinal)
    )
    kill_criterion_states = [
        {
            "ordinal": s.ordinal,
            "status": s.status,
            "flipped_at": s.flipped_at.isoformat(),
            "note": s.note,
        }
        for s in kc_result.scalars()
    ]
```

Then in the return dict, add `"kill_criterion_states": kill_criterion_states,` immediately above the `"obsidian": {` line.

- [ ] **Step 3: Boot the server and curl the routes**

Start the dev server (run in background; the user can also start it manually):

```bash
cd /Users/ericwyluda/Development/projects/sector-research && \
  source backend/venv/bin/activate && \
  uvicorn backend.app.main:app --reload &
sleep 3
```

Then:

```bash
curl -s http://localhost:8000/api/status/board | python -m json.tool | head -30
```

Expected: a JSON object with `entries: []`, `total: 0`, `generated_at: "..."` (or actual entries if you have completed runs).

If you have a completed run id at hand:

```bash
RUN=<some-completed-run-uuid>
curl -s -X PUT "http://localhost:8000/api/runs/$RUN/kill-criteria/0" \
  -H 'Content-Type: application/json' \
  -d '{"status":"triggered","note":"smoke test"}' | python -m json.tool
curl -s "http://localhost:8000/api/runs/$RUN/kill-criteria" | python -m json.tool
curl -s -X POST "http://localhost:8000/api/runs/$RUN/archive" -w "\n%{http_code}\n"
curl -s "http://localhost:8000/api/status/board" | python -m json.tool | head
curl -s "http://localhost:8000/api/status/board?include_archived=true" | python -m json.tool | head
curl -s -X POST "http://localhost:8000/api/runs/$RUN/unarchive" -w "\n%{http_code}\n"
```

Expected: PUT returns the new state row with `status: "triggered"`; GET returns `[{ordinal: 0, status: "triggered", ...}]`; archive returns 204 and the run drops from the default board; include_archived shows it again; unarchive returns 204.

Stop the server when done: `pkill -f "uvicorn backend.app.main:app"` (or use `TaskStop` if running via background task).

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/api/pipeline.py
git commit -m "feat(status-board): register router and hydrate kill_criterion_states in report payload"
```

---

## Task 8: Add TypeScript types and API client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add new type declarations**

Edit `frontend/lib/api.ts`. Find the existing `getCatalysts` declaration (around line 975). Immediately after it, add:

```ts
// ── Status board ─────────────────────────────────────────────────────────────

export type Health = "healthy" | "imminent" | "stale" | "triggered" | "broken";

export interface NextCatalyst {
  description: string;
  type: string | null;
  expected_date: string | null;
  expected_window_end: string | null;
  days_until: number | null;
}

export interface KillCriteriaSummary {
  total: number;
  triggered: number;
}

export interface StatusBoardEntry {
  ticker: string;
  theme_id: string;
  theme_name: string;
  run_id: string;
  thesis_status: string;
  conviction_score: number | null;
  completed_at: string;
  days_since_update: number;
  health: Health;
  health_reasons: string[];
  next_catalyst: NextCatalyst | null;
  kill_criteria_summary: KillCriteriaSummary;
}

export interface StatusBoardResponse {
  entries: StatusBoardEntry[];
  total: number;
  generated_at: string;
}

export interface KillCriterionStateOut {
  ordinal: number;
  status: "armed" | "triggered";
  flipped_at: string;
  note: string | null;
}

export const status = {
  board: (opts?: { theme_id?: string; include_archived?: boolean }) => {
    const qs = new URLSearchParams();
    if (opts?.theme_id) qs.set("theme_id", opts.theme_id);
    if (opts?.include_archived) qs.set("include_archived", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return apiFetch<StatusBoardResponse>(`/api/status/board${suffix}`);
  },
  archive: (run_id: string) =>
    apiFetch<void>(`/api/runs/${encodeURIComponent(run_id)}/archive`, {
      method: "POST",
    }),
  unarchive: (run_id: string) =>
    apiFetch<void>(`/api/runs/${encodeURIComponent(run_id)}/unarchive`, {
      method: "POST",
    }),
};

export const killCriteria = {
  list: (run_id: string) =>
    apiFetch<KillCriterionStateOut[]>(
      `/api/runs/${encodeURIComponent(run_id)}/kill-criteria`,
    ),
  set: (
    run_id: string,
    ordinal: number,
    body: { status: "armed" | "triggered"; note?: string },
  ) =>
    apiFetch<KillCriterionStateOut>(
      `/api/runs/${encodeURIComponent(run_id)}/kill-criteria/${ordinal}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
      },
    ),
};
```

Note on the `archive`/`unarchive` 204 responses: the existing `apiFetch` calls `res.json()` which will throw on an empty 204 body. Fix it by tweaking the helper at the top of `lib/api.ts` to handle 204:

Find:

```ts
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}
```

Replace with:

```ts
async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
```

- [ ] **Step 2: Verify TS compiles**

Run: `cd /Users/ericwyluda/Development/projects/sector-research/frontend && npx tsc --noEmit 2>&1 | head -30`

Expected: no errors related to the new code (existing project errors, if any, are out of scope).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(status-board): add types and api client for status board + kill criteria"
```

---

## Task 9: Add `Status` link to the navigation

**Files:**
- Modify: `frontend/components/Nav.tsx`

- [ ] **Step 1: Insert the link**

Edit `frontend/components/Nav.tsx`. Find the `links` array (around line 6). Insert the Status entry between `/catalysts` and `/library`:

```tsx
const links = [
  { href: "/",              label: "Themes"   },
  { href: "/filings",       label: "Filings"  },
  { href: "/catalysts",     label: "Catalysts" },
  { href: "/status",        label: "Status"   },
  { href: "/library",       label: "Library"  },
  { href: "/pipeline/new",  label: "+ New Run" },
];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Nav.tsx
git commit -m "feat(status-board): add Status link to nav"
```

---

## Task 10: Build the `/status` page

**Files:**
- Create: `frontend/app/status/page.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/app/status/page.tsx`:

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  status as statusApi,
  themes as themesApi,
  type Health,
  type StatusBoardEntry,
  type Theme,
} from "@/lib/api";

const HEALTH_PILL: Record<Health, string> = {
  healthy:   "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  imminent:  "bg-blue-500/10 text-blue-400 border-blue-500/30",
  stale:     "bg-slate-500/10 text-slate-400 border-slate-500/30",
  triggered: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  broken:    "bg-red-500/10 text-red-400 border-red-500/30",
};

const HEALTH_LABEL: Record<Health, string> = {
  healthy:   "Healthy",
  imminent:  "Imminent",
  stale:     "Stale",
  triggered: "Triggered",
  broken:    "Broken",
};

const HEALTH_ORDER: (Health | "all")[] = [
  "all", "broken", "triggered", "stale", "imminent", "healthy",
];

function fmtDays(d: number): string {
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  return `${d}d ago`;
}

function fmtCatalystDays(d: number | null): string {
  if (d === null) return "undated";
  if (d < 0) return "in window";
  if (d === 0) return "today";
  return `${d}d`;
}

function HealthPill({ health }: { health: Health }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${HEALTH_PILL[health]}`}
    >
      {HEALTH_LABEL[health]}
    </span>
  );
}

function KillSummary({ total, triggered }: { total: number; triggered: number }) {
  if (total === 0) return <span className="text-[var(--text-faint)]">—</span>;
  if (triggered === 0)
    return (
      <span className="text-[var(--text-muted)]">
        {total} armed
      </span>
    );
  return (
    <span className="text-amber-400 font-medium">
      {total - triggered} armed · {triggered} triggered
    </span>
  );
}

function OverflowMenu({
  archived,
  onArchive,
  onUnarchive,
  onOpen,
}: {
  archived: boolean;
  onArchive: () => void;
  onUnarchive: () => void;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Row menu"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
        className="px-2 py-0.5 text-[var(--text-muted)] hover:text-[var(--text)] rounded"
      >
        ⋯
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 z-10 min-w-[160px] rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg text-xs"
          onMouseDown={(e) => e.preventDefault()}
        >
          <button
            className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)]"
            onClick={(e) => { e.stopPropagation(); onOpen(); setOpen(false); }}
          >
            Open report
          </button>
          {archived ? (
            <button
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)]"
              onClick={(e) => { e.stopPropagation(); onUnarchive(); setOpen(false); }}
            >
              Unarchive
            </button>
          ) : (
            <button
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)] text-amber-400"
              onClick={(e) => { e.stopPropagation(); onArchive(); setOpen(false); }}
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  entry,
  archived,
  onClick,
  onArchive,
  onUnarchive,
}: {
  entry: StatusBoardEntry;
  archived: boolean;
  onClick: () => void;
  onArchive: () => void;
  onUnarchive: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter") onClick(); }}
      className={`grid grid-cols-[80px_110px_60px_minmax(0,1fr)_120px_70px_40px] gap-3 items-center px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--accent-bg)] hover:bg-[var(--surface-alt)] cursor-pointer transition-colors ${archived ? "opacity-50" : ""}`}
    >
      <div className="font-mono font-bold text-sm text-[var(--text)] tracking-wide">
        {entry.ticker}
      </div>
      <div><HealthPill health={entry.health} /></div>
      <div className="font-mono text-sm text-[var(--text)] tabular-nums">
        {entry.conviction_score ?? "—"}
      </div>
      <div className="text-xs text-[var(--text-muted)] truncate">
        {entry.next_catalyst ? (
          <>
            <span className="text-[var(--text)]">{entry.next_catalyst.description}</span>
            <span className="ml-2 text-blue-400 font-medium">
              {fmtCatalystDays(entry.next_catalyst.days_until)}
            </span>
          </>
        ) : (
          <span className="text-[var(--text-faint)]">—</span>
        )}
      </div>
      <div className="text-[11px] text-[var(--text-muted)] truncate">
        {entry.theme_name}
      </div>
      <div className={`text-[11px] tabular-nums ${entry.days_since_update > 90 ? "text-slate-400" : "text-[var(--text-muted)]"}`}>
        {fmtDays(entry.days_since_update)}
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <OverflowMenu
          archived={archived}
          onArchive={onArchive}
          onUnarchive={onUnarchive}
          onOpen={onClick}
        />
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-12 rounded-lg border border-[var(--border)] bg-[var(--surface)] animate-pulse"
        />
      ))}
    </div>
  );
}

export default function StatusPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<StatusBoardEntry[]>([]);
  const [archived, setArchived] = useState<Set<string>>(new Set());
  const [healthFilter, setHealthFilter] = useState<Health | "all">("all");
  const [themeId, setThemeId] = useState<string>("");
  const [themes, setThemes] = useState<Theme[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    themesApi.list().then(setThemes).catch(() => {});
  }, []);

  async function fetchBoard() {
    try {
      const res = await statusApi.board({
        theme_id: themeId || undefined,
        include_archived: includeArchived,
      });
      setEntries(res.entries);
      // Track which entries are currently archived (we sent
      // include_archived=true but the API doesn't tag them — infer from
      // the entry list when toggle is on by checking the next refetch.)
      // Simpler: when include_archived is on, we don't visually distinguish
      // unless we know archived_at. The API exposes it implicitly by the
      // fact they're absent when include_archived=false. Compute the set
      // by diff'ing against an include_archived=false fetch.
      if (includeArchived) {
        const visible = await statusApi.board({
          theme_id: themeId || undefined,
          include_archived: false,
        });
        const visibleIds = new Set(visible.entries.map((e) => e.run_id));
        setArchived(new Set(res.entries.filter((e) => !visibleIds.has(e.run_id)).map((e) => e.run_id)));
      } else {
        setArchived(new Set());
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load board");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchBoard();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchBoard();
    };
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") fetchBoard();
    }, 60_000);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeId, includeArchived]);

  const counts = useMemo(() => {
    const c: Record<Health | "all", number> = {
      all: entries.length,
      broken: 0,
      triggered: 0,
      stale: 0,
      imminent: 0,
      healthy: 0,
    };
    for (const e of entries) c[e.health]++;
    return c;
  }, [entries]);

  const filtered = useMemo(
    () =>
      healthFilter === "all"
        ? entries
        : entries.filter((e) => e.health === healthFilter),
    [entries, healthFilter],
  );

  async function archiveEntry(run_id: string) {
    await statusApi.archive(run_id);
    fetchBoard();
  }

  async function unarchiveEntry(run_id: string) {
    await statusApi.unarchive(run_id);
    fetchBoard();
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 flex flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold text-[var(--text)] tracking-wide">
          Status Board
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Active theses with health, catalyst proximity, and kill-criteria flags.
        </p>
      </header>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={themeId}
          onChange={(e) => setThemeId(e.target.value)}
          className="px-3 py-1.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--text)]"
        >
          <option value="">All themes</option>
          {themes.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <div className="flex items-center gap-1.5 flex-wrap">
          {HEALTH_ORDER.map((k) => (
            <button
              key={k}
              onClick={() => setHealthFilter(k)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors flex items-center gap-1.5 ${
                healthFilter === k
                  ? "bg-[var(--accent-bg)] text-[var(--primary-dk)]"
                  : "bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)] hover:text-[var(--text)]"
              }`}
            >
              <span>{k === "all" ? "All" : HEALTH_LABEL[k]}</span>
              <span className="text-[10px] tabular-nums font-mono opacity-70">
                {counts[k]}
              </span>
            </button>
          ))}
        </div>

        <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Include archived
        </label>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <Skeleton />
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 space-y-2">
          <p className="text-[var(--text-muted)] text-sm">
            {entries.length === 0
              ? "No active theses yet."
              : `No ${healthFilter === "all" ? "" : HEALTH_LABEL[healthFilter as Health].toLowerCase() + " "}theses.`}
          </p>
          {entries.length === 0 && (
            <button
              onClick={() => router.push("/pipeline/new")}
              className="px-4 py-1.5 rounded-md bg-[var(--accent-bg)] text-[var(--primary-dk)] text-xs font-semibold"
            >
              Start a new run →
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          {/* Column header */}
          <div className="grid grid-cols-[80px_110px_60px_minmax(0,1fr)_120px_70px_40px] gap-3 px-3 py-1 text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
            <div>Ticker</div>
            <div>Health</div>
            <div>Conv</div>
            <div>Next catalyst</div>
            <div>Theme</div>
            <div>Refreshed</div>
            <div></div>
          </div>
          {filtered.map((e) => (
            <Row
              key={e.run_id}
              entry={e}
              archived={archived.has(e.run_id)}
              onClick={() => router.push(`/pipeline/${e.run_id}`)}
              onArchive={() => archiveEntry(e.run_id)}
              onUnarchive={() => unarchiveEntry(e.run_id)}
            />
          ))}
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Verify lint and build**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && \
  npm run lint 2>&1 | tail -20
```

Expected: no errors in `app/status/page.tsx` or `lib/api.ts`. Pre-existing lint warnings elsewhere are out of scope.

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && \
  npm run build 2>&1 | tail -30
```

Expected: build succeeds; `/status` listed in the route summary.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/status/page.tsx
git commit -m "feat(status-board): /status page with row table, filters, polling"
```

---

## Task 11: Add the kill-criterion toggle to the report page

**Files:**
- Modify: `frontend/lib/api.ts` (add `kill_criterion_states?` to `ReportResponse`)
- Modify: `frontend/components/ThesisCard.tsx`
- Modify: `frontend/app/pipeline/[runId]/page.tsx` (thread the new props down)

- [ ] **Step 1: Extend the `ReportResponse` type**

Edit `frontend/lib/api.ts`. The `ReportResponse` interface starts at line 829. Add the new field as the last property before the closing `}` of the interface (immediately after the `obsidian: { ... }` block):

```ts
  kill_criterion_states?: KillCriterionStateOut[];
```

The `KillCriterionStateOut` type was added in Task 8, so it's already in scope.

- [ ] **Step 2: Update `ThesisCard.tsx` to render and persist toggles**

Edit `frontend/components/ThesisCard.tsx`. Add to the imports at the top:

```tsx
import { useState } from "react";
import { killCriteria, type KillCriterionStateOut } from "@/lib/api";
```

Find the `KillCriteriaSection` function (around line 79). Replace its signature and body so it accepts `runId` and the initial `states` array, and renders an inline toggle per criterion:

```tsx
function KillCriteriaSection({
  items,
  states: initialStates,
  runId,
  onPillarHover,
}: {
  items: KillCriterion[];
  states: KillCriterionStateOut[];
  runId: string;
  onPillarHover: (p: string | null) => void;
}) {
  const [collapsed, setCollapsed] = usePersistedCollapse(
    "thesis-kill-criteria",
    true,
  );
  const [states, setStates] = useState<KillCriterionStateOut[]>(initialStates);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function statusOf(ordinal: number): "armed" | "triggered" {
    return states.find((s) => s.ordinal === ordinal)?.status ?? "armed";
  }

  async function flip(ordinal: number, next: "armed" | "triggered", note: string) {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await killCriteria.set(runId, ordinal, {
        status: next,
        note: note || undefined,
      });
      setStates((prev) => {
        const without = prev.filter((s) => s.ordinal !== ordinal);
        return [...without, res].sort((a, b) => a.ordinal - b.ordinal);
      });
      setEditing(null);
      setDraftNote("");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
      <button
        type="button"
        aria-expanded={!collapsed}
        aria-controls="thesis-kill-criteria-panel"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3.5 py-2.5"
      >
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Kill Criteria · {items.length}
        </span>
        <span className="text-[10px] text-[var(--text-faint)] font-mono">
          {collapsed ? "+" : "−"}
        </span>
      </button>
      {!collapsed && (
        <div id="thesis-kill-criteria-panel" className="px-3.5 pb-3 flex flex-col gap-2">
          {items.map((k, i) => {
            const cur = statusOf(i);
            const isEditing = editing === i;
            return (
              <div
                key={i}
                className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 flex flex-col gap-1.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-[11px] font-semibold text-[var(--text)] leading-snug flex-1">
                    {k.condition}
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const note = states.find((s) => s.ordinal === i)?.note ?? "";
                      setDraftNote(note);
                      setEditing(isEditing ? null : i);
                      setSaveError(null);
                    }}
                    className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${
                      cur === "triggered"
                        ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        : "bg-slate-500/10 text-slate-400 border-slate-500/30"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${cur === "triggered" ? "bg-amber-400" : "bg-slate-400"}`} />
                    {cur === "triggered" ? "Triggered" : "Armed"}
                  </button>
                </div>
                <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                  <span className="font-mono text-[var(--text-faint)]">trigger</span>{" "}
                  {k.threshold}
                </div>
                <div className="flex items-center gap-2 flex-wrap mt-0.5">
                  <span className="text-[9px] font-mono text-[var(--text-faint)]">
                    watch: {k.monitoring_source}
                  </span>
                  {k.kills_pillar && (
                    <PillarChip
                      pillar={k.kills_pillar}
                      prefix="kills"
                      onHover={onPillarHover}
                    />
                  )}
                </div>

                {isEditing && (
                  <div className="mt-1.5 flex flex-col gap-1.5 border-t border-[var(--border)] pt-1.5">
                    <textarea
                      value={draftNote}
                      onChange={(e) => setDraftNote(e.target.value)}
                      placeholder="Optional note (what triggered it?)"
                      className="w-full text-[11px] bg-[var(--surface-alt)] border border-[var(--border)] rounded px-2 py-1 resize-y min-h-[40px]"
                    />
                    <div className="flex gap-2 items-center">
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() =>
                          flip(i, cur === "triggered" ? "armed" : "triggered", draftNote)
                        }
                        className="px-2 py-0.5 rounded bg-[var(--accent-bg)] text-[var(--primary-dk)] text-[10px] font-semibold disabled:opacity-50"
                      >
                        {saving ? "Saving…" : cur === "triggered" ? "Mark Armed" : "Mark Triggered"}
                      </button>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => { setEditing(null); setDraftNote(""); setSaveError(null); }}
                        className="px-2 py-0.5 rounded text-[10px] text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        Cancel
                      </button>
                      {saveError && (
                        <span className="text-[10px] text-red-400">{saveError}</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Thread `runId` and `killCriterionStates` through `ThesisCard`**

In `frontend/components/ThesisCard.tsx`:

3a. Find the `Props` interface near the top of the file. Add two new fields:

```tsx
runId: string;
killCriterionStates: KillCriterionStateOut[];
```

3b. Update the `ThesisCard` component signature (line 193) to destructure them:

```tsx
export function ThesisCard({
  structured,
  citations = [],
  ticker,
  thesisStatus,
  runId,
  killCriterionStates,
}: Props) {
```

3c. Update the `<KillCriteriaSection ...>` JSX (around line 268) to pass them through:

```tsx
{killCriteria.length > 0 && (
  <KillCriteriaSection
    items={killCriteria}
    states={killCriterionStates}
    runId={runId}
    onPillarHover={setHighlightedPillar}
  />
)}
```

- [ ] **Step 4: Pass the new props from the pipeline page**

In `frontend/app/pipeline/[runId]/page.tsx`, locate the `<ThesisCard ... />` JSX at line 677 and add the new props. The `runId` is already in scope from `useParams` (line 152) and `report` is in scope from `useState` (line 157):

```tsx
<ThesisCard
  structured={thesisStructured}
  citations={citations}
  ticker={ticker}
  thesisStatus={thesisStatus}
  runId={runId}
  killCriterionStates={report?.kill_criterion_states ?? []}
/>
```

- [ ] **Step 5: Verify lint and build**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && \
  npm run lint 2>&1 | tail -15 && \
  npm run build 2>&1 | tail -15
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/ThesisCard.tsx frontend/lib/api.ts frontend/app/pipeline/\[runId\]/page.tsx
git commit -m "feat(status-board): inline armed/triggered toggle on report page kill criteria"
```

---

## Task 12: Manual end-to-end smoke walkthrough

**Files:** none modified.

This is the verification gate per CLAUDE.md (no test framework). Run through the full flow.

- [ ] **Step 1: Start backend and frontend**

```bash
cd /Users/ericwyluda/Development/projects/sector-research && \
  source backend/venv/bin/activate && \
  uvicorn backend.app.main:app --reload &
```

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && \
  npm run dev &
```

Wait ~5 seconds for both to come up.

- [ ] **Step 2: Verify the board loads with current data**

Open http://localhost:3000/status in a browser. Expected:

- Page title "Status Board"
- One row per active completed thesis (latest run per ticker/theme)
- Each row shows: ticker, health pill, conviction, next catalyst, theme, refresh recency, ⋯ menu
- Skeleton flashes briefly on first load
- Filter pills show counts that sum to total

If you have no completed runs, you'll see the empty state with a "Start a new run" CTA. If so, run a fresh thesis to completion before continuing.

- [ ] **Step 3: Verify health-state transitions**

Pick a completed run that's currently `Healthy`.

a) Open `/pipeline/<run_id>`, locate the Kill Criteria section, expand it. Click the `Armed` pill on the first criterion. The inline editor appears. Click `Mark Triggered`. Pill should flip to `Triggered`.

b) Switch back to `/status` (don't refresh — let the 60s poll do it, or refresh to skip the wait). The same row's health badge should show `Triggered` and the kill summary should show `N-1 armed · 1 triggered`.

c) Back on the report page, flip the same criterion back to `Armed`. After re-poll, the badge returns to `Healthy`.

- [ ] **Step 4: Verify Imminent**

If you have a run whose nearest catalyst is `<= 30 days` out, its health badge should be `Imminent` with `health_reasons` mentioning the days-until. If not, manually patch a catalyst date for testing:

```bash
psql $DATABASE_URL_SYNC -c "
UPDATE catalysts
SET expected_date = current_date + interval '15 days', expected_window_end = NULL
WHERE id = (SELECT id FROM catalysts WHERE run_id = '<some_run_id>' LIMIT 1);
"
```

Refresh `/status` — the row should flip to `Imminent`.

- [ ] **Step 5: Verify Stale**

Pick a run, manually antedate it:

```bash
psql $DATABASE_URL_SYNC -c "
UPDATE research_runs
SET updated_at = now() - interval '100 days'
WHERE id = '<some_run_id>';
"
```

Refresh `/status` — the row should be `Stale` with refresh column slate-tinted at "100d ago".

- [ ] **Step 6: Verify Archive / Unarchive**

On `/status`, click the ⋯ menu of any row → `Archive`. The row disappears. Toggle `Include archived` on — it reappears at 50% opacity. Click ⋯ → `Unarchive`. It returns to full opacity.

- [ ] **Step 7: Verify theme + health filters**

Pick a theme from the dropdown — only that theme's runs should show. Click each health filter pill — only matching rows render; "All" returns to full list.

- [ ] **Step 8: Verify polling**

Open browser devtools → Network. Wait 60s — confirm a fresh `GET /api/status/board` fires. Switch to another tab; wait 90s; come back — confirm no fetches happened while hidden.

- [ ] **Step 9: Stop dev servers**

```bash
pkill -f "uvicorn backend.app.main:app"
pkill -f "next dev"
```

(Or use `TaskStop` on the background tasks if you used those.)

- [ ] **Step 10: Final commit if any drift**

If steps 4–5 left dirty test data in the DB, restore it:

```bash
psql $DATABASE_URL_SYNC -c "
UPDATE research_runs SET updated_at = created_at WHERE updated_at < created_at;
-- Restore any catalyst dates you changed manually as needed.
"
```

No code changes from this task should remain — the smoke walkthrough is read-only on disk.

---

## Definition of done

- All 12 tasks completed and committed.
- `/status` page lives at http://localhost:3000/status with row-table layout matching the spec mockups.
- Health badges compute correctly across all five states (verified in walkthrough Steps 3–6).
- Kill-criterion toggle on `/pipeline/[runId]` persists to `kill_criterion_states` and propagates to the board within one polling tick.
- Archive / unarchive round-trips work; archived rows hidden by default and visible via toggle.
- Migration applies forward and back cleanly (verified in Task 3 Step 5).
- `npm run lint` clean for new code; `npm run build` succeeds.
- Branch `feat/status-board` ready for PR.

## Out of scope (per spec non-goals)

- Badge transition history / audit trail
- Notifications
- LLM auto-evaluation of kill criteria
- Batch kill-criterion edits
- Theme-grouped roll-ups
- CSV/PDF export
- Click-sort table columns
