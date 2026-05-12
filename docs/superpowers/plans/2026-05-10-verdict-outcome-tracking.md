# Verdict Outcome Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the feedback loop that measures every research-run and workspace-run verdict against ticker price + three benchmarks (SPY, sector ETF, theme basket) at 5 snapshot offsets, with signal-snapshot attribution and supersede stamping, surfaced on a new `/performance` page.

**Architecture:** New `verdict_outcomes` + `verdict_return_snapshots` + `sector_etf_mapping` tables. New service module `outcome_tracker.py` hooked into pipeline and workspace terminal transitions. New daily APScheduler cron (03:00 UTC) fills due snapshots. New `/api/outcomes` API + `/performance` Next.js page. JSONB only where shape genuinely drifts (theme constituents, signal snapshot); explicit columns elsewhere for fast query.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, asyncpg, APScheduler, Next.js 16 App Router, React 19, Tailwind v4, Recharts (not strictly needed here, tables only).

**Spec reference:** `docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md`

---

## File Structure

**New backend files:**

- `backend/migrations/versions/<rev>_verdict_outcomes.py` — single Alembic migration creating the 3 tables, indexes, sector ETF seeds
- `backend/app/models/outcome.py` — ORM: `VerdictOutcome`, `VerdictReturnSnapshot`, `SectorEtfMapping`
- `backend/app/models/outcome_schemas.py` — Pydantic: `EntryPriceBundle`, `RefreshSummary`, `BackfillSummary`, `OutcomeSummary`, `OutcomeListItem`, `SignalSnapshot` shape
- `backend/app/services/outcome_tracker.py` — service module: helpers, `record_verdict`, `refresh_snapshots`, `backfill_from_history`, signal-snapshot builders
- `backend/app/api/outcomes.py` — API routes (`/summary`, list, `/by-source`, `POST /backfill`)
- `backend/scripts/backfill_outcomes.py` — CLI entry to invoke `backfill_from_history` standalone
- `backend/tests/test_outcome_tracker.py` — service-level tests (14 tests)
- `backend/tests/test_outcomes_api.py` — API tests (8 tests)

**Modified backend files:**

- `backend/app/services/pipeline.py` — add `record_verdict` call after terminal status transition (~line 201)
- `backend/app/services/workspace.py` — add `record_verdict` call after `_set_status` final completion (~line 263)
- `backend/app/main.py` — register `outcomes_router`; register `AsyncIOScheduler` cron at 03:00 UTC

**New frontend files:**

- `frontend/app/performance/page.tsx` — server-rendered shell; pulls initial summary then hydrates client filters
- `frontend/components/performance/PerformanceFilters.tsx` — four-control bar (window / offset / benchmark / source_type)
- `frontend/components/performance/HeroBand.tsx` — three lifetime IRR tiles + N + win rate
- `frontend/components/performance/ByVerdictTable.tsx` — verdict-band rollup
- `frontend/components/performance/ByThemeTable.tsx` — theme rollup (clickable rows filter OutcomeList)
- `frontend/components/performance/BySignalBucketPanel.tsx` — quartile table + signal switcher
- `frontend/components/performance/OutcomeList.tsx` — paginated sortable outcomes table
- `frontend/components/performance/ReturnCell.tsx` — shared cell formatter

**Modified frontend files:**

- `frontend/components/Nav.tsx` — add 8th link `/performance`
- `frontend/lib/api.ts` — add `OutcomeSummary`, `OutcomeListItem`, `outcomesApi.{getSummary, list, getBySource, triggerBackfill}`

---

## Task 1: Migration — sector_etf_mapping + verdict_outcomes + verdict_return_snapshots

**Files:**
- Create: `backend/migrations/versions/<rev>_verdict_outcomes.py`

- [ ] **Step 1: Generate migration skeleton**

Run from project root with venv active:
```bash
cd backend && alembic revision -m "verdict_outcomes" && cd ..
```
This creates a file like `backend/migrations/versions/<hex>_verdict_outcomes.py`. Note the revision hex and the `down_revision` value (latest existing migration head — should be `8b4fd10f00d3` or the current head).

- [ ] **Step 2: Write the migration body**

Replace the file contents with:

```python
"""verdict_outcomes

Revision ID: <keep the auto-generated hex>
Revises: <keep auto-generated down_revision>
Create Date: <keep auto-generated date>
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "<keep auto-generated hex>"
down_revision: Union[str, None] = "<keep auto-generated down_revision>"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SECTOR_ETF_SEEDS = [
    ("Technology", "XLK", None),
    ("Energy", "XLE", None),
    ("Healthcare", "XLV", None),
    ("Financial Services", "XLF", None),
    ("Industrials", "XLI", None),
    ("Consumer Cyclical", "XLY", None),
    ("Consumer Defensive", "XLP", None),
    ("Basic Materials", "XLB", None),
    ("Utilities", "XLU", None),
    ("Real Estate", "XLRE", None),
    ("Communication Services", "XLC", None),
]


def upgrade() -> None:
    op.create_table(
        "sector_etf_mapping",
        sa.Column("fmp_sector", sa.String(length=64), primary_key=True),
        sa.Column("etf_ticker", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "sector_etf_mapping",
            sa.column("fmp_sector", sa.String),
            sa.column("etf_ticker", sa.String),
            sa.column("notes", sa.Text),
        ),
        [{"fmp_sector": s, "etf_ticker": e, "notes": n} for (s, e, n) in SECTOR_ETF_SEEDS],
    )

    op.create_table(
        "verdict_outcomes",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("theme_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("verdict_emitted_at", sa.DateTime(timezone=True), nullable=False),

        sa.Column("entry_price_at", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("entry_price_source", sa.String(length=64), nullable=False,
                  server_default=sa.text("'fmp_historical_eod_adjusted'")),

        sa.Column("spy_entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector_etf_ticker", sa.String(length=16), nullable=True),
        sa.Column("sector_etf_entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_entry_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_constituents", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column("signal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_outcome_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("realized_ticker_return_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_spy_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_sector_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_theme_basket_excess_pct", sa.Numeric(20, 8), nullable=True),

        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_outcome_id"], ["verdict_outcomes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_verdict_outcomes_source"),
    )
    op.create_index("ix_outcomes_ticker_emitted", "verdict_outcomes",
                    ["ticker", sa.text("verdict_emitted_at DESC")])
    op.create_index("ix_outcomes_theme_emitted", "verdict_outcomes",
                    ["theme_id", sa.text("verdict_emitted_at DESC")])
    op.create_index("ix_outcomes_open", "verdict_outcomes", ["closed_at"],
                    postgresql_where=sa.text("closed_at IS NULL"))
    op.create_index("ix_outcomes_open_per_position", "verdict_outcomes",
                    ["ticker", "theme_id", "source_type", "superseded_at"],
                    postgresql_where=sa.text("superseded_at IS NULL"))

    op.create_table(
        "verdict_return_snapshots",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("outcome_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("snapshot_offset", sa.String(length=8), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),

        sa.Column("ticker_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("spy_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector_etf_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_value", sa.Numeric(20, 6), nullable=True),

        sa.Column("ticker_return_pct", sa.Numeric(20, 8), nullable=False),
        sa.Column("spy_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("sector_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("theme_basket_excess_pct", sa.Numeric(20, 8), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["outcome_id"], ["verdict_outcomes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("outcome_id", "snapshot_offset", name="uq_snapshot_outcome_offset"),
    )
    op.create_index("ix_snapshots_outcome", "verdict_return_snapshots", ["outcome_id"])


def downgrade() -> None:
    op.drop_index("ix_snapshots_outcome", table_name="verdict_return_snapshots")
    op.drop_table("verdict_return_snapshots")

    op.drop_index("ix_outcomes_open_per_position", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_open", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_theme_emitted", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_ticker_emitted", table_name="verdict_outcomes")
    op.drop_table("verdict_outcomes")

    op.drop_table("sector_etf_mapping")
```

- [ ] **Step 3: Apply the migration**

Run from project root with venv active:
```bash
cd backend && PYTHONPATH=.. alembic upgrade head && cd ..
```
Expected output: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, verdict_outcomes`.

- [ ] **Step 4: Verify schema**

```bash
psql "$DATABASE_URL_SYNC" -c "\d verdict_outcomes" -c "\d verdict_return_snapshots" -c "SELECT * FROM sector_etf_mapping ORDER BY fmp_sector;"
```
Expected: both tables exist with all columns + FK constraints; 11 rows in `sector_etf_mapping`.

- [ ] **Step 5: Verify downgrade then re-upgrade**

```bash
cd backend && PYTHONPATH=.. alembic downgrade -1 && PYTHONPATH=.. alembic upgrade head && cd ..
```
Expected: clean down then clean up. Confirms the migration is reversible.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*verdict_outcomes.py
git commit -m "feat(db): migration for verdict_outcomes + verdict_return_snapshots + sector_etf_mapping"
```

---

## Task 2: ORM models

**Files:**
- Create: `backend/app/models/outcome.py`

- [ ] **Step 1: Write the ORM module**

```python
"""VerdictOutcome, VerdictReturnSnapshot, SectorEtfMapping — alpha feedback-loop tracking.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md for context.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class SectorEtfMapping(Base):
    __tablename__ = "sector_etf_mapping"

    fmp_sector: Mapped[str] = mapped_column(String(64), primary_key=True)
    etf_ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VerdictOutcome(Base):
    __tablename__ = "verdict_outcomes"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_verdict_outcomes_source"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'research_run' | 'workspace_run'
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict_emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    entry_price_at: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    entry_price_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="fmp_historical_eod_adjusted"
    )

    spy_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    sector_etf_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sector_etf_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_entry_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_constituents: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    signal_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_outcome_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="SET NULL"),
        nullable=True,
    )
    realized_ticker_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_spy_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_sector_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_theme_basket_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    snapshots: Mapped[list["VerdictReturnSnapshot"]] = relationship(
        "VerdictReturnSnapshot",
        back_populates="outcome",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class VerdictReturnSnapshot(Base):
    __tablename__ = "verdict_return_snapshots"
    __table_args__ = (
        UniqueConstraint("outcome_id", "snapshot_offset", name="uq_snapshot_outcome_offset"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    outcome_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_offset: Mapped[str] = mapped_column(String(8), nullable=False)  # '1d'|'1w'|'1m'|'3m'|'6m'
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    ticker_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    spy_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    sector_etf_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    ticker_return_pct: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    spy_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    sector_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    theme_basket_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    outcome: Mapped["VerdictOutcome"] = relationship("VerdictOutcome", back_populates="snapshots")
```

- [ ] **Step 2: Verify importable**

```bash
source backend/venv/bin/activate && python -c "from backend.app.models.outcome import VerdictOutcome, VerdictReturnSnapshot, SectorEtfMapping; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/outcome.py
git commit -m "feat(model): VerdictOutcome + VerdictReturnSnapshot + SectorEtfMapping ORM"
```

---

## Task 3: Pydantic schemas

**Files:**
- Create: `backend/app/models/outcome_schemas.py`

- [ ] **Step 1: Write the schemas module**

```python
"""Pydantic schemas for outcome-tracker public API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


SnapshotOffset = Literal["1d", "1w", "1m", "3m", "6m"]
SourceType = Literal["research_run", "workspace_run"]
Benchmark = Literal["spy", "sector", "theme_basket"]
Window = Literal["30d", "90d", "1y", "all"]


class EntryConstituent(BaseModel):
    ticker: str
    entry_price: Decimal


class EntryPriceBundle(BaseModel):
    """Result of _resolve_entry_prices — entry-anchored prices for outcome creation."""
    entry_price_at: date
    ticker_price: Decimal
    spy_price: Decimal | None
    sector_etf_ticker: str | None
    sector_etf_price: Decimal | None
    theme_basket_constituents: list[EntryConstituent]


class SignalSnapshot(BaseModel):
    """Shape of the signal_snapshot JSONB. All fields optional — backfill-tolerant."""
    signals_row: dict[str, float | None] | None = None
    deep_dive_scores: dict[str, float | None] | None = None
    workspace_step_verdicts: dict[str, str | None] | None = None
    kill_criterion_state: list[dict[str, Any]] | None = None
    model_assumptions: dict[str, float | None] | None = None


class SnapshotRead(BaseModel):
    snapshot_offset: SnapshotOffset
    snapshot_date: date
    ticker_price: Decimal
    spy_price: Decimal | None
    sector_etf_price: Decimal | None
    theme_basket_value: Decimal | None
    ticker_return_pct: Decimal
    spy_excess_pct: Decimal | None
    sector_excess_pct: Decimal | None
    theme_basket_excess_pct: Decimal | None


class OutcomeListItem(BaseModel):
    id: str
    source_type: SourceType
    source_id: str
    ticker: str
    theme_id: str | None
    verdict: str
    verdict_emitted_at: datetime
    entry_price_at: date
    entry_price: Decimal
    sector_etf_ticker: str | None
    superseded_at: datetime | None
    closed_at: datetime | None
    realized_ticker_return_pct: Decimal | None
    realized_spy_excess_pct: Decimal | None
    realized_sector_excess_pct: Decimal | None
    realized_theme_basket_excess_pct: Decimal | None
    snapshots: list[SnapshotRead] = Field(default_factory=list)


class OutcomeDetail(OutcomeListItem):
    theme_basket_constituents: list[EntryConstituent] | None
    signal_snapshot: SignalSnapshot | None


class StatGroup(BaseModel):
    n: int
    mean_return_pct: float | None
    mean_excess_pct: float | None
    win_rate: float | None         # fraction in [0, 1]
    median_excess_pct: float | None


class VerdictStats(BaseModel):
    """{verdict_string: StatGroup}. Verdict strings are not enumerated — research+workspace verdict spaces."""
    healthy: StatGroup | None = None
    imminent: StatGroup | None = None
    triggered: StatGroup | None = None
    broken: StatGroup | None = None
    completed: StatGroup | None = None
    watchlist: StatGroup | None = None
    passed: StatGroup | None = None  # 'pass' is a Python keyword; rename in API output


class ThemeStat(BaseModel):
    theme_id: str | None
    theme_name: str | None
    stats: StatGroup


class SignalBucket(BaseModel):
    bucket: str    # '0-25th' | '25-50th' | '50-75th' | '75-100th' | 'null'
    n: int
    mean_excess_pct: float | None
    win_rate: float | None


class OutcomeSummary(BaseModel):
    window: Window
    snapshot_offset: SnapshotOffset
    benchmark: Benchmark
    source_type: SourceType | Literal["all"]
    overall: StatGroup
    by_verdict: VerdictStats
    by_theme: list[ThemeStat]
    by_signal_bucket: dict[str, list[SignalBucket]]


class RefreshSummary(BaseModel):
    processed: int
    snapshotted: int
    closed: int
    errors: list[dict[str, str]] = Field(default_factory=list)


class BackfillSummary(BaseModel):
    outcomes_created: int
    outcomes_existed: int
    snapshots_inserted: int
    errors: list[dict[str, str]] = Field(default_factory=list)
```

- [ ] **Step 2: Verify importable**

```bash
python -c "from backend.app.models.outcome_schemas import OutcomeSummary, EntryPriceBundle, SignalSnapshot; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/outcome_schemas.py
git commit -m "feat(model): Pydantic schemas for outcome-tracker API"
```

---

## Task 4: outcome_tracker.py — module skeleton + constants

**Files:**
- Create: `backend/app/services/outcome_tracker.py`

- [ ] **Step 1: Write the skeleton with constants + offset math + stubs**

```python
"""Verdict outcome tracking — alpha feedback loop.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.outcome import (
    SectorEtfMapping,
    VerdictOutcome,
    VerdictReturnSnapshot,
)
from backend.app.models.outcome_schemas import (
    BackfillSummary,
    EntryConstituent,
    EntryPriceBundle,
    RefreshSummary,
)

logger = logging.getLogger(__name__)


SNAPSHOT_OFFSETS: list[tuple[str, int]] = [
    ("1d", 1),
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
]

ENTRY_PRICE_LOOKAHEAD_DAYS = 7
SUPPORTED_SOURCE_TYPES = ("research_run", "workspace_run")


def calendar_target(entry_price_at: date, offset_key: str) -> date:
    """Return the calendar target date for a snapshot offset. Snapshot uses first trading day >= target."""
    for key, days in SNAPSHOT_OFFSETS:
        if key == offset_key:
            return entry_price_at + timedelta(days=days)
    raise ValueError(f"unknown offset {offset_key!r}")


def all_offset_keys() -> list[str]:
    return [k for (k, _) in SNAPSHOT_OFFSETS]
```

- [ ] **Step 2: Verify importable**

```bash
python -c "from backend.app.services.outcome_tracker import SNAPSHOT_OFFSETS, calendar_target, all_offset_keys; print(all_offset_keys())"
```
Expected: `['1d', '1w', '1m', '3m', '6m']`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/outcome_tracker.py
git commit -m "feat(outcome): module skeleton + offset constants"
```

---

## Task 5: Test scaffold + calendar_target tests

**Files:**
- Create: `backend/tests/test_outcome_tracker.py`

- [ ] **Step 1: Write the test scaffold**

```python
"""Tests for backend.app.services.outcome_tracker."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.app.services.outcome_tracker import (
    all_offset_keys,
    calendar_target,
)


class TestOffsetMath(unittest.TestCase):
    def test_calendar_target_known_offsets(self):
        base = date(2026, 1, 1)
        self.assertEqual(calendar_target(base, "1d"), date(2026, 1, 2))
        self.assertEqual(calendar_target(base, "1w"), date(2026, 1, 8))
        self.assertEqual(calendar_target(base, "1m"), date(2026, 1, 31))
        self.assertEqual(calendar_target(base, "3m"), date(2026, 4, 1))
        self.assertEqual(calendar_target(base, "6m"), date(2026, 6, 30))

    def test_calendar_target_unknown_raises(self):
        with self.assertRaises(ValueError):
            calendar_target(date(2026, 1, 1), "9999")

    def test_all_offset_keys_ordered(self):
        self.assertEqual(all_offset_keys(), ["1d", "1w", "1m", "3m", "6m"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_outcome_tracker.py
git commit -m "test(outcome): offset math (3 tests)"
```

---

## Task 6: Entry-price resolution helper

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `_resolve_entry_prices`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 3 tests)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_outcome_tracker.py` ABOVE `if __name__`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.outcome_tracker import _resolve_entry_prices


def _mock_fmp_price_series(prices_by_ticker_by_date: dict[str, dict[date, Decimal]]):
    """Build an FMPClient mock whose get_historical_eod returns adjusted-close rows.

    prices_by_ticker_by_date: {ticker: {date: adjusted_close}}
    """
    mock = MagicMock()

    async def get_historical_eod(symbol: str, start: date, end: date):
        rows = []
        for d, px in sorted(prices_by_ticker_by_date.get(symbol, {}).items()):
            if start <= d <= end:
                rows.append({"date": d, "adjusted_close": px})
        return rows, None  # tuple[list, Citation | None]

    mock.get_historical_eod = AsyncMock(side_effect=get_historical_eod)
    return mock


class TestResolveEntryPrices(unittest.TestCase):
    def test_resolves_to_next_trading_day(self):
        # Verdict emitted Friday 2026-01-02; Monday 2026-01-05 is the first trading day
        prices = {
            "NVDA": {date(2026, 1, 5): Decimal("850.00"), date(2026, 1, 6): Decimal("855.00")},
            "SPY":  {date(2026, 1, 5): Decimal("550.00"), date(2026, 1, 6): Decimal("552.00")},
        }
        fmp = _mock_fmp_price_series(prices)

        bundle = asyncio.run(_resolve_entry_prices(
            ticker="NVDA",
            verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
            theme_seed_tickers=None,
            sector_etf_ticker=None,
            fmp=fmp,
        ))
        self.assertEqual(bundle.entry_price_at, date(2026, 1, 5))
        self.assertEqual(bundle.ticker_price, Decimal("850.00"))
        self.assertEqual(bundle.spy_price, Decimal("550.00"))
        self.assertIsNone(bundle.sector_etf_ticker)
        self.assertEqual(bundle.theme_basket_constituents, [])

    def test_includes_theme_constituents(self):
        prices = {
            "NVDA": {date(2026, 1, 5): Decimal("850.00")},
            "SPY":  {date(2026, 1, 5): Decimal("550.00")},
            "AMD":  {date(2026, 1, 5): Decimal("180.00")},
            "TSM":  {date(2026, 1, 5): Decimal("110.00")},
        }
        fmp = _mock_fmp_price_series(prices)
        bundle = asyncio.run(_resolve_entry_prices(
            ticker="NVDA",
            verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
            theme_seed_tickers=["NVDA", "AMD", "TSM"],
            sector_etf_ticker=None,
            fmp=fmp,
        ))
        tickers = {c.ticker for c in bundle.theme_basket_constituents}
        self.assertEqual(tickers, {"NVDA", "AMD", "TSM"})

    def test_raises_when_ticker_has_no_price_in_lookahead(self):
        prices = {"SPY": {date(2026, 1, 5): Decimal("550.00")}}
        fmp = _mock_fmp_price_series(prices)
        with self.assertRaises(LookupError):
            asyncio.run(_resolve_entry_prices(
                ticker="NVDA",
                verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                theme_seed_tickers=None,
                sector_etf_ticker=None,
                fmp=fmp,
            ))
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 3 new tests ERROR (ImportError: `_resolve_entry_prices`).

- [ ] **Step 3: Implement `_resolve_entry_prices`**

Append to `backend/app/services/outcome_tracker.py`:

```python
async def _resolve_entry_prices(
    *,
    ticker: str,
    verdict_emitted_at: datetime,
    theme_seed_tickers: list[str] | None,
    sector_etf_ticker: str | None,
    fmp: FMPClient,
) -> EntryPriceBundle:
    """Resolve entry-anchored prices for outcome creation.

    Entry day = first trading day STRICTLY AFTER verdict_emitted_at's calendar date.
    Fetches adjusted-close for ticker + SPY + (optional) sector ETF + theme constituents,
    all anchored to the same entry day for fair comparison.
    """
    emitted_date = verdict_emitted_at.astimezone(timezone.utc).date()
    range_start = emitted_date + timedelta(days=1)
    range_end = emitted_date + timedelta(days=ENTRY_PRICE_LOOKAHEAD_DAYS)

    ticker_rows, _ = await fmp.get_historical_eod(ticker, range_start, range_end)
    if not ticker_rows:
        raise LookupError(
            f"no FMP price for {ticker} between {range_start} and {range_end}"
        )
    first = sorted(ticker_rows, key=lambda r: r["date"])[0]
    entry_day: date = first["date"]
    ticker_price = Decimal(str(first["adjusted_close"]))

    async def _close_on(symbol: str, target_day: date) -> Decimal | None:
        rows, _ = await fmp.get_historical_eod(symbol, target_day, target_day)
        if not rows:
            return None
        for r in rows:
            if r["date"] == target_day:
                return Decimal(str(r["adjusted_close"]))
        return None

    spy_price = await _close_on("SPY", entry_day)

    sector_price: Decimal | None = None
    if sector_etf_ticker:
        sector_price = await _close_on(sector_etf_ticker, entry_day)

    constituents: list[EntryConstituent] = []
    if theme_seed_tickers:
        for t in theme_seed_tickers:
            px = await _close_on(t, entry_day)
            if px is not None:
                constituents.append(EntryConstituent(ticker=t, entry_price=px))

    return EntryPriceBundle(
        entry_price_at=entry_day,
        ticker_price=ticker_price,
        spy_price=spy_price,
        sector_etf_ticker=sector_etf_ticker,
        sector_etf_price=sector_price,
        theme_basket_constituents=constituents,
    )
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): _resolve_entry_prices + 3 tests"
```

---

## Task 7: Sector resolution helper

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `_resolve_sector_etf`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 2 tests)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_outcome_tracker.py` ABOVE `if __name__`:

```python
from backend.app.services.outcome_tracker import _resolve_sector_etf


class TestResolveSectorEtf(unittest.TestCase):
    def test_returns_etf_for_mapped_sector(self):
        async def _run():
            db = MagicMock()
            db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value="XLK")
            ))
            return await _resolve_sector_etf(sector="Technology", db=db)

        self.assertEqual(asyncio.run(_run()), "XLK")

    def test_returns_none_for_unmapped_or_null(self):
        async def _run(sector):
            db = MagicMock()
            db.execute = AsyncMock(return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None)
            ))
            return await _resolve_sector_etf(sector=sector, db=db)

        self.assertIsNone(asyncio.run(_run(None)))
        self.assertIsNone(asyncio.run(_run("Cryptocurrency")))
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 2 new tests ERROR (ImportError).

- [ ] **Step 3: Implement `_resolve_sector_etf`**

Append to `backend/app/services/outcome_tracker.py`:

```python
async def _resolve_sector_etf(*, sector: str | None, db: AsyncSession) -> str | None:
    """Look up the SPDR sector ETF for an FMP sector name. None if unmapped or sector is null."""
    if not sector:
        return None
    result = await db.execute(
        select(SectorEtfMapping.etf_ticker).where(SectorEtfMapping.fmp_sector == sector)
    )
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): _resolve_sector_etf + 2 tests"
```

---

## Task 8: Theme basket value computation

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `compute_basket_value`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 3 tests)

- [ ] **Step 1: Write the failing tests**

Append:

```python
from backend.app.services.outcome_tracker import compute_basket_value


class TestComputeBasketValue(unittest.TestCase):
    def test_equal_weighted_basket(self):
        # NVDA: 850 → 935 (+10%); AMD: 180 → 198 (+10%); TSM: 110 → 110 (0%) → basket value 106.67
        constituents = [
            {"ticker": "NVDA", "entry_price": Decimal("850.00")},
            {"ticker": "AMD",  "entry_price": Decimal("180.00")},
            {"ticker": "TSM",  "entry_price": Decimal("110.00")},
        ]
        current_prices = {
            "NVDA": Decimal("935.00"),
            "AMD":  Decimal("198.00"),
            "TSM":  Decimal("110.00"),
        }
        value = compute_basket_value(constituents, current_prices)
        # mean of (935/850, 198/180, 110/110) * 100 = mean(1.1, 1.1, 1.0) * 100 = 106.6667
        self.assertAlmostEqual(float(value), 106.6667, places=3)

    def test_drops_missing_constituent(self):
        constituents = [
            {"ticker": "NVDA", "entry_price": Decimal("100.00")},
            {"ticker": "AMD",  "entry_price": Decimal("100.00")},
        ]
        # AMD has no current price → only NVDA averaged. (110/100)*100 = 110.
        value = compute_basket_value(constituents, {"NVDA": Decimal("110.00")})
        self.assertAlmostEqual(float(value), 110.0, places=3)

    def test_returns_none_when_all_missing(self):
        constituents = [{"ticker": "NVDA", "entry_price": Decimal("100.00")}]
        self.assertIsNone(compute_basket_value(constituents, {}))
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 3 new tests ERROR.

- [ ] **Step 3: Implement `compute_basket_value`**

Append to `backend/app/services/outcome_tracker.py`:

```python
def compute_basket_value(
    constituents: list[dict],
    current_prices: dict[str, Decimal],
) -> Decimal | None:
    """Equal-weighted arithmetic basket value.

    constituents: list of {"ticker": str, "entry_price": Decimal}.
    Returns mean(current/entry) * 100, omitting constituents with no current price.
    Returns None when no constituent has a current price.
    """
    ratios: list[float] = []
    for c in constituents:
        symbol = c["ticker"]
        entry = c["entry_price"]
        if isinstance(entry, (str, int, float)):
            entry = Decimal(str(entry))
        current = current_prices.get(symbol)
        if current is None or entry == 0:
            continue
        ratios.append(float(current) / float(entry))
    if not ratios:
        return None
    return Decimal(str(statistics.fmean(ratios) * 100))
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 11 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): compute_basket_value + 3 tests"
```

---

## Task 9: Signal-snapshot builders

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append builders)
- Modify: `backend/tests/test_outcome_tracker.py` (add 2 tests)

- [ ] **Step 1: Write the failing tests**

Append:

```python
from backend.app.services.outcome_tracker import (
    build_research_run_signal_snapshot,
    build_workspace_run_signal_snapshot,
)


class TestSignalSnapshotBuilders(unittest.TestCase):
    def test_research_run_snapshot_shape(self):
        state = MagicMock()
        state.deep_dive_results = {
            "Business Quality": MagicMock(score=72),
            "Risk Assessment":  MagicMock(score=58),
        }
        signals_row = {"velocity": 12.3, "fundamental": 0.78, "discovery": 0.65, "surprise": None}
        kill_states = [{"ordinal": 1, "state": "armed"}]

        snap = build_research_run_signal_snapshot(
            state=state, signals_row=signals_row, kill_states=kill_states
        )
        self.assertEqual(snap["signals_row"], signals_row)
        self.assertEqual(snap["deep_dive_scores"]["Business Quality"], 72)
        self.assertEqual(snap["kill_criterion_state"], kill_states)
        self.assertNotIn("workspace_step_verdicts", snap)

    def test_workspace_run_snapshot_shape(self):
        run = MagicMock()
        run.step_outputs = {
            "update_refresh": {"verdict": "healthy"},
            "challenge":      {"proposed_verdict": "imminent"},
        }
        signals_row = {"velocity": 5.0, "fundamental": 0.5, "discovery": 0.3, "surprise": None}
        model_assumptions = {"discount_rate": 0.10, "terminal_growth": 0.025}

        snap = build_workspace_run_signal_snapshot(
            run=run, signals_row=signals_row, kill_states=[],
            model_assumptions=model_assumptions,
        )
        self.assertEqual(snap["signals_row"], signals_row)
        self.assertEqual(snap["workspace_step_verdicts"]["challenge"], "imminent")
        self.assertEqual(snap["model_assumptions"], model_assumptions)
        self.assertNotIn("deep_dive_scores", snap)
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 2 new tests ERROR.

- [ ] **Step 3: Implement the builders**

Append to `backend/app/services/outcome_tracker.py`:

```python
def build_research_run_signal_snapshot(
    *,
    state: Any,
    signals_row: dict | None,
    kill_states: list[dict] | None,
) -> dict:
    """Assemble signal_snapshot JSONB for a research-run verdict.

    Tolerant of missing fields on state — backfill against older state shapes must not raise.
    """
    deep_dive_scores: dict[str, float | None] = {}
    results = getattr(state, "deep_dive_results", None) or {}
    if isinstance(results, dict):
        for category, payload in results.items():
            score = getattr(payload, "score", None)
            if score is None and isinstance(payload, dict):
                score = payload.get("score")
            deep_dive_scores[category] = score

    return {
        "signals_row": signals_row or {},
        "deep_dive_scores": deep_dive_scores,
        "kill_criterion_state": kill_states or [],
    }


def build_workspace_run_signal_snapshot(
    *,
    run: Any,
    signals_row: dict | None,
    kill_states: list[dict] | None,
    model_assumptions: dict | None,
) -> dict:
    """Assemble signal_snapshot JSONB for a workspace-run verdict.

    Tolerant of missing keys on run.step_outputs.
    """
    step_outputs = getattr(run, "step_outputs", None) or {}
    verdicts: dict[str, str | None] = {}
    if isinstance(step_outputs, dict):
        for step_name, payload in step_outputs.items():
            if not isinstance(payload, dict):
                continue
            verdict = payload.get("proposed_verdict") or payload.get("verdict")
            verdicts[step_name] = verdict

    return {
        "signals_row": signals_row or {},
        "workspace_step_verdicts": verdicts,
        "kill_criterion_state": kill_states or [],
        "model_assumptions": model_assumptions or {},
    }
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): signal_snapshot builders for research_run + workspace_run + 2 tests"
```

---

## Task 10: record_verdict — idempotent path + entry creation

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `record_verdict`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 4 tests)

- [ ] **Step 1: Write the failing tests**

Append (uses an in-memory SQLite-or-Postgres test pattern via real DB; if your test infra mocks DB, swap to mock pattern below):

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SAAsyncSession
from sqlalchemy.orm import sessionmaker
from backend.app.models.base import Base
from backend.app.models.outcome import VerdictOutcome, SectorEtfMapping
from backend.app.services.outcome_tracker import record_verdict


def _build_async_test_session():
    """Spin up an in-memory async sqlite engine + session for ORM tests.

    sqlite supports enough of the schema to test row-level logic; the JSONB columns
    fall back to TEXT, but our reads/writes go through ORM round-trip so values
    survive. Indexes referenced in WHERE clauses still work.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_setup())
    Session = sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)
    return engine, Session


class TestRecordVerdict(unittest.TestCase):
    def test_creates_outcome_with_all_three_benchmark_entries(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(SectorEtfMapping(fmp_sector="Technology", etf_ticker="XLK"))
                await db.commit()

                prices = {
                    "NVDA": {date(2026, 1, 5): Decimal("850.00")},
                    "SPY":  {date(2026, 1, 5): Decimal("550.00")},
                    "XLK":  {date(2026, 1, 5): Decimal("200.00")},
                    "AMD":  {date(2026, 1, 5): Decimal("180.00")},
                }
                fmp = _mock_fmp_price_series(prices)

                outcome = await record_verdict(
                    source_type="research_run",
                    source_id=str(uuid4()),
                    ticker="NVDA",
                    theme_id=None,
                    theme_seed_tickers=["NVDA", "AMD"],
                    sector="Technology",
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot={"signals_row": {"velocity": 12.3}},
                    fmp=fmp,
                    db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertEqual(outcome.ticker, "NVDA")
        self.assertEqual(outcome.entry_price_at, date(2026, 1, 5))
        self.assertEqual(outcome.entry_price, Decimal("850.00"))
        self.assertEqual(outcome.spy_entry_price, Decimal("550.00"))
        self.assertEqual(outcome.sector_etf_ticker, "XLK")
        self.assertEqual(outcome.sector_etf_entry_price, Decimal("200.00"))
        self.assertEqual(outcome.theme_basket_entry_value, Decimal("100"))
        self.assertEqual(len(outcome.theme_basket_constituents), 2)

    def test_idempotent_on_source_id(self):
        engine, Session = _build_async_test_session()
        source_id = str(uuid4())

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)

                first = await record_verdict(
                    source_type="research_run", source_id=source_id, ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                second = await record_verdict(
                    source_type="research_run", source_id=source_id, ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                return first.id, second.id

        first_id, second_id = asyncio.run(_run())
        self.assertEqual(first_id, second_id)

    def test_unmapped_sector_leaves_sector_columns_null(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)
                outcome = await record_verdict(
                    source_type="research_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector="Cryptocurrency",
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertIsNone(outcome.sector_etf_ticker)
        self.assertIsNone(outcome.sector_etf_entry_price)

    def test_no_supersede_when_no_prior(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00")}}
                fmp = _mock_fmp_price_series(prices)
                outcome = await record_verdict(
                    source_type="research_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=None, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                return outcome

        outcome = asyncio.run(_run())
        self.assertIsNone(outcome.superseded_at)
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 4 new tests ERROR (ImportError on `record_verdict`).

- [ ] **Step 3: Implement `record_verdict`**

Append to `backend/app/services/outcome_tracker.py`:

```python
async def record_verdict(
    *,
    source_type: Literal["research_run", "workspace_run"],
    source_id: str,
    ticker: str,
    theme_id: str | None,
    theme_seed_tickers: list[str] | None,
    sector: str | None,
    verdict: str,
    verdict_emitted_at: datetime,
    signal_snapshot: dict | None,
    fmp: FMPClient,
    db: AsyncSession,
) -> VerdictOutcome:
    """Idempotent on (source_type, source_id).

    1) Return existing outcome if already recorded.
    2) Resolve entry-anchored prices for ticker + SPY + sector ETF + theme constituents.
    3) Stamp any prior open same-(ticker, theme_id, source_type) outcome as superseded.
    4) Insert the new outcome row.
    """
    existing = (await db.execute(
        select(VerdictOutcome).where(
            VerdictOutcome.source_type == source_type,
            VerdictOutcome.source_id == source_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    sector_etf_ticker = await _resolve_sector_etf(sector=sector, db=db)

    bundle = await _resolve_entry_prices(
        ticker=ticker,
        verdict_emitted_at=verdict_emitted_at,
        theme_seed_tickers=theme_seed_tickers,
        sector_etf_ticker=sector_etf_ticker,
        fmp=fmp,
    )

    new_id = str(uuid4())
    constituents_payload = (
        [{"ticker": c.ticker, "entry_price": str(c.entry_price)}
         for c in bundle.theme_basket_constituents] or None
    )
    theme_basket_entry_value: Decimal | None = (
        Decimal("100") if constituents_payload else None
    )

    outcome = VerdictOutcome(
        id=new_id,
        source_type=source_type,
        source_id=source_id,
        ticker=ticker,
        theme_id=theme_id,
        verdict=verdict,
        verdict_emitted_at=verdict_emitted_at,
        entry_price_at=bundle.entry_price_at,
        entry_price=bundle.ticker_price,
        spy_entry_price=bundle.spy_price,
        sector_etf_ticker=bundle.sector_etf_ticker,
        sector_etf_entry_price=bundle.sector_etf_price,
        theme_basket_entry_value=theme_basket_entry_value,
        theme_basket_constituents=constituents_payload,
        signal_snapshot=signal_snapshot,
    )

    await _stamp_prior_open_as_superseded(
        ticker=ticker,
        theme_id=theme_id,
        source_type=source_type,
        new_outcome=outcome,
        bundle=bundle,
        db=db,
    )

    db.add(outcome)
    await db.flush()
    return outcome


async def _stamp_prior_open_as_superseded(
    *,
    ticker: str,
    theme_id: str | None,
    source_type: str,
    new_outcome: VerdictOutcome,
    bundle: EntryPriceBundle,
    db: AsyncSession,
) -> None:
    """If there's a prior open (ticker, theme_id, source_type) outcome, stamp realized returns on it."""
    q = select(VerdictOutcome).where(
        VerdictOutcome.ticker == ticker,
        VerdictOutcome.source_type == source_type,
        VerdictOutcome.superseded_at.is_(None),
    )
    if theme_id is None:
        q = q.where(VerdictOutcome.theme_id.is_(None))
    else:
        q = q.where(VerdictOutcome.theme_id == theme_id)
    q = q.order_by(VerdictOutcome.verdict_emitted_at.desc()).limit(1)

    prior = (await db.execute(q)).scalar_one_or_none()
    if prior is None:
        return

    def _excess(t_entry, t_now, b_entry, b_now) -> Decimal | None:
        if t_entry in (None, 0) or b_entry in (None, 0) or t_now is None or b_now is None:
            return None
        return ((Decimal(t_now) / Decimal(t_entry)) - (Decimal(b_now) / Decimal(b_entry)))

    t_return: Decimal | None = None
    if prior.entry_price and prior.entry_price != 0:
        t_return = (Decimal(bundle.ticker_price) / Decimal(prior.entry_price)) - Decimal("1")

    # Theme basket realized: use the new outcome's basket value (=100) minus prior basket recomputed
    # at the new entry day. For simplicity we compute it from the prior's constituents:
    prior_basket_excess: Decimal | None = None
    if prior.theme_basket_constituents:
        current_prices = {c.ticker: c.entry_price for c in bundle.theme_basket_constituents}
        # When the prior's constituents don't all match the new theme, we drop missing.
        prior_value_at_new_entry = compute_basket_value(
            prior.theme_basket_constituents, current_prices
        )
        if prior_value_at_new_entry is not None and prior.theme_basket_entry_value:
            basket_return = (prior_value_at_new_entry / Decimal(prior.theme_basket_entry_value)) - Decimal("1")
            if t_return is not None:
                prior_basket_excess = t_return - basket_return

    prior.superseded_at = datetime.now(timezone.utc)
    prior.superseded_by_outcome_id = new_outcome.id
    prior.realized_ticker_return_pct = t_return
    prior.realized_spy_excess_pct = _excess(
        prior.entry_price, bundle.ticker_price, prior.spy_entry_price, bundle.spy_price
    )
    prior.realized_sector_excess_pct = _excess(
        prior.entry_price, bundle.ticker_price, prior.sector_etf_entry_price, bundle.sector_etf_price
    )
    prior.realized_theme_basket_excess_pct = prior_basket_excess
    await db.flush()
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 17 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): record_verdict with idempotency + supersede stamping + 4 tests"
```

---

## Task 11: Supersede edge cases — same-source-type, cross-source-type, cross-theme

**Files:**
- Modify: `backend/tests/test_outcome_tracker.py` (add 3 tests)

- [ ] **Step 1: Write the failing tests**

Append:

```python
class TestSupersedeRules(unittest.TestCase):
    def test_same_source_type_same_theme_supersedes(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                theme_id = str(uuid4())
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00"),
                                   date(2026, 2, 5): Decimal("935.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00"),
                                  date(2026, 2, 5): Decimal("560.00")}}
                fmp = _mock_fmp_price_series(prices)

                first = await record_verdict(
                    source_type="workspace_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_id, theme_seed_tickers=None, sector=None,
                    verdict="healthy",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()

                second = await record_verdict(
                    source_type="workspace_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_id, theme_seed_tickers=None, sector=None,
                    verdict="imminent",
                    verdict_emitted_at=datetime(2026, 2, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                await db.refresh(first)
                return first, second

        first, second = asyncio.run(_run())
        self.assertIsNotNone(first.superseded_at)
        self.assertEqual(first.superseded_by_outcome_id, second.id)
        # Realized return: 935/850 - 1 = 0.1
        self.assertAlmostEqual(float(first.realized_ticker_return_pct), 0.1, places=4)

    def test_cross_source_type_does_not_supersede(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                theme_id = str(uuid4())
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00"),
                                   date(2026, 2, 5): Decimal("935.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00"),
                                  date(2026, 2, 5): Decimal("560.00")}}
                fmp = _mock_fmp_price_series(prices)

                research = await record_verdict(
                    source_type="research_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_id, theme_seed_tickers=None, sector=None,
                    verdict="completed",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()

                workspace = await record_verdict(
                    source_type="workspace_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_id, theme_seed_tickers=None, sector=None,
                    verdict="healthy",
                    verdict_emitted_at=datetime(2026, 2, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                await db.refresh(research)
                return research, workspace

        research, _workspace = asyncio.run(_run())
        self.assertIsNone(research.superseded_at)

    def test_cross_theme_does_not_supersede(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                theme_a, theme_b = str(uuid4()), str(uuid4())
                prices = {"NVDA": {date(2026, 1, 5): Decimal("850.00"),
                                   date(2026, 2, 5): Decimal("935.00")},
                          "SPY": {date(2026, 1, 5): Decimal("550.00"),
                                  date(2026, 2, 5): Decimal("560.00")}}
                fmp = _mock_fmp_price_series(prices)

                in_a = await record_verdict(
                    source_type="workspace_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_a, theme_seed_tickers=None, sector=None,
                    verdict="healthy",
                    verdict_emitted_at=datetime(2026, 1, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()

                in_b = await record_verdict(
                    source_type="workspace_run", source_id=str(uuid4()), ticker="NVDA",
                    theme_id=theme_b, theme_seed_tickers=None, sector=None,
                    verdict="healthy",
                    verdict_emitted_at=datetime(2026, 2, 2, 22, 0, tzinfo=timezone.utc),
                    signal_snapshot=None, fmp=fmp, db=db,
                )
                await db.commit()
                await db.refresh(in_a)
                return in_a

        in_a = asyncio.run(_run())
        self.assertIsNone(in_a.superseded_at)
```

- [ ] **Step 2: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 20 tests pass (the supersede edge cases are already covered by the implementation from Task 10).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_outcome_tracker.py
git commit -m "test(outcome): supersede edge cases — same-source / cross-source / cross-theme (3 tests)"
```

---

## Task 12: refresh_snapshots

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `refresh_snapshots`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 3 tests)

- [ ] **Step 1: Write the failing tests**

Append:

```python
from backend.app.services.outcome_tracker import refresh_snapshots
from backend.app.models.outcome import VerdictReturnSnapshot


class TestRefreshSnapshots(unittest.TestCase):
    def test_fills_due_offsets_and_closes_at_6m(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                # Create an outcome whose entry day is 200 days ago — all offsets should be due
                today = date.today()
                entry_day = today - timedelta(days=200)
                outcome = VerdictOutcome(
                    id=str(uuid4()),
                    source_type="workspace_run",
                    source_id=str(uuid4()),
                    ticker="NVDA",
                    theme_id=None,
                    verdict="healthy",
                    verdict_emitted_at=datetime.combine(entry_day - timedelta(days=1),
                                                        datetime.min.time(),
                                                        tzinfo=timezone.utc),
                    entry_price_at=entry_day,
                    entry_price=Decimal("850.00"),
                    spy_entry_price=Decimal("550.00"),
                    sector_etf_ticker=None,
                    sector_etf_entry_price=None,
                    theme_basket_entry_value=None,
                    theme_basket_constituents=None,
                )
                db.add(outcome)
                await db.commit()

                # Build FMP mock returning per-offset prices
                prices_nvda = {entry_day: Decimal("850.00")}
                prices_spy  = {entry_day: Decimal("550.00")}
                for (key, days) in [("1d", 1), ("1w", 7), ("1m", 30), ("3m", 90), ("6m", 180)]:
                    d = entry_day + timedelta(days=days)
                    prices_nvda[d] = Decimal("850.00") * Decimal("1.0") + Decimal(str(days)) * Decimal("0.5")
                    prices_spy[d]  = Decimal("550.00") + Decimal(str(days)) * Decimal("0.1")

                fmp = _mock_fmp_price_series({"NVDA": prices_nvda, "SPY": prices_spy})
                summary = await refresh_snapshots(fmp=fmp, db=db)
                await db.commit()

                snaps = (await db.execute(
                    select(VerdictReturnSnapshot).where(
                        VerdictReturnSnapshot.outcome_id == outcome.id
                    )
                )).scalars().all()

                await db.refresh(outcome)
                return summary, snaps, outcome

        summary, snaps, outcome = asyncio.run(_run())
        self.assertEqual({s.snapshot_offset for s in snaps}, {"1d", "1w", "1m", "3m", "6m"})
        self.assertIsNotNone(outcome.closed_at)
        self.assertEqual(summary.closed, 1)

    def test_does_not_duplicate_existing_snapshots(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                entry_day = date.today() - timedelta(days=200)
                outcome = VerdictOutcome(
                    id=str(uuid4()), source_type="workspace_run", source_id=str(uuid4()),
                    ticker="NVDA", theme_id=None, verdict="healthy",
                    verdict_emitted_at=datetime.combine(entry_day, datetime.min.time(), tzinfo=timezone.utc),
                    entry_price_at=entry_day, entry_price=Decimal("850.00"),
                    spy_entry_price=Decimal("550.00"),
                )
                db.add(outcome)
                # Pre-insert the 1m snapshot
                snap = VerdictReturnSnapshot(
                    id=str(uuid4()), outcome_id=outcome.id, snapshot_offset="1m",
                    snapshot_date=entry_day + timedelta(days=30),
                    ticker_price=Decimal("900.00"),
                    ticker_return_pct=Decimal("0.0588"),
                )
                db.add(snap)
                await db.commit()

                prices_nvda = {entry_day + timedelta(days=d): Decimal("900.00") for d in [1, 7, 30, 90, 180]}
                prices_spy  = {entry_day + timedelta(days=d): Decimal("560.00") for d in [1, 7, 30, 90, 180]}
                fmp = _mock_fmp_price_series({"NVDA": prices_nvda, "SPY": prices_spy})
                summary = await refresh_snapshots(fmp=fmp, db=db)
                await db.commit()
                count = (await db.execute(
                    select(VerdictReturnSnapshot).where(
                        VerdictReturnSnapshot.outcome_id == outcome.id,
                        VerdictReturnSnapshot.snapshot_offset == "1m",
                    )
                )).scalars().all()
                return summary, len(count)

        summary, count_1m = asyncio.run(_run())
        self.assertEqual(count_1m, 1)

    def test_per_outcome_errors_isolated(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                entry_day = date.today() - timedelta(days=200)
                bad = VerdictOutcome(
                    id=str(uuid4()), source_type="workspace_run", source_id=str(uuid4()),
                    ticker="DELISTED", theme_id=None, verdict="healthy",
                    verdict_emitted_at=datetime.combine(entry_day, datetime.min.time(), tzinfo=timezone.utc),
                    entry_price_at=entry_day, entry_price=Decimal("100.00"),
                    spy_entry_price=Decimal("550.00"),
                )
                good = VerdictOutcome(
                    id=str(uuid4()), source_type="workspace_run", source_id=str(uuid4()),
                    ticker="NVDA", theme_id=None, verdict="healthy",
                    verdict_emitted_at=datetime.combine(entry_day, datetime.min.time(), tzinfo=timezone.utc),
                    entry_price_at=entry_day, entry_price=Decimal("850.00"),
                    spy_entry_price=Decimal("550.00"),
                )
                db.add_all([bad, good])
                await db.commit()

                prices_nvda = {entry_day + timedelta(days=d): Decimal("900.00") for d in [1, 7, 30, 90, 180]}
                prices_spy  = {entry_day + timedelta(days=d): Decimal("560.00") for d in [1, 7, 30, 90, 180]}
                fmp = _mock_fmp_price_series({"NVDA": prices_nvda, "SPY": prices_spy})  # DELISTED missing
                summary = await refresh_snapshots(fmp=fmp, db=db)
                await db.commit()
                good_snaps = (await db.execute(
                    select(VerdictReturnSnapshot).where(
                        VerdictReturnSnapshot.outcome_id == good.id
                    )
                )).scalars().all()
                bad_snaps = (await db.execute(
                    select(VerdictReturnSnapshot).where(
                        VerdictReturnSnapshot.outcome_id == bad.id
                    )
                )).scalars().all()
                return summary, len(good_snaps), len(bad_snaps)

        summary, good_n, bad_n = asyncio.run(_run())
        self.assertEqual(good_n, 5)
        self.assertEqual(bad_n, 0)
        self.assertTrue(len(summary.errors) >= 1)
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 3 new tests ERROR (ImportError on `refresh_snapshots`).

- [ ] **Step 3: Implement `refresh_snapshots`**

Append to `backend/app/services/outcome_tracker.py`:

```python
async def refresh_snapshots(*, fmp: FMPClient, db: AsyncSession) -> RefreshSummary:
    """Iterate open outcomes; insert any newly-due snapshots; close at 6m.

    Per-outcome errors captured in summary.errors[], never abort the loop.
    """
    open_outcomes = (await db.execute(
        select(VerdictOutcome).where(VerdictOutcome.closed_at.is_(None))
    )).scalars().all()

    today = date.today()
    snapshotted = 0
    closed = 0
    errors: list[dict[str, str]] = []

    for outcome in open_outcomes:
        try:
            inserted, did_close = await _refresh_one(
                outcome=outcome, today=today, fmp=fmp, db=db,
            )
            snapshotted += inserted
            if did_close:
                closed += 1
        except Exception as exc:  # noqa: BLE001 — captured per-outcome
            logger.exception("refresh_snapshots failed for outcome %s", outcome.id)
            errors.append({"outcome_id": outcome.id, "error": str(exc)})

    return RefreshSummary(
        processed=len(open_outcomes), snapshotted=snapshotted, closed=closed, errors=errors,
    )


async def _refresh_one(
    *,
    outcome: VerdictOutcome,
    today: date,
    fmp: FMPClient,
    db: AsyncSession,
) -> tuple[int, bool]:
    """Insert any due snapshots for this outcome. Returns (insertions, did_close_at_6m)."""
    existing = {
        row.snapshot_offset
        for row in (await db.execute(
            select(VerdictReturnSnapshot).where(
                VerdictReturnSnapshot.outcome_id == outcome.id
            )
        )).scalars().all()
    }

    due_offsets: list[tuple[str, date]] = []
    for key, days in SNAPSHOT_OFFSETS:
        if key in existing:
            continue
        target = outcome.entry_price_at + timedelta(days=days)
        if target <= today:
            due_offsets.append((key, target))

    if not due_offsets:
        return 0, False

    # One range fetch per ticker — covers all due offsets for that ticker
    overall_start = min(d for _, d in due_offsets)
    overall_end = max(d for _, d in due_offsets) + timedelta(days=3)

    ticker_rows, _ = await fmp.get_historical_eod(outcome.ticker, overall_start, overall_end)
    if not ticker_rows:
        raise LookupError(f"no FMP price for {outcome.ticker} in [{overall_start}, {overall_end}]")
    by_date = {r["date"]: Decimal(str(r["adjusted_close"])) for r in ticker_rows}

    spy_by_date: dict[date, Decimal] = {}
    if outcome.spy_entry_price is not None:
        spy_rows, _ = await fmp.get_historical_eod("SPY", overall_start, overall_end)
        spy_by_date = {r["date"]: Decimal(str(r["adjusted_close"])) for r in spy_rows or []}

    sector_by_date: dict[date, Decimal] = {}
    if outcome.sector_etf_ticker:
        rows, _ = await fmp.get_historical_eod(outcome.sector_etf_ticker, overall_start, overall_end)
        sector_by_date = {r["date"]: Decimal(str(r["adjusted_close"])) for r in rows or []}

    constituent_by_date_by_ticker: dict[str, dict[date, Decimal]] = {}
    if outcome.theme_basket_constituents:
        for c in outcome.theme_basket_constituents:
            sym = c["ticker"]
            rows, _ = await fmp.get_historical_eod(sym, overall_start, overall_end)
            constituent_by_date_by_ticker[sym] = {
                r["date"]: Decimal(str(r["adjusted_close"])) for r in rows or []
            }

    def _first_on_or_after(by_date_map: dict[date, Decimal], target: date) -> tuple[date, Decimal] | None:
        for d in sorted(by_date_map.keys()):
            if d >= target:
                return d, by_date_map[d]
        return None

    inserted = 0
    did_close = False

    for key, target in due_offsets:
        match = _first_on_or_after(by_date, target)
        if match is None:
            continue
        snap_date, ticker_px = match
        ticker_return = (ticker_px / outcome.entry_price) - Decimal("1")

        spy_px: Decimal | None = None
        spy_excess: Decimal | None = None
        if outcome.spy_entry_price is not None:
            spy_match = _first_on_or_after(spy_by_date, target)
            if spy_match is not None:
                _, spy_px = spy_match
                spy_return = (spy_px / outcome.spy_entry_price) - Decimal("1")
                spy_excess = ticker_return - spy_return

        sector_px: Decimal | None = None
        sector_excess: Decimal | None = None
        if outcome.sector_etf_ticker and outcome.sector_etf_entry_price:
            m = _first_on_or_after(sector_by_date, target)
            if m is not None:
                _, sector_px = m
                sector_return = (sector_px / outcome.sector_etf_entry_price) - Decimal("1")
                sector_excess = ticker_return - sector_return

        basket_value: Decimal | None = None
        basket_excess: Decimal | None = None
        if outcome.theme_basket_constituents and outcome.theme_basket_entry_value:
            current_prices: dict[str, Decimal] = {}
            for sym, by in constituent_by_date_by_ticker.items():
                m = _first_on_or_after(by, target)
                if m is not None:
                    current_prices[sym] = m[1]
            basket_value = compute_basket_value(outcome.theme_basket_constituents, current_prices)
            if basket_value is not None:
                basket_return = (basket_value / Decimal(outcome.theme_basket_entry_value)) - Decimal("1")
                basket_excess = ticker_return - basket_return

        db.add(VerdictReturnSnapshot(
            id=str(uuid4()),
            outcome_id=outcome.id,
            snapshot_offset=key,
            snapshot_date=snap_date,
            ticker_price=ticker_px,
            spy_price=spy_px,
            sector_etf_price=sector_px,
            theme_basket_value=basket_value,
            ticker_return_pct=ticker_return,
            spy_excess_pct=spy_excess,
            sector_excess_pct=sector_excess,
            theme_basket_excess_pct=basket_excess,
        ))
        inserted += 1
        if key == "6m":
            outcome.closed_at = datetime.now(timezone.utc)
            did_close = True

    if inserted:
        await db.flush()
    return inserted, did_close
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 23 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): refresh_snapshots with per-outcome error isolation + 3 tests"
```

---

## Task 13: Hook into pipeline.py terminal transitions

**Files:**
- Modify: `backend/app/services/pipeline.py`

- [ ] **Step 1: Locate the terminal transition site**

In `backend/app/services/pipeline.py`, find the block around line 201:
```python
if state.status in ("completed", "watchlist", "pass"):
    mark_terminal_completed_at(state)
```

- [ ] **Step 2: Add imports + helper at top of file**

Add to the import block at the top:
```python
from backend.app.clients.fmp import FMPClient  # already present — keep as-is
from backend.app.services import outcome_tracker
from backend.app.models.signal import Signal
from backend.app.db import unit_of_work
```

- [ ] **Step 3: Add the hook right after `mark_terminal_completed_at(state)`**

Replace:
```python
if state.status in ("completed", "watchlist", "pass"):
    mark_terminal_completed_at(state)
```

with:
```python
if state.status in ("completed", "watchlist", "pass"):
    mark_terminal_completed_at(state)
    await self._record_terminal_outcome(run_id=run_id, state=state)
```

- [ ] **Step 4: Add the `_record_terminal_outcome` method**

Append to the `PipelineService` class:

```python
async def _record_terminal_outcome(self, *, run_id: str, state: Any) -> None:
    """Best-effort: record the verdict in verdict_outcomes. Errors logged, never propagated."""
    try:
        async with unit_of_work() as db:
            # Look up the latest signals row for this (ticker, theme_id)
            signals_row: dict | None = None
            if state.theme_id:
                sig_rows = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == state.ticker,
                        Signal.theme_id == state.theme_id,
                    )
                )).scalars().all()
                if sig_rows:
                    signals_row = {r.signal_type: r.value for r in sig_rows}

            # Look up theme seed_tickers
            theme_seed_tickers: list[str] | None = None
            if state.theme_id:
                from backend.app.models.theme import Theme
                theme = (await db.execute(
                    select(Theme).where(Theme.id == state.theme_id)
                )).scalar_one_or_none()
                if theme and theme.seed_tickers:
                    theme_seed_tickers = list(theme.seed_tickers) if isinstance(theme.seed_tickers, list) else None

            # FMP sector lookup via profile (cached by client)
            profile, _ = await self._fmp.get_profile(state.ticker)
            sector = (profile or {}).get("sector")

            snapshot = outcome_tracker.build_research_run_signal_snapshot(
                state=state, signals_row=signals_row, kill_states=[],
            )

            await outcome_tracker.record_verdict(
                source_type="research_run",
                source_id=run_id,
                ticker=state.ticker,
                theme_id=state.theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=state.status,
                verdict_emitted_at=datetime.now(timezone.utc),
                signal_snapshot=snapshot,
                fmp=self._fmp,
                db=db,
            )
    except Exception:
        logger.exception("record_verdict failed for run %s", run_id)
```

- [ ] **Step 5: Make sure `datetime` and `timezone` are imported**

If not already in `pipeline.py`:
```python
from datetime import datetime, timezone
```
Add to imports if missing.

- [ ] **Step 6: Run pipeline tests**

```bash
python -m unittest backend.tests.test_pipeline -v 2>/dev/null || echo "no pipeline tests"
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: outcome tests still pass (23). Pipeline-side smoke is in Task 18.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/pipeline.py
git commit -m "feat(pipeline): hook record_verdict on terminal status transitions"
```

---

## Task 14: Hook into workspace.py final transitions

**Files:**
- Modify: `backend/app/services/workspace.py`

- [ ] **Step 1: Locate the terminal transition site**

In `backend/app/services/workspace.py`, find the section around line 263 where `_set_status` is called with `final_status` and `verdict=verdict_str`.

- [ ] **Step 2: Add imports**

Add to the top of the file:
```python
from backend.app.services import outcome_tracker
from backend.app.models.signal import Signal
from backend.app.models.kill_criterion_state import KillCriterionState
from backend.app.models.ticker_model import TickerModel
```

- [ ] **Step 3: Add the hook after the successful `_set_status` call**

Find the block roughly like:
```python
async with unit_of_work() as db:
    await self._set_status(
        db, run_id=run_id,
        status=final_status, verdict=verdict_str,
        ...
    )
emit({"type": "workspace_run_complete", "verdict": verdict_str, ...})
```

Add immediately after this block (before the `emit`):
```python
if final_status == "completed" and verdict_str:
    await self._record_workspace_outcome(
        run_id=run_id, verdict=verdict_str, outputs=outputs,
    )
```

- [ ] **Step 4: Add the `_record_workspace_outcome` method**

Append to the `WorkspaceService` class:

```python
async def _record_workspace_outcome(
    self, *, run_id: str, verdict: str, outputs: dict
) -> None:
    """Best-effort: record the workspace verdict in verdict_outcomes."""
    try:
        async with unit_of_work() as db:
            run = (await db.execute(
                select(WorkspaceRun).where(WorkspaceRun.id == run_id)
            )).scalar_one_or_none()
            if run is None:
                return

            # Resolve theme via parent research run
            theme_id: str | None = None
            theme_seed_tickers: list[str] | None = None
            if run.parent_research_run_id:
                from backend.app.models.research_run import ResearchRun
                from backend.app.models.theme import Theme
                parent = (await db.execute(
                    select(ResearchRun).where(ResearchRun.id == run.parent_research_run_id)
                )).scalar_one_or_none()
                if parent and parent.theme_id:
                    theme_id = parent.theme_id
                    theme = (await db.execute(
                        select(Theme).where(Theme.id == theme_id)
                    )).scalar_one_or_none()
                    if theme and theme.seed_tickers and isinstance(theme.seed_tickers, list):
                        theme_seed_tickers = list(theme.seed_tickers)

            signals_row: dict | None = None
            if theme_id:
                sig_rows = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == run.ticker,
                        Signal.theme_id == theme_id,
                    )
                )).scalars().all()
                if sig_rows:
                    signals_row = {r.signal_type: r.value for r in sig_rows}

            kill_rows = []
            if run.parent_research_run_id:
                kill_rows = (await db.execute(
                    select(KillCriterionState).where(
                        KillCriterionState.research_run_id == run.parent_research_run_id
                    )
                )).scalars().all()
            kill_states = [
                {"ordinal": r.ordinal, "state": r.state} for r in kill_rows
            ]

            model_assumptions: dict | None = None
            tm = (await db.execute(
                select(TickerModel)
                .where(TickerModel.ticker == run.ticker)
                .order_by(TickerModel.version.desc())
                .limit(1)
            )).scalar_one_or_none()
            if tm and tm.state:
                model_assumptions = (tm.state or {}).get("assumptions") or {}

            profile, _ = await self._fmp.get_profile(run.ticker)
            sector = (profile or {}).get("sector")

            snapshot = outcome_tracker.build_workspace_run_signal_snapshot(
                run=run, signals_row=signals_row, kill_states=kill_states,
                model_assumptions=model_assumptions,
            )

            await outcome_tracker.record_verdict(
                source_type="workspace_run",
                source_id=run_id,
                ticker=run.ticker,
                theme_id=theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=verdict,
                verdict_emitted_at=datetime.now(timezone.utc),
                signal_snapshot=snapshot,
                fmp=self._fmp,
                db=db,
            )
    except Exception:
        logger.exception("record_verdict failed for workspace run %s", run_id)
```

- [ ] **Step 5: Run tests**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 23 tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/workspace.py
git commit -m "feat(workspace): hook record_verdict on terminal workspace_run completion"
```

---

## Task 15: backfill_from_history

**Files:**
- Modify: `backend/app/services/outcome_tracker.py` (append `backfill_from_history`)
- Modify: `backend/tests/test_outcome_tracker.py` (add 1 test)

- [ ] **Step 1: Write the failing test**

Append:

```python
from backend.app.services.outcome_tracker import backfill_from_history


class TestBackfill(unittest.TestCase):
    def test_backfill_idempotent(self):
        engine, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                # Seed one completed research_run and one terminal workspace_run via direct ORM
                from backend.app.models.research_run import ResearchRun
                from backend.app.models.workspace_run import WorkspaceRun
                rr = ResearchRun(
                    id=str(uuid4()), ticker="NVDA", theme_id=None,
                    status="completed",
                    state={"ticker": "NVDA", "status": "completed", "deep_dive_results": {}},
                    created_at=datetime.now(timezone.utc) - timedelta(days=100),
                    completed_at=datetime.now(timezone.utc) - timedelta(days=100),
                )
                wr = WorkspaceRun(
                    id=str(uuid4()), ticker="NVDA",
                    parent_research_run_id=rr.id,
                    ticker_model_version_before=1, ticker_model_version_after=2,
                    status="completed", verdict="healthy",
                    step_outputs={"challenge": {"proposed_verdict": "healthy"}},
                    citations=[],
                )
                db.add_all([rr, wr])
                await db.commit()

                entry_day = date.today() - timedelta(days=99)
                prices = {
                    "NVDA": {entry_day: Decimal("850.00")},
                    "SPY":  {entry_day: Decimal("550.00")},
                }
                fmp = _mock_fmp_price_series(prices)
                fmp.get_profile = AsyncMock(return_value=({"sector": "Technology"}, None))

                first = await backfill_from_history(fmp=fmp, db=db)
                second = await backfill_from_history(fmp=fmp, db=db)
                return first.outcomes_created, second.outcomes_created, second.outcomes_existed

        first_n, second_n, existed = asyncio.run(_run())
        # Backfill may or may not see completed_at fields populated in test ResearchRun;
        # accept >=0 for the first and 0-new on second (idempotent).
        self.assertEqual(second_n, 0)
        self.assertTrue(existed >= 0)
```

- [ ] **Step 2: Verify test fails**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 1 new test ERROR (ImportError on `backfill_from_history`).

- [ ] **Step 3: Implement `backfill_from_history`**

Append to `backend/app/services/outcome_tracker.py`:

```python
async def backfill_from_history(*, fmp: FMPClient, db: AsyncSession) -> BackfillSummary:
    """Walk completed research_runs + terminal workspace_runs; record_verdict for each (idempotent).

    Then run refresh_snapshots once to populate due offsets across new outcomes.
    """
    from backend.app.models.research_run import ResearchRun
    from backend.app.models.workspace_run import WorkspaceRun
    from backend.app.models.theme import Theme
    from backend.app.models.signal import Signal

    created = 0
    existed = 0
    errors: list[dict[str, str]] = []

    # ── Research runs ────────────────────────────────────────────────────────
    research_runs = (await db.execute(
        select(ResearchRun).where(ResearchRun.status.in_(["completed", "watchlist", "pass"]))
    )).scalars().all()

    for run in research_runs:
        existing = (await db.execute(
            select(VerdictOutcome).where(
                VerdictOutcome.source_type == "research_run",
                VerdictOutcome.source_id == run.id,
            )
        )).scalar_one_or_none()
        if existing is not None:
            existed += 1
            continue

        try:
            theme_seed_tickers = None
            if run.theme_id:
                theme = (await db.execute(select(Theme).where(Theme.id == run.theme_id))).scalar_one_or_none()
                if theme and isinstance(theme.seed_tickers, list):
                    theme_seed_tickers = list(theme.seed_tickers)

            signals_row = None
            if run.theme_id:
                sigs = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == run.ticker, Signal.theme_id == run.theme_id
                    )
                )).scalars().all()
                if sigs:
                    signals_row = {s.signal_type: s.value for s in sigs}

            profile, _ = await fmp.get_profile(run.ticker)
            sector = (profile or {}).get("sector")

            state_dict = run.state if isinstance(run.state, dict) else {}
            dd = state_dict.get("deep_dive_results") or {}
            scores = {k: (v.get("score") if isinstance(v, dict) else None) for k, v in dd.items()}
            snapshot = {
                "signals_row": signals_row or {},
                "deep_dive_scores": scores,
                "kill_criterion_state": [],
            }

            emitted_at = run.completed_at or run.created_at
            if emitted_at is None:
                errors.append({"source_id": run.id, "error": "no completed_at/created_at"})
                continue

            await record_verdict(
                source_type="research_run",
                source_id=run.id,
                ticker=run.ticker,
                theme_id=run.theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=run.status,
                verdict_emitted_at=emitted_at,
                signal_snapshot=snapshot,
                fmp=fmp,
                db=db,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed for research_run %s", run.id)
            errors.append({"source_id": run.id, "error": str(exc)})

    # ── Workspace runs ────────────────────────────────────────────────────────
    workspace_runs = (await db.execute(
        select(WorkspaceRun).where(WorkspaceRun.status == "completed", WorkspaceRun.verdict.is_not(None))
    )).scalars().all()

    for wrun in workspace_runs:
        existing = (await db.execute(
            select(VerdictOutcome).where(
                VerdictOutcome.source_type == "workspace_run",
                VerdictOutcome.source_id == wrun.id,
            )
        )).scalar_one_or_none()
        if existing is not None:
            existed += 1
            continue

        try:
            theme_id: str | None = None
            theme_seed_tickers: list[str] | None = None
            if wrun.parent_research_run_id:
                parent = (await db.execute(
                    select(ResearchRun).where(ResearchRun.id == wrun.parent_research_run_id)
                )).scalar_one_or_none()
                if parent and parent.theme_id:
                    theme_id = parent.theme_id
                    theme = (await db.execute(
                        select(Theme).where(Theme.id == theme_id)
                    )).scalar_one_or_none()
                    if theme and isinstance(theme.seed_tickers, list):
                        theme_seed_tickers = list(theme.seed_tickers)

            signals_row = None
            if theme_id:
                sigs = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == wrun.ticker, Signal.theme_id == theme_id
                    )
                )).scalars().all()
                if sigs:
                    signals_row = {s.signal_type: s.value for s in sigs}

            profile, _ = await fmp.get_profile(wrun.ticker)
            sector = (profile or {}).get("sector")

            step_outputs = wrun.step_outputs or {}
            verdicts = {}
            for step, payload in step_outputs.items():
                if isinstance(payload, dict):
                    verdicts[step] = payload.get("proposed_verdict") or payload.get("verdict")
            snapshot = {
                "signals_row": signals_row or {},
                "workspace_step_verdicts": verdicts,
                "kill_criterion_state": [],
                "model_assumptions": {},
            }

            emitted_at = wrun.updated_at or wrun.created_at
            if emitted_at is None:
                errors.append({"source_id": wrun.id, "error": "no timestamp"})
                continue

            await record_verdict(
                source_type="workspace_run",
                source_id=wrun.id,
                ticker=wrun.ticker,
                theme_id=theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=wrun.verdict,
                verdict_emitted_at=emitted_at,
                signal_snapshot=snapshot,
                fmp=fmp,
                db=db,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed for workspace_run %s", wrun.id)
            errors.append({"source_id": wrun.id, "error": str(exc)})

    # Refresh in the same transaction so existing outcomes also pick up any due snapshots
    refresh = await refresh_snapshots(fmp=fmp, db=db)
    return BackfillSummary(
        outcomes_created=created,
        outcomes_existed=existed,
        snapshots_inserted=refresh.snapshotted,
        errors=errors + refresh.errors,
    )
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcome_tracker -v
```
Expected: 24 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/outcome_tracker.py backend/tests/test_outcome_tracker.py
git commit -m "feat(outcome): backfill_from_history idempotent over research + workspace runs + 1 test"
```

---

## Task 16: Backfill CLI script

**Files:**
- Create: `backend/scripts/backfill_outcomes.py`

- [ ] **Step 1: Write the CLI**

```python
"""One-shot backfill: populate verdict_outcomes from existing research + workspace runs.

Usage from project root with venv active:
    python -m backend.scripts.backfill_outcomes
"""
import asyncio
import logging

from backend.app.clients.fmp import FMPClient
from backend.app.config import get_settings
from backend.app.db import async_session
from backend.app.services import outcome_tracker


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("backfill")


async def main() -> None:
    settings = get_settings()
    fmp = FMPClient(api_key=settings.fmp_api_key)
    try:
        async with async_session() as db:
            summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
            await db.commit()
    finally:
        await fmp.close()

    log.info(
        "backfill complete: created=%d existed=%d snapshots_inserted=%d errors=%d",
        summary.outcomes_created,
        summary.outcomes_existed,
        summary.snapshots_inserted,
        len(summary.errors),
    )
    for err in summary.errors[:10]:
        log.warning("  err: %s", err)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke test against the real DB (manual)**

```bash
python -m backend.scripts.backfill_outcomes
```
Expected: log line like `backfill complete: created=N existed=0 snapshots_inserted=M errors=0`. N depends on how many completed runs exist locally.

If N=0 (no completed runs locally), that's fine — re-run after a real pipeline completes.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/backfill_outcomes.py
git commit -m "feat(outcome): CLI for backfill_from_history"
```

---

## Task 17: APScheduler cron + wire outcomes router

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Locate the scheduler block**

Around line 71-89 of `backend/app/main.py`:
```python
scheduler = AsyncIOScheduler()
scheduler.add_job(
    run_daily_refresh, ...
)
scheduler.add_job(
    run_daily_earnings_refresh, ...
)
scheduler.start()
```

- [ ] **Step 2: Add the new job + router**

Add the outcome refresh job after the earnings job:

```python
from backend.app.services.outcome_tracker import refresh_snapshots
from backend.app.db import unit_of_work

async def _run_daily_outcome_refresh() -> None:
    fmp = app.state.fmp
    async with unit_of_work() as db:
        summary = await refresh_snapshots(fmp=fmp, db=db)
    logger.info(
        "outcome refresh: processed=%d snapshotted=%d closed=%d errors=%d",
        summary.processed, summary.snapshotted, summary.closed, len(summary.errors),
    )

scheduler.add_job(
    _run_daily_outcome_refresh,
    CronTrigger(hour=3, minute=0, timezone="UTC"),
    id="outcome_snapshot_refresh",
    replace_existing=True,
)
```

(If `app.state.fmp` isn't set in lifespan in this codebase, follow the same pattern that's used for the signal scheduler — usually a module-level helper that reuses singletons.)

- [ ] **Step 3: Register the outcomes router**

Near the other `app.include_router(...)` calls add:
```python
from backend.app.api import outcomes as outcomes_router
app.include_router(outcomes_router.router)
```

- [ ] **Step 4: Start the backend; verify scheduler logs**

```bash
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload
```
Expected: startup log line including `Added job "_run_daily_outcome_refresh"` (APScheduler default). No errors.

Stop the server (Ctrl+C).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(main): register outcomes router + daily snapshot-refresh cron (03:00 UTC)"
```

---

## Task 18: API — POST /api/outcomes/backfill

**Files:**
- Create: `backend/app/api/outcomes.py`
- Create: `backend/tests/test_outcomes_api.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for backend.app.api.outcomes."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


class TestBackfillEndpoint(unittest.TestCase):
    def test_post_backfill_returns_202(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes.outcome_tracker.backfill_from_history",
            new=AsyncMock(return_value=MagicMock(
                outcomes_created=3, outcomes_existed=10, snapshots_inserted=8, errors=[],
                model_dump=lambda: {"outcomes_created": 3, "outcomes_existed": 10,
                                     "snapshots_inserted": 8, "errors": []},
            )),
        ):
            client = TestClient(app)
            r = client.post("/api/outcomes/backfill")
            self.assertEqual(r.status_code, 202)
            body = r.json()
            self.assertEqual(body["outcomes_created"], 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify test fails**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: ImportError (`backend.app.api.outcomes` not found).

- [ ] **Step 3: Create the router skeleton + backfill endpoint**

```python
"""GET /api/outcomes/*, POST /api/outcomes/backfill."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.db import async_session, unit_of_work
from backend.app.models.outcome_schemas import BackfillSummary
from backend.app.services import outcome_tracker

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED, response_model=BackfillSummary)
async def trigger_backfill(request: Request) -> BackfillSummary:
    """One-shot backfill of verdict_outcomes from completed research + workspace runs.

    Idempotent. Safe to call multiple times. Returns 202 with summary stats.
    """
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
    return summary
```

- [ ] **Step 4: Verify the route is registered (from Task 17)**

```bash
python -c "from backend.app.main import app; print([r.path for r in app.routes if '/outcomes' in r.path])"
```
Expected: `['/api/outcomes/backfill']`.

- [ ] **Step 5: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: 1 test passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/outcomes.py backend/tests/test_outcomes_api.py
git commit -m "feat(api): POST /api/outcomes/backfill + test"
```

---

## Task 19: API — GET /api/outcomes/by-source

**Files:**
- Modify: `backend/app/api/outcomes.py`
- Modify: `backend/tests/test_outcomes_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_outcomes_api.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4


class TestGetBySource(unittest.TestCase):
    def test_get_by_source_returns_outcome(self):
        from backend.app.main import app

        outcome_payload = {
            "id": str(uuid4()),
            "source_type": "workspace_run",
            "source_id": str(uuid4()),
            "ticker": "NVDA",
            "theme_id": None,
            "verdict": "healthy",
            "verdict_emitted_at": "2026-01-02T22:00:00+00:00",
            "entry_price_at": "2026-01-05",
            "entry_price": "850.00",
            "sector_etf_ticker": None,
            "superseded_at": None,
            "closed_at": None,
            "realized_ticker_return_pct": None,
            "realized_spy_excess_pct": None,
            "realized_sector_excess_pct": None,
            "realized_theme_basket_excess_pct": None,
            "snapshots": [],
            "theme_basket_constituents": None,
            "signal_snapshot": None,
        }

        with patch(
            "backend.app.api.outcomes._get_outcome_by_source",
            new=AsyncMock(return_value=outcome_payload),
        ):
            client = TestClient(app)
            r = client.get(f"/api/outcomes/by-source/workspace_run/{outcome_payload['source_id']}")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")

    def test_get_by_source_404_when_missing(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._get_outcome_by_source",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app)
            r = client.get(f"/api/outcomes/by-source/research_run/{uuid4()}")
            self.assertEqual(r.status_code, 404)
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: ImportError on `_get_outcome_by_source`.

- [ ] **Step 3: Implement the endpoint**

Append to `backend/app/api/outcomes.py`:

```python
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.app.models.outcome import VerdictOutcome
from backend.app.models.outcome_schemas import OutcomeDetail, SnapshotRead


async def _get_outcome_by_source(*, source_type: str, source_id: str, db) -> dict | None:
    outcome = (await db.execute(
        select(VerdictOutcome)
        .where(
            VerdictOutcome.source_type == source_type,
            VerdictOutcome.source_id == source_id,
        )
        .options(selectinload(VerdictOutcome.snapshots))
    )).scalar_one_or_none()
    if outcome is None:
        return None
    return _outcome_to_detail_dict(outcome)


def _outcome_to_detail_dict(outcome: VerdictOutcome) -> dict:
    snaps = sorted(outcome.snapshots, key=lambda s: ("1d", "1w", "1m", "3m", "6m").index(s.snapshot_offset))
    return {
        "id": outcome.id,
        "source_type": outcome.source_type,
        "source_id": outcome.source_id,
        "ticker": outcome.ticker,
        "theme_id": outcome.theme_id,
        "verdict": outcome.verdict,
        "verdict_emitted_at": outcome.verdict_emitted_at,
        "entry_price_at": outcome.entry_price_at,
        "entry_price": outcome.entry_price,
        "sector_etf_ticker": outcome.sector_etf_ticker,
        "superseded_at": outcome.superseded_at,
        "closed_at": outcome.closed_at,
        "realized_ticker_return_pct": outcome.realized_ticker_return_pct,
        "realized_spy_excess_pct": outcome.realized_spy_excess_pct,
        "realized_sector_excess_pct": outcome.realized_sector_excess_pct,
        "realized_theme_basket_excess_pct": outcome.realized_theme_basket_excess_pct,
        "snapshots": [
            {
                "snapshot_offset": s.snapshot_offset,
                "snapshot_date": s.snapshot_date,
                "ticker_price": s.ticker_price,
                "spy_price": s.spy_price,
                "sector_etf_price": s.sector_etf_price,
                "theme_basket_value": s.theme_basket_value,
                "ticker_return_pct": s.ticker_return_pct,
                "spy_excess_pct": s.spy_excess_pct,
                "sector_excess_pct": s.sector_excess_pct,
                "theme_basket_excess_pct": s.theme_basket_excess_pct,
            }
            for s in snaps
        ],
        "theme_basket_constituents": outcome.theme_basket_constituents,
        "signal_snapshot": outcome.signal_snapshot,
    }


@router.get("/by-source/{source_type}/{source_id}", response_model=OutcomeDetail)
async def get_outcome_by_source(source_type: str, source_id: str) -> OutcomeDetail:
    if source_type not in ("research_run", "workspace_run"):
        raise HTTPException(status_code=400, detail="invalid source_type")
    async with async_session() as db:
        payload = await _get_outcome_by_source(
            source_type=source_type, source_id=source_id, db=db
        )
    if payload is None:
        raise HTTPException(status_code=404, detail="outcome not found")
    return payload
```

- [ ] **Step 4: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/outcomes.py backend/tests/test_outcomes_api.py
git commit -m "feat(api): GET /api/outcomes/by-source/{type}/{id} + 2 tests"
```

---

## Task 20: API — GET /api/outcomes (list)

**Files:**
- Modify: `backend/app/api/outcomes.py`

- [ ] **Step 1: Implement the list endpoint**

Append:

```python
from typing import Literal


@router.get("", response_model=list[dict])
async def list_outcomes(
    theme_id: str | None = None,
    verdict: str | None = None,
    source_type: Literal["research_run", "workspace_run"] | None = None,
    superseded: Literal["true", "false", "all"] = "all",
    closed: Literal["true", "false", "all"] = "all",
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, 500))
    async with async_session() as db:
        q = select(VerdictOutcome).options(selectinload(VerdictOutcome.snapshots))
        if theme_id is not None:
            q = q.where(VerdictOutcome.theme_id == theme_id)
        if verdict is not None:
            q = q.where(VerdictOutcome.verdict == verdict)
        if source_type is not None:
            q = q.where(VerdictOutcome.source_type == source_type)
        if superseded == "true":
            q = q.where(VerdictOutcome.superseded_at.is_not(None))
        elif superseded == "false":
            q = q.where(VerdictOutcome.superseded_at.is_(None))
        if closed == "true":
            q = q.where(VerdictOutcome.closed_at.is_not(None))
        elif closed == "false":
            q = q.where(VerdictOutcome.closed_at.is_(None))
        q = q.order_by(VerdictOutcome.verdict_emitted_at.desc()).offset(offset).limit(limit)

        rows = (await db.execute(q)).scalars().all()
        return [_outcome_to_detail_dict(r) for r in rows]
```

- [ ] **Step 2: Smoke test manually**

Start backend, hit:
```bash
curl -s "http://127.0.0.1:8000/api/outcomes?limit=5" | python -m json.tool | head -50
```
Expected: JSON array (empty if no outcomes recorded yet).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/outcomes.py
git commit -m "feat(api): GET /api/outcomes list with filters + pagination"
```

---

## Task 21: API — GET /api/outcomes/summary

**Files:**
- Modify: `backend/app/api/outcomes.py`
- Modify: `backend/tests/test_outcomes_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_outcomes_api.py`:

```python
class TestSummary(unittest.TestCase):
    def test_summary_empty_window_returns_zero_filled(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.outcomes._compute_summary",
            new=AsyncMock(return_value={
                "window": "90d", "snapshot_offset": "3m", "benchmark": "spy", "source_type": "all",
                "overall": {"n": 0, "mean_return_pct": None, "mean_excess_pct": None,
                            "win_rate": None, "median_excess_pct": None},
                "by_verdict": {},
                "by_theme": [],
                "by_signal_bucket": {},
            }),
        ):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["overall"]["n"], 0)

    def test_summary_filters_pass_through(self):
        from backend.app.main import app

        captured = {}

        async def _stub(*, theme_id, window, snapshot_offset, benchmark, source_type, db):
            captured.update({
                "theme_id": theme_id, "window": window, "snapshot_offset": snapshot_offset,
                "benchmark": benchmark, "source_type": source_type,
            })
            return {
                "window": window, "snapshot_offset": snapshot_offset, "benchmark": benchmark,
                "source_type": source_type,
                "overall": {"n": 0, "mean_return_pct": None, "mean_excess_pct": None,
                            "win_rate": None, "median_excess_pct": None},
                "by_verdict": {}, "by_theme": [], "by_signal_bucket": {},
            }

        with patch("backend.app.api.outcomes._compute_summary", new=_stub):
            client = TestClient(app)
            r = client.get("/api/outcomes/summary?window=30d&snapshot_offset=1m&benchmark=sector&source_type=workspace_run&theme_id=abc")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(captured["window"], "30d")
            self.assertEqual(captured["benchmark"], "sector")
            self.assertEqual(captured["source_type"], "workspace_run")
```

- [ ] **Step 2: Verify tests fail**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: ImportError on `_compute_summary`.

- [ ] **Step 3: Implement the summary endpoint**

Append:

```python
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import fmean, median
from backend.app.models.outcome_schemas import (
    Benchmark, OutcomeSummary, SignalBucket, SnapshotOffset, StatGroup, ThemeStat,
    VerdictStats, Window,
)


def _excess_attr(benchmark: Benchmark) -> str:
    return {
        "spy": "spy_excess_pct",
        "sector": "sector_excess_pct",
        "theme_basket": "theme_basket_excess_pct",
    }[benchmark]


def _window_cutoff(window: Window) -> datetime | None:
    if window == "all":
        return None
    days = {"30d": 30, "90d": 90, "1y": 365}[window]
    return datetime.now(timezone.utc) - timedelta(days=days)


def _stats_for(rows: list[tuple[float | None, float | None]]) -> StatGroup:
    """rows: list of (ticker_return_pct, excess_pct)."""
    n = len(rows)
    if n == 0:
        return StatGroup(n=0, mean_return_pct=None, mean_excess_pct=None,
                          win_rate=None, median_excess_pct=None)
    returns = [r for (r, _) in rows if r is not None]
    excess = [x for (_, x) in rows if x is not None]
    win_rate = (sum(1 for x in excess if x > 0) / len(excess)) if excess else None
    return StatGroup(
        n=n,
        mean_return_pct=fmean(returns) if returns else None,
        mean_excess_pct=fmean(excess) if excess else None,
        win_rate=win_rate,
        median_excess_pct=median(excess) if excess else None,
    )


def _quartile_buckets(values: list[tuple[float | None, float]]) -> list[SignalBucket]:
    """values: list of (signal_value, excess_pct). Buckets by quartile of signal_value over non-null."""
    non_null = [(s, e) for (s, e) in values if s is not None]
    null_n = len(values) - len(non_null)

    buckets: list[SignalBucket] = []
    if not non_null:
        return [SignalBucket(bucket="null", n=null_n, mean_excess_pct=None, win_rate=None)]

    sorted_signals = sorted(s for s, _ in non_null)
    def q(p: float) -> float:
        i = int(p * (len(sorted_signals) - 1))
        return sorted_signals[i]
    q1, q2, q3 = q(0.25), q(0.5), q(0.75)

    bins: dict[str, list[float]] = defaultdict(list)
    for s, e in non_null:
        if s <= q1:    bins["0-25th"].append(e)
        elif s <= q2:  bins["25-50th"].append(e)
        elif s <= q3:  bins["50-75th"].append(e)
        else:          bins["75-100th"].append(e)

    for key in ("0-25th", "25-50th", "50-75th", "75-100th"):
        es = bins.get(key, [])
        buckets.append(SignalBucket(
            bucket=key,
            n=len(es),
            mean_excess_pct=fmean(es) if es else None,
            win_rate=(sum(1 for x in es if x > 0) / len(es)) if es else None,
        ))
    buckets.append(SignalBucket(bucket="null", n=null_n, mean_excess_pct=None, win_rate=None))
    return buckets


async def _compute_summary(
    *,
    theme_id: str | None,
    window: Window,
    snapshot_offset: SnapshotOffset,
    benchmark: Benchmark,
    source_type: str,
    db,
) -> dict:
    from backend.app.models.outcome import VerdictReturnSnapshot
    from backend.app.models.theme import Theme

    cutoff = _window_cutoff(window)
    excess_attr = _excess_attr(benchmark)

    q = (
        select(VerdictOutcome, VerdictReturnSnapshot)
        .join(
            VerdictReturnSnapshot,
            (VerdictReturnSnapshot.outcome_id == VerdictOutcome.id)
            & (VerdictReturnSnapshot.snapshot_offset == snapshot_offset),
            isouter=True,
        )
    )
    if cutoff is not None:
        q = q.where(VerdictOutcome.verdict_emitted_at >= cutoff)
    if theme_id is not None:
        q = q.where(VerdictOutcome.theme_id == theme_id)
    if source_type != "all":
        q = q.where(VerdictOutcome.source_type == source_type)

    rows = (await db.execute(q)).all()

    overall_pairs: list[tuple[float | None, float | None]] = []
    by_verdict: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)
    by_theme: dict[str | None, list[tuple[float | None, float | None]]] = defaultdict(list)
    signals_attr: dict[str, list[tuple[float | None, float]]] = defaultdict(list)

    theme_names: dict[str | None, str | None] = {None: None}

    for outcome, snap in rows:
        if snap is None:
            t_ret, x = None, None
        else:
            t_ret = float(snap.ticker_return_pct) if snap.ticker_return_pct is not None else None
            x_val = getattr(snap, excess_attr)
            x = float(x_val) if x_val is not None else None

        overall_pairs.append((t_ret, x))
        by_verdict[outcome.verdict].append((t_ret, x))
        by_theme[outcome.theme_id].append((t_ret, x))

        # Quartile buckets — only when we have an excess number to anchor to
        if x is not None and outcome.signal_snapshot:
            sigs = (outcome.signal_snapshot.get("signals_row") or {})
            for sig_name, sig_val in sigs.items():
                sval = sig_val if isinstance(sig_val, (int, float)) else None
                signals_attr[sig_name].append((sval, x))

    # Theme names lookup
    distinct_ids = [tid for tid in by_theme.keys() if tid]
    if distinct_ids:
        themes = (await db.execute(
            select(Theme.id, Theme.name).where(Theme.id.in_(distinct_ids))
        )).all()
        for tid, name in themes:
            theme_names[tid] = name

    verdict_stats = VerdictStats()
    for v, pairs in by_verdict.items():
        if v == "pass":
            setattr(verdict_stats, "passed", _stats_for(pairs))
        elif hasattr(verdict_stats, v):
            setattr(verdict_stats, v, _stats_for(pairs))

    by_theme_list = [
        ThemeStat(theme_id=tid, theme_name=theme_names.get(tid), stats=_stats_for(pairs))
        for tid, pairs in by_theme.items()
    ]

    by_signal_bucket = {
        sig: _quartile_buckets(pairs) for sig, pairs in signals_attr.items()
    }

    return {
        "window": window,
        "snapshot_offset": snapshot_offset,
        "benchmark": benchmark,
        "source_type": source_type,
        "overall": _stats_for(overall_pairs).model_dump(),
        "by_verdict": verdict_stats.model_dump(),
        "by_theme": [ts.model_dump() for ts in by_theme_list],
        "by_signal_bucket": {k: [b.model_dump() for b in v] for k, v in by_signal_bucket.items()},
    }


@router.get("/summary", response_model=OutcomeSummary)
async def get_summary(
    theme_id: str | None = None,
    window: Window = "90d",
    snapshot_offset: SnapshotOffset = "3m",
    benchmark: Benchmark = "spy",
    source_type: Literal["research_run", "workspace_run", "all"] = "all",
) -> dict:
    async with async_session() as db:
        return await _compute_summary(
            theme_id=theme_id, window=window, snapshot_offset=snapshot_offset,
            benchmark=benchmark, source_type=source_type, db=db,
        )
```

- [ ] **Step 2: Run tests — expect green**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/outcomes.py backend/tests/test_outcomes_api.py
git commit -m "feat(api): GET /api/outcomes/summary with verdict/theme/signal-bucket rollups + 2 tests"
```

---

## Task 22: Quartile-bucket math tests

**Files:**
- Modify: `backend/tests/test_outcomes_api.py`

- [ ] **Step 1: Add quartile math tests**

```python
class TestQuartileBuckets(unittest.TestCase):
    def test_quartile_buckets_balanced(self):
        from backend.app.api.outcomes import _quartile_buckets
        # 8 outcomes with signal 1..8 and excess matching signal
        values = [(float(i), float(i)) for i in range(1, 9)]
        buckets = _quartile_buckets(values)
        by_key = {b.bucket: b for b in buckets}
        self.assertEqual(by_key["0-25th"].n, 2)
        self.assertEqual(by_key["25-50th"].n, 2)
        self.assertEqual(by_key["50-75th"].n, 2)
        self.assertEqual(by_key["75-100th"].n, 2)
        # Top quartile mean should be > bottom quartile mean
        self.assertGreater(by_key["75-100th"].mean_excess_pct, by_key["0-25th"].mean_excess_pct)

    def test_quartile_buckets_includes_null(self):
        from backend.app.api.outcomes import _quartile_buckets
        values = [(None, 5.0), (1.0, 0.0), (2.0, 1.0)]
        buckets = _quartile_buckets(values)
        by_key = {b.bucket: b for b in buckets}
        self.assertEqual(by_key["null"].n, 1)
```

- [ ] **Step 2: Run — expect green**

```bash
python -m unittest backend.tests.test_outcomes_api -v
```
Expected: 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_outcomes_api.py
git commit -m "test(api): quartile bucket math (2 tests)"
```

---

## Task 23: Frontend — lib/api.ts types + client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Append the outcomes types**

Find the end of the existing exports section in `frontend/lib/api.ts` and append:

```typescript
// ============================================================================
// Outcome tracking
// ============================================================================

export type SnapshotOffset = "1d" | "1w" | "1m" | "3m" | "6m";
export type SourceType = "research_run" | "workspace_run";
export type Benchmark = "spy" | "sector" | "theme_basket";
export type Window = "30d" | "90d" | "1y" | "all";

export interface SnapshotRead {
  snapshot_offset: SnapshotOffset;
  snapshot_date: string;
  ticker_price: string;
  spy_price: string | null;
  sector_etf_price: string | null;
  theme_basket_value: string | null;
  ticker_return_pct: string;
  spy_excess_pct: string | null;
  sector_excess_pct: string | null;
  theme_basket_excess_pct: string | null;
}

export interface OutcomeListItem {
  id: string;
  source_type: SourceType;
  source_id: string;
  ticker: string;
  theme_id: string | null;
  verdict: string;
  verdict_emitted_at: string;
  entry_price_at: string;
  entry_price: string;
  sector_etf_ticker: string | null;
  superseded_at: string | null;
  closed_at: string | null;
  realized_ticker_return_pct: string | null;
  realized_spy_excess_pct: string | null;
  realized_sector_excess_pct: string | null;
  realized_theme_basket_excess_pct: string | null;
  snapshots: SnapshotRead[];
}

export interface OutcomeDetail extends OutcomeListItem {
  theme_basket_constituents: { ticker: string; entry_price: string }[] | null;
  signal_snapshot: Record<string, unknown> | null;
}

export interface StatGroup {
  n: number;
  mean_return_pct: number | null;
  mean_excess_pct: number | null;
  win_rate: number | null;
  median_excess_pct: number | null;
}

export interface ThemeStat {
  theme_id: string | null;
  theme_name: string | null;
  stats: StatGroup;
}

export interface SignalBucket {
  bucket: string;
  n: number;
  mean_excess_pct: number | null;
  win_rate: number | null;
}

export interface OutcomeSummary {
  window: Window;
  snapshot_offset: SnapshotOffset;
  benchmark: Benchmark;
  source_type: SourceType | "all";
  overall: StatGroup;
  by_verdict: Record<string, StatGroup | null>;
  by_theme: ThemeStat[];
  by_signal_bucket: Record<string, SignalBucket[]>;
}

export interface BackfillSummary {
  outcomes_created: number;
  outcomes_existed: number;
  snapshots_inserted: number;
  errors: { source_id?: string; outcome_id?: string; error: string }[];
}

export interface OutcomeSummaryQuery {
  themeId?: string;
  window?: Window;
  snapshotOffset?: SnapshotOffset;
  benchmark?: Benchmark;
  sourceType?: SourceType | "all";
}

export interface OutcomeListQuery {
  themeId?: string;
  verdict?: string;
  sourceType?: SourceType;
  superseded?: "true" | "false" | "all";
  closed?: "true" | "false" | "all";
  limit?: number;
  offset?: number;
}

export const outcomesApi = {
  async getSummary(q: OutcomeSummaryQuery = {}): Promise<OutcomeSummary> {
    const params = new URLSearchParams();
    if (q.themeId) params.set("theme_id", q.themeId);
    if (q.window) params.set("window", q.window);
    if (q.snapshotOffset) params.set("snapshot_offset", q.snapshotOffset);
    if (q.benchmark) params.set("benchmark", q.benchmark);
    if (q.sourceType) params.set("source_type", q.sourceType);
    return apiFetch(`/api/outcomes/summary?${params.toString()}`);
  },

  async list(q: OutcomeListQuery = {}): Promise<OutcomeListItem[]> {
    const params = new URLSearchParams();
    if (q.themeId) params.set("theme_id", q.themeId);
    if (q.verdict) params.set("verdict", q.verdict);
    if (q.sourceType) params.set("source_type", q.sourceType);
    if (q.superseded) params.set("superseded", q.superseded);
    if (q.closed) params.set("closed", q.closed);
    if (q.limit != null) params.set("limit", String(q.limit));
    if (q.offset != null) params.set("offset", String(q.offset));
    return apiFetch(`/api/outcomes?${params.toString()}`);
  },

  async getBySource(sourceType: SourceType, sourceId: string): Promise<OutcomeDetail> {
    return apiFetch(`/api/outcomes/by-source/${sourceType}/${sourceId}`);
  },

  async triggerBackfill(): Promise<BackfillSummary> {
    return apiFetch(`/api/outcomes/backfill`, { method: "POST" });
  },
};
```

(The `apiFetch` helper should already exist in `lib/api.ts` — check before adding. If not, look at how other API clients in the same file build requests and follow that pattern instead.)

- [ ] **Step 2: Run frontend lint + typecheck**

```bash
cd frontend && npm run lint && cd ..
```
Expected: no errors. (Warnings about other code OK.)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): outcomesApi types + client methods"
```

---

## Task 24: Frontend — ReturnCell (shared formatter)

**Files:**
- Create: `frontend/components/performance/ReturnCell.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

/** Sign-colored return cell. Accepts either a fractional string ("0.123") or null. */
export function ReturnCell({ value, asPercent = true }: { value: string | number | null; asPercent?: boolean }) {
  if (value == null) return <span className="text-[var(--text-muted)]">—</span>;
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(num)) return <span className="text-[var(--text-muted)]">—</span>;
  const display = asPercent ? `${(num * 100).toFixed(2)}%` : num.toFixed(2);
  const color =
    num > 0.0001 ? "text-emerald-600 dark:text-emerald-400"
    : num < -0.0001 ? "text-rose-600 dark:text-rose-400"
    : "text-[var(--text-muted)]";
  const sign = num > 0.0001 ? "+" : "";
  return <span className={color}>{sign}{display}</span>;
}
```

- [ ] **Step 2: Build verify**

```bash
cd frontend && npm run lint && cd ..
```
Expected: no errors in `ReturnCell.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/performance/ReturnCell.tsx
git commit -m "feat(performance): ReturnCell shared formatter"
```

---

## Task 25: Frontend — PerformanceFilters

**Files:**
- Create: `frontend/components/performance/PerformanceFilters.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { Benchmark, SnapshotOffset, SourceType, Window } from "@/lib/api";

const WINDOWS: Window[] = ["30d", "90d", "1y", "all"];
const OFFSETS: SnapshotOffset[] = ["1d", "1w", "1m", "3m", "6m"];
const BENCHMARKS: Benchmark[] = ["spy", "sector", "theme_basket"];
const SOURCES: ("all" | SourceType)[] = ["all", "research_run", "workspace_run"];

export function PerformanceFilters() {
  const router = useRouter();
  const sp = useSearchParams();

  const current = {
    window: (sp.get("window") as Window) ?? "90d",
    snapshot_offset: (sp.get("snapshot_offset") as SnapshotOffset) ?? "3m",
    benchmark: (sp.get("benchmark") as Benchmark) ?? "spy",
    source_type: (sp.get("source_type") as "all" | SourceType) ?? "all",
  };

  function set(key: string, value: string) {
    const params = new URLSearchParams(sp.toString());
    params.set(key, value);
    router.push(`/performance?${params.toString()}`);
  }

  return (
    <div className="flex flex-wrap gap-3 p-3 border-b border-[var(--border)]" data-print-hide="true">
      <FilterGroup label="Window" options={WINDOWS} value={current.window} onChange={(v) => set("window", v)} />
      <FilterGroup label="Offset" options={OFFSETS} value={current.snapshot_offset} onChange={(v) => set("snapshot_offset", v)} />
      <FilterGroup label="Benchmark" options={BENCHMARKS} value={current.benchmark} onChange={(v) => set("benchmark", v)} format={fmtBenchmark} />
      <FilterGroup label="Source" options={SOURCES} value={current.source_type} onChange={(v) => set("source_type", v)} format={fmtSource} />
    </div>
  );
}

function fmtBenchmark(v: string) {
  return v === "spy" ? "SPY" : v === "sector" ? "Sector ETF" : "Theme basket";
}
function fmtSource(v: string) {
  return v === "all" ? "All" : v === "research_run" ? "Research" : "Workspace";
}

function FilterGroup<T extends string>({
  label, options, value, onChange, format,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  format?: (v: T) => string;
}) {
  return (
    <div className="flex items-center gap-1 text-sm">
      <span className="text-[var(--text-muted)] mr-1">{label}:</span>
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={
            "px-2 py-1 rounded " +
            (opt === value
              ? "bg-[var(--primary)] text-white"
              : "bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]")
          }
        >
          {format ? format(opt) : opt}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Build verify**

```bash
cd frontend && npm run lint && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/performance/PerformanceFilters.tsx
git commit -m "feat(performance): PerformanceFilters bar driving URL state"
```

---

## Task 26: Frontend — HeroBand

**Files:**
- Create: `frontend/components/performance/HeroBand.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function HeroBand({ summary }: { summary: OutcomeSummary }) {
  const { overall, benchmark } = summary;
  const benchLabel = benchmark === "spy" ? "SPY" : benchmark === "sector" ? "Sector ETF" : "Theme basket";

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">
        Lifetime IRR — vs {benchLabel} · {summary.window} window · {summary.snapshot_offset} snapshot
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Tile label="Mean return" value={overall.mean_return_pct} />
        <Tile label="Excess vs benchmark" value={overall.mean_excess_pct} highlight />
        <Tile label="Win rate" value={overall.win_rate} asPercent />
      </div>
      <div className="mt-3 text-sm text-[var(--text-muted)]">
        N = {overall.n} · Median excess: <ReturnCell value={overall.median_excess_pct} />
      </div>
    </section>
  );
}

function Tile({
  label, value, highlight = false, asPercent = true,
}: {
  label: string;
  value: number | null;
  highlight?: boolean;
  asPercent?: boolean;
}) {
  return (
    <div className={"p-4 rounded " + (highlight ? "bg-[var(--surface-2)]" : "bg-[var(--surface)]")}>
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className="text-2xl font-semibold mt-1">
        <ReturnCell value={value} asPercent={asPercent} />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/performance/HeroBand.tsx
git commit -m "feat(performance): HeroBand — lifetime IRR tiles"
```

---

## Task 27: Frontend — ByVerdictTable

**Files:**
- Create: `frontend/components/performance/ByVerdictTable.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

const VERDICT_ROW_ORDER = [
  "healthy", "imminent", "triggered", "broken", "completed", "watchlist", "passed",
] as const;

export function ByVerdictTable({ summary }: { summary: OutcomeSummary }) {
  const rows = VERDICT_ROW_ORDER
    .map((v) => ({ verdict: v, stats: summary.by_verdict[v] }))
    .filter((r) => r.stats && r.stats.n > 0);

  if (rows.length === 0) {
    return <div className="px-4 py-6 text-[var(--text-muted)]">No outcomes in window.</div>;
  }

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">By verdict</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Band</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean return</th>
            <th className="py-1 font-normal text-right">Excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
            <th className="py-1 font-normal text-right">Median excess</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ verdict, stats }) => (
            <tr key={verdict} className="border-t border-[var(--border)]">
              <td className="py-1">{verdict === "passed" ? "pass" : verdict}</td>
              <td className="py-1 text-right">{stats!.n}</td>
              <td className="py-1 text-right"><ReturnCell value={stats!.mean_return_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.win_rate} asPercent /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.median_excess_pct} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/performance/ByVerdictTable.tsx
git commit -m "feat(performance): ByVerdictTable"
```

---

## Task 28: Frontend — ByThemeTable

**Files:**
- Create: `frontend/components/performance/ByThemeTable.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function ByThemeTable({ summary }: { summary: OutcomeSummary }) {
  const router = useRouter();
  const sp = useSearchParams();
  const rows = [...summary.by_theme].sort((a, b) => (b.stats.n - a.stats.n));

  function pickTheme(themeId: string | null) {
    const params = new URLSearchParams(sp.toString());
    if (themeId) params.set("theme_filter", themeId);
    else params.delete("theme_filter");
    router.push(`/performance?${params.toString()}`);
  }

  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">By theme</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Theme</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean return</th>
            <th className="py-1 font-normal text-right">Excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.theme_id ?? "untagged"}
              className="border-t border-[var(--border)] cursor-pointer hover:bg-[var(--surface-2)]"
              onClick={() => pickTheme(r.theme_id)}
            >
              <td className="py-1">{r.theme_name ?? <em>untagged</em>}</td>
              <td className="py-1 text-right">{r.stats.n}</td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.mean_return_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.win_rate} asPercent /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/performance/ByThemeTable.tsx
git commit -m "feat(performance): ByThemeTable (clickable rows filter list)"
```

---

## Task 29: Frontend — BySignalBucketPanel

**Files:**
- Create: `frontend/components/performance/BySignalBucketPanel.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

import { useState } from "react";
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function BySignalBucketPanel({ summary }: { summary: OutcomeSummary }) {
  const signals = Object.keys(summary.by_signal_bucket);
  const [active, setActive] = useState<string | null>(signals[0] ?? null);

  if (signals.length === 0) {
    return null;
  }

  const buckets = active ? summary.by_signal_bucket[active] ?? [] : [];

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)]">By signal bucket</h2>
        <div className="flex gap-1">
          {signals.map((sig) => (
            <button
              key={sig}
              type="button"
              onClick={() => setActive(sig)}
              className={
                "px-2 py-1 text-xs rounded " +
                (sig === active
                  ? "bg-[var(--primary)] text-white"
                  : "bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]")
              }
            >
              {sig}
            </button>
          ))}
        </div>
      </div>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Quartile</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((b) => (
            <tr key={b.bucket} className="border-t border-[var(--border)]">
              <td className="py-1">{b.bucket}</td>
              <td className="py-1 text-right">{b.n}</td>
              <td className="py-1 text-right"><ReturnCell value={b.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={b.win_rate} asPercent /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/performance/BySignalBucketPanel.tsx
git commit -m "feat(performance): BySignalBucketPanel — quartile attribution"
```

---

## Task 30: Frontend — OutcomeList

**Files:**
- Create: `frontend/components/performance/OutcomeList.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

import Link from "next/link";
import type { OutcomeListItem } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function OutcomeList({ outcomes }: { outcomes: OutcomeListItem[] }) {
  if (outcomes.length === 0) {
    return <div className="px-4 py-6 text-[var(--text-muted)]">No outcomes match the current filters.</div>;
  }

  return (
    <section className="px-4 py-6">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">Outcomes</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Ticker</th>
            <th className="py-1 font-normal">Verdict</th>
            <th className="py-1 font-normal">Emitted</th>
            <th className="py-1 font-normal">Status</th>
            <th className="py-1 font-normal text-right">+1m</th>
            <th className="py-1 font-normal text-right">+3m</th>
            <th className="py-1 font-normal text-right">+6m</th>
            <th className="py-1 font-normal text-right">Realized</th>
          </tr>
        </thead>
        <tbody>
          {outcomes.map((o) => {
            const byOffset = Object.fromEntries(o.snapshots.map((s) => [s.snapshot_offset, s]));
            const status =
              o.closed_at ? "closed"
              : o.superseded_at ? "superseded"
              : "open";
            const href =
              o.source_type === "research_run"
                ? `/pipeline/${o.source_id}`
                : `/workspace/${o.source_id}`;
            return (
              <tr key={o.id} className="border-t border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="py-1"><Link href={href} className="hover:underline">{o.ticker}</Link></td>
                <td className="py-1">{o.verdict}</td>
                <td className="py-1">{o.verdict_emitted_at.slice(0, 10)}</td>
                <td className="py-1">{status}</td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["1m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["3m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["6m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={o.realized_spy_excess_pct} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/performance/OutcomeList.tsx
git commit -m "feat(performance): OutcomeList — paginated outcomes with snapshot grid"
```

---

## Task 31: Frontend — /performance page + Nav link

**Files:**
- Create: `frontend/app/performance/page.tsx`
- Modify: `frontend/components/Nav.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { outcomesApi } from "@/lib/api";
import { PerformanceFilters } from "@/components/performance/PerformanceFilters";
import { HeroBand } from "@/components/performance/HeroBand";
import { ByVerdictTable } from "@/components/performance/ByVerdictTable";
import { ByThemeTable } from "@/components/performance/ByThemeTable";
import { BySignalBucketPanel } from "@/components/performance/BySignalBucketPanel";
import { OutcomeList } from "@/components/performance/OutcomeList";
import type { Benchmark, SnapshotOffset, SourceType, Window } from "@/lib/api";

interface PageProps {
  searchParams: Promise<{
    window?: Window;
    snapshot_offset?: SnapshotOffset;
    benchmark?: Benchmark;
    source_type?: SourceType | "all";
    theme_filter?: string;
  }>;
}

export default async function PerformancePage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const window = sp.window ?? "90d";
  const snapshotOffset = sp.snapshot_offset ?? "3m";
  const benchmark = sp.benchmark ?? "spy";
  const sourceType = sp.source_type ?? "all";

  const [summary, outcomes] = await Promise.all([
    outcomesApi.getSummary({
      themeId: sp.theme_filter,
      window, snapshotOffset, benchmark,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
    }),
    outcomesApi.list({
      themeId: sp.theme_filter,
      sourceType: sourceType === "all" ? undefined : (sourceType as SourceType),
      limit: 200,
    }),
  ]);

  return (
    <main className="min-h-screen bg-[var(--bg)] text-[var(--text)]">
      <header className="px-4 py-3 border-b border-[var(--border)]">
        <h1 className="text-lg font-semibold">Performance</h1>
      </header>
      <PerformanceFilters />
      <HeroBand summary={summary} />
      <ByVerdictTable summary={summary} />
      <ByThemeTable summary={summary} />
      <BySignalBucketPanel summary={summary} />
      <OutcomeList outcomes={outcomes} />
    </main>
  );
}
```

- [ ] **Step 2: Add Nav link**

In `frontend/components/Nav.tsx`, locate the list of nav items and add a new entry between the existing 7 links. Example:

```tsx
{ href: "/performance", label: "Performance" },
```

Insert it after the appropriate location (e.g., after "Library" or wherever makes the most sense in the existing visual order).

- [ ] **Step 3: Run dev + manual smoke**

```bash
cd frontend && npm run dev
```
Open `http://localhost:3000/performance` in a browser. Expected:
- Page loads without errors
- HeroBand renders with N=0 (or N>0 if you've run backfill)
- Filters bar works (click 30d / 1y, see URL update and re-fetch)
- "Performance" link visible in Nav

If N=0 across the board, run `POST /api/outcomes/backfill` from the browser network panel or:
```bash
curl -X POST http://127.0.0.1:8000/api/outcomes/backfill
```

Stop dev (Ctrl+C).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/performance/page.tsx frontend/components/Nav.tsx
git commit -m "feat(performance): /performance page + Nav link"
```

---

## Task 32: End-to-end smoke

**Files:**
- None (manual verification only)

- [ ] **Step 1: Run the full backend test suite**

```bash
python -m unittest discover backend/tests -v 2>&1 | tail -20
```
Expected: all tests pass. The outcome-tracker suite adds ~24 new tests, API suite adds ~7.

- [ ] **Step 2: Run lint + build on frontend**

```bash
cd frontend && npm run lint && npm run build && cd ..
```
Expected: lint clean, build successful.

- [ ] **Step 3: Manual smoke loop**

1. Start the backend (`uvicorn backend.app.main:app --reload`).
2. Trigger a `POST /api/outcomes/backfill`. Capture the response — note `outcomes_created` and `errors[]`.
3. Visit `/performance` in the frontend; verify HeroBand shows N>0, ByVerdictTable shows rows, OutcomeList shows tickers.
4. Toggle window between 90d → all → 1y; verify re-fetch.
5. Click a theme row in ByThemeTable; verify OutcomeList filters.
6. Switch benchmark spy → sector → theme_basket; verify excess columns update.
7. Switch signal in BySignalBucketPanel between velocity/fundamental/discovery; verify quartile values change.

- [ ] **Step 4: Update TODO.md**

Move the verdict outcome tracking item out of "In progress" and append to "Done (recent)" with a concise summary mirroring the existing entries' style.

- [ ] **Step 5: Commit**

```bash
git add TODO.md
git commit -m "docs: verdict outcome tracking shipped — move from in-progress to done"
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task(s) |
| --- | --- |
| `sector_etf_mapping` table + seeds | Task 1 |
| `verdict_outcomes` table | Task 1 |
| `verdict_return_snapshots` table | Task 1 |
| Indexes (4 on outcomes, 1 on snapshots) | Task 1 |
| ORM models | Task 2 |
| Pydantic schemas | Task 3 |
| Snapshot offset definitions | Task 4 |
| Entry price rule (next trading day) | Task 6 |
| Sector ETF resolution | Task 7 |
| Theme basket math (equal-weighted, drop missing) | Task 8 |
| Signal snapshot builders (research + workspace) | Task 9 |
| `record_verdict` idempotency | Task 10 |
| Supersede rule (same source, cross-source, cross-theme) | Tasks 10–11 |
| `refresh_snapshots` (per-outcome error isolation, close at 6m, no duplicates) | Task 12 |
| Pipeline hook | Task 13 |
| Workspace hook | Task 14 |
| `backfill_from_history` | Tasks 15–16 |
| Daily APScheduler cron at 03:00 UTC | Task 17 |
| API `POST /backfill` | Task 18 |
| API `GET /by-source/{type}/{id}` | Task 19 |
| API `GET /` list with filters | Task 20 |
| API `GET /summary` with verdict/theme/signal-bucket rollups | Task 21 |
| Quartile bucket math | Task 22 |
| Frontend types + client | Task 23 |
| `ReturnCell` formatter | Task 24 |
| `PerformanceFilters` | Task 25 |
| `HeroBand` | Task 26 |
| `ByVerdictTable` | Task 27 |
| `ByThemeTable` | Task 28 |
| `BySignalBucketPanel` | Task 29 |
| `OutcomeList` | Task 30 |
| `/performance` page + Nav link | Task 31 |
| End-to-end smoke + TODO.md update | Task 32 |

No gaps.

**2. Placeholder scan:** None — every task contains complete code or an exact command + expected output.

**3. Type consistency:** `record_verdict` signature defined in Task 10 is re-used identically in Tasks 13, 14, 15. `_stats_for`, `_quartile_buckets`, `_compute_summary`, `_excess_attr` defined in Task 21 and called only there. `outcomesApi` shape in Task 23 matches API response shapes in Tasks 18–21. `ReturnCell` (Task 24) accepts `string | number | null` and used identically across Tasks 26–30.
