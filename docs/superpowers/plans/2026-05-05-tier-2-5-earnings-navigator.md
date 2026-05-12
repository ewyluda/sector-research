# Tier 2.5 — Earnings Cycle Navigator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pre/post-earnings layer over every active status-board thesis. Surface consensus + signposts before the print, ingest deterministic actuals (EPS / revenue surprise + guidance direction) when FMP populates `epsActual`, and expose a Haiku "thesis-check" verdict on demand. Inline drawer on `/status` rows mirrors the read-through drawer pattern; numbers (not narrative) propagate through the existing read-through engine to peer theses.

**Architecture:** Two new tables — `earnings_prints` (per-ticker, per-fiscal-period; idempotent on `(ticker, year, quarter)`) and `thesis_print_verdicts` (per-run, per-print; CASCADE on run_id deletion). One daily APScheduler cron job at 21:00 UTC walks active board tickers, upserts print rows, and on transition-to-actual fetches the matching transcript and runs a small Haiku call for guidance direction. A second Haiku call computes the per-thesis verdict on demand. Five new endpoints under `/api/earnings/*`. One small extension to `services/read_through.py` enriches peer-event payloads with surprise numbers (originator's narrative verdict stays scoped). One symmetric-slack-window fix folded into `services/catalyst_promotion.py`. Frontend adds a third badge slot + `EarningsDrawer.tsx` to `/status` rows on the same 60s polling cadence.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + PostgreSQL + APScheduler (backend), Next.js 16 App Router + React 19 + Tailwind v4 (frontend). No backend test framework configured per CLAUDE.md — verification is a manual smoke script for backend and lint + build + Playwright walkthrough for frontend. Frontend has no markdown library installed; existing thesis text (e.g. `ThesisCard.tsx`) renders plain JSX, so this plan introduces a small safe React renderer (`SafeMarkdownBlock`) that handles the paragraphs / bullets / `**bold**` Haiku produces — no `dangerouslySetInnerHTML`, no new dependencies.

**Resolved spec open question — guidance-direction extraction:** **Use a small Haiku call** (option B in the spec). Already paying Haiku for the verdict; one extra ~200-tokens-out structured-output call per print transition is ~$0.0003. Robust against non-standard guidance phrasing. Regex would have miss rates on companies that don't say "we are raising/maintaining/lowering."

**Branch strategy:**
- **Preferred:** Branch `feat/earnings-navigator` off `main` after PR #21 (Tier 2.6 + 1.4) lands. All Tier 2.5 work imports models / hooks / services that landed in PR #21.
- **If PR #21 still open at start:** Branch `feat/earnings-navigator` off `feat/status-board-and-read-through` so you inherit `Catalyst.type='earnings'`, `read_through.py::compute_peer_events`, and the `/status` page surfaces. Plan to rebase onto `main` after PR #21 squash-merges (mirror the Tier 1.4 → Tier 2.6 rebase choreography from 2026-05-05).

Spec: `docs/superpowers/specs/2026-05-05-tier-2-5-earnings-navigator-design.md`.

---

## File structure

**Backend — create:**
- `backend/app/models/earnings_print.py` — `EarningsPrint` ORM model
- `backend/app/models/thesis_print_verdict.py` — `ThesisPrintVerdict` ORM model
- `backend/migrations/versions/<rev>_add_earnings_prints_and_verdicts.py` — Alembic migration
- `backend/app/services/earnings_prints.py` — `index_earnings_prints` + `fetch_active_board_tickers` + helpers (`_derive_fiscal_period`, `_compute_surprise`)
- `backend/app/services/earnings_brief.py` — pre-earnings Haiku brief (no persistence)
- `backend/app/services/earnings_verdict.py` — post-print verdict Haiku call (persisted) + sibling `extract_guidance_direction` Haiku call
- `backend/app/services/earnings_scheduler.py` — daily cron job (`run_daily_earnings_refresh`)
- `backend/app/api/earnings.py` — five endpoints (board, brief, verdict, prints-by-ticker, refresh)
- `backend/scripts/smoke_earnings_navigator.py` — manual smoke runner

**Backend — modify:**
- `backend/app/models/__init__.py` — register `EarningsPrint`, `ThesisPrintVerdict`
- `backend/app/main.py` — register `earnings_router`, register the scheduler job alongside the existing X-signal job
- `backend/app/services/catalyst_promotion.py` — symmetric slack window in `_try_fmp_earnings_override`
- `backend/app/services/read_through.py` — enrich peer-event payload with surprise numbers; update `summarize_read_through` system prompt with the "do not parrot" line

**Frontend — create:**
- `frontend/components/status/EarningsDrawer.tsx` — drawer rendered inline beneath a status-board row, three sub-views (`PreEarningsBlock`, `PostEarningsBlock`, `VerdictBlock`) + an inline `SafeMarkdownBlock` for Haiku output

**Frontend — modify:**
- `frontend/lib/api.ts` — add `VerdictPhase`, `Verdict`, `EarningsPrintRow`, `ThesisPrintVerdictRow`, `MatchedEarningsCatalyst`, `EarningsBoardEntry` types and `earnings` API client object
- `frontend/app/status/page.tsx` — third badge slot, third 60s polling loop, drawer mount

---

## Task 1: Add `EarningsPrint` ORM model

**Files:**
- Create: `backend/app/models/earnings_print.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the ORM model**

Create `backend/app/models/earnings_print.py`:

```python
"""EarningsPrint — one row per (ticker, fiscal_period).

Per-ticker, shared across themes. Idempotent on
(ticker, fiscal_year, fiscal_quarter): `INSERT ... ON CONFLICT DO UPDATE`
upgrades a row from "estimates only" to "estimates + actuals" when
FMP populates epsActual. Re-runs of the daily scheduler are safe.

For non-calendar-year reporters where FMP doesn't expose fiscal periods
reliably, fiscal_year/quarter are derived from earnings_date (calendar).
The unique constraint is on the inferred values, not on a pristine
fiscal mapping.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class EarningsPrint(Base):
    __tablename__ = "earnings_prints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)

    eps_estimated: Mapped[float | None] = mapped_column(Float)
    eps_actual: Mapped[float | None] = mapped_column(Float)
    revenue_estimated: Mapped[float | None] = mapped_column(Float)
    revenue_actual: Mapped[float | None] = mapped_column(Float)

    # Computed at write-time, nullable when actual is missing.
    eps_surprise_pct: Mapped[float | None] = mapped_column(Float)
    revenue_surprise_pct: Mapped[float | None] = mapped_column(Float)

    # Best-effort from transcript scrape; null when undetermined.
    # Allowed values: "raised" | "maintained" | "lowered" | "n/a"
    guidance_direction: Mapped[str | None] = mapped_column(String(20))

    # Pointer to the transcript that informed guidance/verdict.
    transcript_year: Mapped[int | None] = mapped_column(Integer)
    transcript_quarter: Mapped[int | None] = mapped_column(Integer)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "fiscal_year",
            "fiscal_quarter",
            name="uq_earnings_prints_period",
        ),
        Index("ix_earnings_prints_ticker_date", "ticker", "earnings_date"),
    )
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`, add the import alongside the others (file pattern is one import per model, plus an `__all__` entry):

```python
from backend.app.models.earnings_print import EarningsPrint  # noqa: F401
```

Append `"EarningsPrint"` to the `__all__` list if the file maintains one.

- [ ] **Step 3: Verify imports compile**

Run: `source backend/venv/bin/activate && python -c "from backend.app.models import EarningsPrint; print(EarningsPrint.__tablename__)"`
Expected: `earnings_prints`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/earnings_print.py backend/app/models/__init__.py
git commit -m "feat(earnings): add EarningsPrint ORM model"
```

---

## Task 2: Add `ThesisPrintVerdict` ORM model

**Files:**
- Create: `backend/app/models/thesis_print_verdict.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the ORM model**

Create `backend/app/models/thesis_print_verdict.py`:

```python
"""ThesisPrintVerdict — per-run, per-print Haiku verdict.

One row per (run_id, earnings_print_id). Lazy — written only when the
user clicks "Run thesis-check." Idempotent on (run_id, earnings_print_id):
re-clicking overwrites with a fresh Haiku call.

CASCADE on run_id: re-running the thesis orphans old verdicts. The
status board picks the latest run per (ticker, theme), so users
naturally see "no verdict yet" on a fresh run with prior prints,
prompting a re-trigger.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ThesisPrintVerdict(Base):
    __tablename__ = "thesis_print_verdicts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    earnings_print_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("earnings_prints.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Allowed values: "confirms" | "threatens" | "neutral" | "insufficient"
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    pillars_addressed: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "earnings_print_id",
            name="uq_thesis_print_verdicts_run_print",
        ),
        Index("ix_thesis_print_verdicts_run_id", "run_id"),
    )
```

- [ ] **Step 2: Register the model**

In `backend/app/models/__init__.py`:

```python
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict  # noqa: F401
```

Append `"ThesisPrintVerdict"` to `__all__` if maintained.

- [ ] **Step 3: Verify imports compile**

Run: `source backend/venv/bin/activate && python -c "from backend.app.models import ThesisPrintVerdict; print(ThesisPrintVerdict.__tablename__)"`
Expected: `thesis_print_verdicts`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/thesis_print_verdict.py backend/app/models/__init__.py
git commit -m "feat(earnings): add ThesisPrintVerdict ORM model"
```

---

## Task 3: Alembic migration

**Files:**
- Create: `backend/migrations/versions/<auto>_add_earnings_prints_and_verdicts.py`

- [ ] **Step 1: Generate the migration**

Run:
```bash
cd backend && PYTHONPATH=.. alembic revision --autogenerate -m "add earnings_prints and verdicts" && cd ..
```

Expected: a new file appears in `backend/migrations/versions/` whose `down_revision` is the head of the chain at the time of branch creation (most likely the read-through migration if branched off `feat/status-board-and-read-through`, or the kill-criterion-states migration if branched cleanly off `main` post-PR-21).

- [ ] **Step 2: Inspect and tighten the generated migration**

Open the new file. The autogenerate diff should produce two `op.create_table` blocks. Review for:

For `earnings_prints`:
- `id` (UUID primary key)
- `ticker` (VARCHAR(16), not null)
- `fiscal_year`, `fiscal_quarter` (INTEGER, not null)
- `earnings_date` (DATE, not null)
- `eps_estimated`, `eps_actual`, `revenue_estimated`, `revenue_actual`, `eps_surprise_pct`, `revenue_surprise_pct` (all FLOAT, nullable)
- `guidance_direction` (VARCHAR(20), nullable)
- `transcript_year`, `transcript_quarter` (INTEGER, nullable)
- `ingested_at` (TIMESTAMP WITH TIME ZONE, not null)
- `UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", name="uq_earnings_prints_period")`
- `Index("ix_earnings_prints_ticker_date", "ticker", "earnings_date")`

For `thesis_print_verdicts`:
- `id` (UUID primary key)
- `run_id` (UUID, FK to `research_runs.id`, ondelete='CASCADE', not null)
- `earnings_print_id` (UUID, FK to `earnings_prints.id`, ondelete='CASCADE', not null)
- `verdict` (VARCHAR(20), not null)
- `summary_md` (TEXT, not null)
- `pillars_addressed` (JSONB, not null, server_default='[]')
- `generated_at` (TIMESTAMP WITH TIME ZONE, not null)
- `UniqueConstraint("run_id", "earnings_print_id", name="uq_thesis_print_verdicts_run_print")`
- `Index("ix_thesis_print_verdicts_run_id", "run_id")`

The autogenerate output sometimes:
- Misses `server_default="[]"` on the JSONB column → add it manually.
- Generates the FK without `ondelete="CASCADE"` → add it manually.
- Reorders columns in alphabetical, not declared, order → harmless.

Hand-write the `downgrade()` to fully reverse (drop verdicts first, then prints — verdicts FK → prints):

```python
def downgrade() -> None:
    op.drop_index("ix_thesis_print_verdicts_run_id", table_name="thesis_print_verdicts")
    op.drop_constraint("uq_thesis_print_verdicts_run_print", "thesis_print_verdicts", type_="unique")
    op.drop_table("thesis_print_verdicts")
    op.drop_index("ix_earnings_prints_ticker_date", table_name="earnings_prints")
    op.drop_constraint("uq_earnings_prints_period", "earnings_prints", type_="unique")
    op.drop_table("earnings_prints")
```

This matches the discipline established in Tier 2.6's migration (hand-written downgrade fully reverses the upgrade).

- [ ] **Step 3: Apply the migration**

Run: `cd backend && PYTHONPATH=.. alembic upgrade head && cd ..`
Expected: `Running upgrade <prev_rev> -> <new_rev>, add earnings_prints and verdicts`

- [ ] **Step 4: Verify the tables exist**

Run:
```bash
psql "$(python -c "from backend.app.config import get_settings; print(get_settings().database_url_sync)")" -c "\d earnings_prints"
psql "$(python -c "from backend.app.config import get_settings; print(get_settings().database_url_sync)")" -c "\d thesis_print_verdicts"
```

Expected: both tables exist with the columns, FKs, unique constraints, and indexes listed in step 2.

- [ ] **Step 5: Verify the downgrade reverses cleanly**

Run:
```bash
cd backend && PYTHONPATH=.. alembic downgrade -1 && cd ..
psql "$(python -c "from backend.app.config import get_settings; print(get_settings().database_url_sync)")" -c "\dt earnings_prints thesis_print_verdicts"
```
Expected: `Did not find any relation named "earnings_prints"` and `..."thesis_print_verdicts"`. Then re-apply: `cd backend && PYTHONPATH=.. alembic upgrade head && cd ..`.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*_add_earnings_prints_and_verdicts.py
git commit -m "feat(earnings): alembic migration for earnings_prints and thesis_print_verdicts"
```

---

## Task 4: Slack-window symmetry fix in `catalyst_promotion.py`

This is a small, isolated, drop-in fix. Land it early so it gets exercise in any thesis runs you happen to kick off during the rest of the work.

**Files:**
- Modify: `backend/app/services/catalyst_promotion.py:78-83`

- [ ] **Step 1: Apply the symmetric slack**

In `backend/app/services/catalyst_promotion.py`, locate the block in `_try_fmp_earnings_override`:

```python
    if parsed.window_start and parsed.window_end:
        lower = max(parsed.window_start, today)
        upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
    else:
        lower = today
        upper = today + timedelta(days=365)
```

Change to:

```python
    if parsed.window_start and parsed.window_end:
        lower = max(parsed.window_start - timedelta(days=_FMP_EARNINGS_SLACK_DAYS), today)
        upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
    else:
        lower = today
        upper = today + timedelta(days=365)
```

Update the slack-constant docstring at line ~24 from:

```python
# Slack window for matching FMP earnings dates against parsed timeframes.
# A "Q2 2026" parsed window ends Jun 30, but the actual earnings print may
# fall a few weeks later (mid-July). Allow this much buffer past window_end.
_FMP_EARNINGS_SLACK_DAYS = 30
```

to:

```python
# Slack window for matching FMP earnings dates against parsed timeframes.
# A "Q2 2026" parsed window is Apr 1 – Jun 30, but actual earnings prints
# routinely fall mid-July (post window_end) and pre-announcements can hit
# late March (pre window_start). Symmetric slack on both sides catches both.
_FMP_EARNINGS_SLACK_DAYS = 30
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `source backend/venv/bin/activate && python -c "from backend.app.services.catalyst_promotion import _try_fmp_earnings_override; print(_try_fmp_earnings_override.__doc__[:60])"`
Expected: docstring prints; no import errors.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/catalyst_promotion.py
git commit -m "fix(catalysts): symmetric slack window in FMP earnings override"
```

---

## Task 5: `services/earnings_prints.py` — indexer + active-tickers helper

**Files:**
- Create: `backend/app/services/earnings_prints.py`

- [ ] **Step 1: Create the service module**

Create `backend/app/services/earnings_prints.py`:

```python
"""Earnings prints indexer.

Walks active status-board tickers, pulls FMP earnings calendar, and
upserts EarningsPrint rows. Idempotent on (ticker, fiscal_year,
fiscal_quarter); newly-populated `epsActual` upgrades a row from
"estimates only" to "estimates + actuals."

This service does NOT fetch transcripts or compute guidance direction —
that's the scheduler's job (see services/earnings_scheduler.py).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.earnings_print import EarningsPrint

logger = logging.getLogger(__name__)


def _derive_fiscal_period(earnings_date: date) -> tuple[int, int]:
    """Best-effort fiscal year/quarter from a calendar earnings date.

    For non-calendar-year reporters, this is approximate — the unique
    constraint is on the inferred values, not on a pristine fiscal
    mapping. If FMP later exposes fiscal_year/fiscal_quarter in the
    earnings calendar response (it currently does not in /stable/earnings),
    swap this for the explicit values.
    """
    quarter = (earnings_date.month - 1) // 3 + 1
    return earnings_date.year, quarter


def _compute_surprise(estimated: float | None, actual: float | None) -> float | None:
    """(actual - estimated) / |estimated|. None when either side is None
    or estimated is zero."""
    if estimated is None or actual is None:
        return None
    if estimated == 0:
        return None
    return (actual - estimated) / abs(estimated)


async def fetch_active_board_tickers(db: AsyncSession) -> list[str]:
    """Distinct uppercased tickers from the latest non-archived completed
    run per (ticker, theme). Mirrors the DISTINCT ON query in
    services/status_board.py to keep the universe identical."""
    sql = text(
        """
        SELECT DISTINCT ticker
        FROM (
            SELECT DISTINCT ON (ticker, theme_id) ticker
            FROM research_runs
            WHERE status = 'completed' AND archived_at IS NULL
            ORDER BY ticker, theme_id, updated_at DESC
        ) t
        """
    )
    rows = (await db.execute(sql)).all()
    return [r[0].upper() for r in rows]


async def index_earnings_prints(
    ticker: str,
    fmp: FMPClient,
    db: AsyncSession,
) -> list[EarningsPrint]:
    """Pull FMP earnings calendar for a ticker, upsert prints. Returns
    the affected ORM rows after refresh.

    FMP /stable/earnings shape per row:
        {symbol, date: 'YYYY-MM-DD', epsActual, epsEstimated,
         revenueActual, revenueEstimated, lastUpdated}

    epsActual is null for upcoming prints, populated post-print.
    The upsert deliberately does NOT clobber guidance_direction,
    transcript_year, transcript_quarter — those are populated by the
    scheduler's transcript pass and survive subsequent calendar refreshes.
    """
    try:
        rows, _ = await fmp.get_earnings_calendar(ticker, limit=4)
    except Exception as e:
        logger.warning("[%s] FMP earnings calendar fetch failed: %s", ticker, e)
        return []

    if not rows:
        return []

    affected: list[EarningsPrint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_str = row.get("date")
        if not date_str:
            continue
        try:
            earnings_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        fy, fq = _derive_fiscal_period(earnings_date)

        eps_est = row.get("epsEstimated")
        eps_act = row.get("epsActual")
        rev_est = row.get("revenueEstimated")
        rev_act = row.get("revenueActual")

        values = dict(
            ticker=ticker.upper(),
            fiscal_year=fy,
            fiscal_quarter=fq,
            earnings_date=earnings_date,
            eps_estimated=eps_est,
            eps_actual=eps_act,
            revenue_estimated=rev_est,
            revenue_actual=rev_act,
            eps_surprise_pct=_compute_surprise(eps_est, eps_act),
            revenue_surprise_pct=_compute_surprise(rev_est, rev_act),
            ingested_at=datetime.now(timezone.utc),
        )

        stmt = pg_insert(EarningsPrint).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_earnings_prints_period",
            set_={
                "earnings_date": stmt.excluded.earnings_date,
                "eps_estimated": stmt.excluded.eps_estimated,
                "eps_actual": stmt.excluded.eps_actual,
                "revenue_estimated": stmt.excluded.revenue_estimated,
                "revenue_actual": stmt.excluded.revenue_actual,
                "eps_surprise_pct": stmt.excluded.eps_surprise_pct,
                "revenue_surprise_pct": stmt.excluded.revenue_surprise_pct,
                "ingested_at": stmt.excluded.ingested_at,
            },
        ).returning(EarningsPrint.id)
        result = await db.execute(stmt)
        row_id = result.scalar_one()
        loaded = await db.get(EarningsPrint, row_id)
        if loaded is not None:
            affected.append(loaded)

    return affected
```

- [ ] **Step 2: Smoke-check the indexer**

Run:
```bash
source backend/venv/bin/activate
PYTHONPATH=. python -c "
import asyncio
from backend.app.db import async_session
from backend.app.clients.fmp import FMPClient
from backend.app.services.earnings_prints import index_earnings_prints, fetch_active_board_tickers

async def main():
    async with async_session() as db:
        tickers = await fetch_active_board_tickers(db)
        print(f'active board tickers: {tickers[:5]}... ({len(tickers)} total)')
    fmp = FMPClient()
    try:
        async with async_session() as db:
            rows = await index_earnings_prints('AAPL', fmp, db)
            await db.commit()
            print(f'AAPL prints upserted: {len(rows)}')
            for r in rows:
                print(f'  {r.fiscal_year}Q{r.fiscal_quarter} {r.earnings_date} eps_est={r.eps_estimated} eps_act={r.eps_actual}')
    finally:
        await fmp.close()

asyncio.run(main())
"
```

Expected: prints non-empty list of active board tickers, then 1-4 AAPL print rows (calendar quarters within FMP's window). At least one row should have non-null `eps_estimated`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/earnings_prints.py
git commit -m "feat(earnings): indexer service for earnings_prints (FMP calendar upsert)"
```

---

## Task 6: `services/earnings_brief.py` — pre-earnings Haiku brief

**Files:**
- Create: `backend/app/services/earnings_brief.py`

- [ ] **Step 1: Define the Pydantic output schema and prompt**

Create `backend/app/services/earnings_brief.py`:

```python
"""Pre-earnings brief — lazy Haiku synthesis of "what to watch."

Distills thesis pillars + signposts + consensus into 3-5 bullets of what
would confirm vs threaten the thesis if the print delivers/misses.
Not persisted — re-rendered on demand.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import HAIKU, complete
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun

logger = logging.getLogger(__name__)


class BriefOutput(BaseModel):
    summary_md: str = Field(..., description="3-5 markdown bullets")
    pillars_addressed: list[str] = Field(default_factory=list)


EARNINGS_BRIEF_SYSTEM = """You are an equity analyst preparing a pre-earnings checklist for a specific investment thesis.

Inputs you will receive:
- thesis_summary: the high-level thesis statement
- thesis_pillars: the 3-5 named pillars the thesis depends on
- signposts: verbatim signposts from the thesis catalyst, if any
- consensus: analyst-expected EPS and revenue for the upcoming quarter
- recent_trend: last 4 quarters of beat/miss/inline outcomes

Task: produce a 3-5 bullet markdown checklist of what to watch in the
upcoming print. Each bullet should:
- Start with a metric or signpost name (e.g., "**Cloud revenue YoY:**").
- State what would confirm vs threaten the thesis at that line item.
- Be specific (e.g., "above 25% YoY" rather than "strong growth").

Constraints:
- Reason about the print itself only — no broader macro, no buy/sell.
- Do not invent numbers the consensus did not provide.
- If the thesis has fewer than 3 testable pillars, produce 3 bullets and
  note where you had to broaden the question.

Return strict JSON matching the schema. The "pillars_addressed" field
must be a subset of the input thesis_pillars names."""
```

- [ ] **Step 2: Implement `_extract_thesis` helper and `compute_brief`**

Append to `backend/app/services/earnings_brief.py`:

```python
def _extract_thesis(run: ResearchRun) -> tuple[str | None, list[str]]:
    """Pull (thesis_summary, thesis_pillars[]) from persisted run state.
    Mirrors the helper in read_through.py but additionally extracts pillars."""
    if not isinstance(run.state, dict):
        return None, []
    phase_outputs = run.state.get("phase_outputs") or {}
    thesis = phase_outputs.get("thesis") or {}
    structured = thesis.get("structured") if isinstance(thesis, dict) else None
    if not isinstance(structured, dict):
        return None, []
    summary = structured.get("thesis_summary")
    pillars_raw = structured.get("thesis_pillars") or structured.get("pillars") or []
    pillars: list[str] = []
    if isinstance(pillars_raw, list):
        for p in pillars_raw:
            if isinstance(p, str):
                pillars.append(p)
            elif isinstance(p, dict) and isinstance(p.get("name"), str):
                pillars.append(p["name"])
    return summary, pillars


async def compute_brief(
    run_id: str,
    earnings_print_id: str,
    db: AsyncSession,
) -> BriefOutput:
    """Lazy Haiku call. Raises ValueError if thesis_summary is missing
    or run/print rows are not found."""
    run = await db.get(ResearchRun, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    print_row = await db.get(EarningsPrint, earnings_print_id)
    if print_row is None:
        raise ValueError(f"earnings print not found: {earnings_print_id}")

    thesis_summary, thesis_pillars = _extract_thesis(run)
    if not thesis_summary:
        raise ValueError(f"no thesis_summary in run state: {run_id}")

    cat_q = (
        select(Catalyst)
        .where(Catalyst.run_id == run_id)
        .where(Catalyst.type == "earnings")
        .order_by(Catalyst.ordinal)
    )
    cat_rows = (await db.execute(cat_q)).scalars().all()
    signposts: list[str] = []
    for c in cat_rows:
        if isinstance(c.signposts, list):
            signposts.extend(s for s in c.signposts if isinstance(s, str))

    user_payload: dict[str, Any] = {
        "thesis_summary": thesis_summary,
        "thesis_pillars": thesis_pillars,
        "signposts": signposts[:10],
        "consensus": {
            "eps_estimated": print_row.eps_estimated,
            "revenue_estimated": print_row.revenue_estimated,
            "earnings_date": print_row.earnings_date.isoformat(),
            "fiscal_year": print_row.fiscal_year,
            "fiscal_quarter": print_row.fiscal_quarter,
        },
    }

    raw = await complete(
        model=HAIKU,
        system=EARNINGS_BRIEF_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(user_payload, indent=2)}],
        assistant_prefill='{"summary_md":',
        max_tokens=800,
    )
    full_json = '{"summary_md":' + raw
    try:
        parsed = BriefOutput.model_validate_json(full_json)
    except Exception as e:
        logger.exception("BriefOutput parse failed: raw=%s", raw[:300])
        raise ValueError(f"brief parse failed: {e}") from e
    return parsed
```

- [ ] **Step 3: Verify imports compile**

Run: `source backend/venv/bin/activate && python -c "from backend.app.services.earnings_brief import compute_brief, BriefOutput; print(BriefOutput.model_json_schema()['properties'].keys())"`
Expected: `dict_keys(['summary_md', 'pillars_addressed'])`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/earnings_brief.py
git commit -m "feat(earnings): pre-earnings brief Haiku synthesis service"
```

---

## Task 7: `services/earnings_verdict.py` — post-print verdict + guidance extraction

**Files:**
- Create: `backend/app/services/earnings_verdict.py`

- [ ] **Step 1: Create module skeleton with prompts and schemas**

Create `backend/app/services/earnings_verdict.py`:

```python
"""Post-print thesis verdict — Haiku call against the print's actuals.

Produces a structured `VerdictOutput` ({verdict, summary_md,
pillars_addressed}) per (run_id, earnings_print_id) and persists it.
Idempotent on the unique constraint — re-clicking overwrites with a
fresh call.

Sibling helper `extract_guidance_direction` runs as part of the daily
scheduler when a transcript first becomes available. Separate Haiku call
so the deterministic post-print row (with guidance populated) lands
without waiting on a per-thesis verdict.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.graph.llm import HAIKU, complete
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.services.earnings_brief import _extract_thesis

logger = logging.getLogger(__name__)

VerdictLiteral = Literal["confirms", "threatens", "neutral", "insufficient"]
GuidanceLiteral = Literal["raised", "maintained", "lowered", "n/a"]


class VerdictOutput(BaseModel):
    verdict: VerdictLiteral
    summary_md: str = Field(..., description="3-5 sentences")
    pillars_addressed: list[str] = Field(default_factory=list)


class GuidanceOutput(BaseModel):
    guidance_direction: GuidanceLiteral
    rationale: str = Field(..., description="One sentence.")


EARNINGS_VERDICT_SYSTEM = """You are an equity analyst evaluating whether an earnings print confirms or threatens an investment thesis.

Inputs you will receive:
- thesis_summary: the high-level thesis statement
- thesis_pillars: the named pillars the thesis depends on
- signposts: verbatim signposts from the thesis catalyst, if any
- actuals: EPS surprise %, revenue surprise %, guidance direction, fiscal period
- transcript_excerpt: optional management commentary, capped ~6K chars

Task: emit a verdict — one of:
- "confirms": the print provides direct evidence supporting one or more
  pillars (a beat alone is not enough; the print must speak to thesis logic).
- "threatens": the print provides direct evidence against one or more
  pillars (a miss alone is not enough; the management commentary or
  guidance must reframe the pillar negatively).
- "neutral": the print spoke to thesis pillars but doesn't move them
  meaningfully in either direction.
- "insufficient": the print is silent on thesis pillars — beat/miss numbers
  alone, no qualitative signal. LEAN HEAVILY toward this verdict when in
  doubt; do not infer from sentiment.

Output:
- verdict: one of the four literals above.
- summary_md: 3-5 sentences explaining the verdict, citing specific
  numbers or transcript phrases. Markdown allowed (paragraphs, bullets,
  bold). Keep it scannable.
- pillars_addressed: subset of input thesis_pillars names that the print
  spoke to (empty list if verdict='insufficient').

Return strict JSON matching the schema. Do NOT recommend buy/sell. Do
NOT speculate beyond the evidence provided."""


GUIDANCE_EXTRACTION_SYSTEM = """You are reading the management commentary section of an earnings call transcript. Your only job is to determine forward guidance direction.

Output one of:
- "raised": management increased forward guidance vs. prior outlook.
- "maintained": management reiterated prior guidance unchanged.
- "lowered": management decreased forward guidance vs. prior outlook.
- "n/a": no forward guidance was given on this call (or company does
  not provide guidance).

If the transcript explicitly references prior guidance and the relationship
to it, use that. If the transcript provides numerical ranges without
explicit comparison to prior, mark "n/a" (you do not have prior guidance
to compare against). Do not infer "raised" from optimistic sentiment alone.

Return strict JSON: {"guidance_direction": "...", "rationale": "..."}.
Rationale is one sentence quoting or paraphrasing the relevant transcript
language."""
```

- [ ] **Step 2: Implement `extract_guidance_direction`**

Append to `backend/app/services/earnings_verdict.py`:

```python
async def extract_guidance_direction(
    transcript_text: str,
) -> GuidanceOutput | None:
    """Single Haiku call against a (capped) management commentary excerpt.
    Returns None on parse failure or empty input — caller decides how to
    handle (typically: leave guidance_direction null on the print row)."""
    if not transcript_text or len(transcript_text.strip()) < 200:
        return None

    excerpt = transcript_text[:6000]
    raw = await complete(
        model=HAIKU,
        system=GUIDANCE_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": excerpt}],
        assistant_prefill='{"guidance_direction":',
        max_tokens=200,
    )
    full_json = '{"guidance_direction":' + raw
    try:
        return GuidanceOutput.model_validate_json(full_json)
    except Exception:
        logger.exception("GuidanceOutput parse failed: raw=%s", raw[:200])
        return None
```

- [ ] **Step 3: Implement `compute_verdict`**

Append to `backend/app/services/earnings_verdict.py`:

```python
async def compute_verdict(
    run_id: str,
    earnings_print_id: str,
    fmp: FMPClient,
    db: AsyncSession,
) -> ThesisPrintVerdict:
    """Run Haiku verdict + persist via INSERT ... ON CONFLICT DO UPDATE.
    Caller owns the transaction (commit not called here)."""
    run = await db.get(ResearchRun, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    print_row = await db.get(EarningsPrint, earnings_print_id)
    if print_row is None:
        raise ValueError(f"earnings print not found: {earnings_print_id}")

    thesis_summary, thesis_pillars = _extract_thesis(run)
    if not thesis_summary:
        raise ValueError(f"no thesis_summary in run state: {run_id}")

    cat_q = (
        select(Catalyst)
        .where(Catalyst.run_id == run_id)
        .where(Catalyst.type == "earnings")
        .order_by(Catalyst.ordinal)
    )
    cat_rows = (await db.execute(cat_q)).scalars().all()
    signposts: list[str] = []
    for c in cat_rows:
        if isinstance(c.signposts, list):
            signposts.extend(s for s in c.signposts if isinstance(s, str))

    transcript_excerpt: str | None = None
    if print_row.transcript_year and print_row.transcript_quarter:
        try:
            data, _ = await fmp.get_earnings_transcript(
                print_row.ticker,
                year=print_row.transcript_year,
                quarter=print_row.transcript_quarter,
            )
            if isinstance(data, list) and data and isinstance(data[0], dict):
                transcript_excerpt = (data[0].get("content") or "")[:6000]
        except Exception as e:
            logger.warning(
                "[%s] verdict transcript fetch failed: %s",
                print_row.ticker, e,
            )

    user_payload: dict[str, Any] = {
        "thesis_summary": thesis_summary,
        "thesis_pillars": thesis_pillars,
        "signposts": signposts[:10],
        "actuals": {
            "fiscal_year": print_row.fiscal_year,
            "fiscal_quarter": print_row.fiscal_quarter,
            "eps_surprise_pct": print_row.eps_surprise_pct,
            "revenue_surprise_pct": print_row.revenue_surprise_pct,
            "guidance_direction": print_row.guidance_direction,
        },
        "transcript_excerpt": transcript_excerpt,
    }

    raw = await complete(
        model=HAIKU,
        system=EARNINGS_VERDICT_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(user_payload, indent=2)}],
        assistant_prefill='{"verdict":',
        max_tokens=900,
    )
    full_json = '{"verdict":' + raw
    try:
        parsed = VerdictOutput.model_validate_json(full_json)
    except Exception as e:
        logger.exception("VerdictOutput parse failed: raw=%s", raw[:300])
        raise ValueError(f"verdict parse failed: {e}") from e

    stmt = pg_insert(ThesisPrintVerdict).values(
        run_id=run_id,
        earnings_print_id=earnings_print_id,
        verdict=parsed.verdict,
        summary_md=parsed.summary_md,
        pillars_addressed=parsed.pillars_addressed,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_thesis_print_verdicts_run_print",
        set_={
            "verdict": stmt.excluded.verdict,
            "summary_md": stmt.excluded.summary_md,
            "pillars_addressed": stmt.excluded.pillars_addressed,
            "generated_at": stmt.excluded.generated_at,
        },
    ).returning(ThesisPrintVerdict.id)
    row_id = (await db.execute(stmt)).scalar_one()
    loaded = await db.get(ThesisPrintVerdict, row_id)
    assert loaded is not None  # ON CONFLICT guarantees a row exists
    return loaded
```

- [ ] **Step 4: Verify imports compile**

Run: `source backend/venv/bin/activate && python -c "from backend.app.services.earnings_verdict import compute_verdict, extract_guidance_direction, VerdictOutput, GuidanceOutput; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/earnings_verdict.py
git commit -m "feat(earnings): post-print verdict + guidance extraction services"
```

---

## Task 8: `services/earnings_scheduler.py` + register cron job

**Files:**
- Create: `backend/app/services/earnings_scheduler.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the scheduler module**

Create `backend/app/services/earnings_scheduler.py`:

```python
"""Daily earnings prints refresh — APScheduler cron job.

Runs once per weekday at 21:00 UTC (5 PM ET). For each active board ticker:
1. Upsert earnings_prints rows from FMP calendar (idempotent).
2. For any newly-populated print (transition from eps_actual NULL to
   non-NULL), best-effort fetch the matching transcript and run a small
   Haiku call to extract guidance_direction; write back to the print row.

Transcript fetch failures are non-fatal: print row keeps
guidance_direction null. Re-running the scheduler retries.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.earnings_print import EarningsPrint
from backend.app.services.earnings_prints import (
    fetch_active_board_tickers,
    index_earnings_prints,
)
from backend.app.services.earnings_verdict import extract_guidance_direction

logger = logging.getLogger(__name__)

INTER_TICKER_SLEEP = 1.0  # seconds; FMP TTL caching makes this gentle


async def _enrich_one_print_with_guidance(
    print_row: EarningsPrint,
    fmp: FMPClient,
    db: AsyncSession,
) -> bool:
    """Fetch transcript for (ticker, fiscal_year, fiscal_quarter), run
    guidance extraction, write back. Returns True if guidance_direction
    was newly populated."""
    if print_row.guidance_direction is not None:
        return False  # already enriched
    if print_row.eps_actual is None:
        return False  # not post-print yet

    try:
        data, _ = await fmp.get_earnings_transcript(
            print_row.ticker,
            year=print_row.fiscal_year,
            quarter=print_row.fiscal_quarter,
        )
    except Exception as e:
        logger.warning(
            "[%s] transcript fetch failed (%dQ%d): %s",
            print_row.ticker, print_row.fiscal_year, print_row.fiscal_quarter, e,
        )
        return False

    if not isinstance(data, list) or not data:
        return False
    first = data[0] if isinstance(data[0], dict) else None
    if first is None:
        return False
    content = first.get("content") or ""
    if not content:
        return False

    guidance = await extract_guidance_direction(content)
    if guidance is None:
        return False

    fresh = await db.get(EarningsPrint, print_row.id)
    if fresh is None:
        return False
    fresh.guidance_direction = guidance.guidance_direction
    fresh.transcript_year = print_row.fiscal_year
    fresh.transcript_quarter = print_row.fiscal_quarter
    return True


async def run_daily_earnings_refresh() -> dict:
    """Top-level entry point invoked by the cron trigger. Returns a
    summary dict for logging."""
    fmp = FMPClient()
    started = datetime.now(timezone.utc)
    summary: dict = {
        "tickers_processed": 0,
        "prints_upserted": 0,
        "guidance_enriched": 0,
        "errors": [],
    }
    try:
        async with async_session() as db:
            tickers = await fetch_active_board_tickers(db)

        for ticker in tickers:
            try:
                async with async_session() as db:
                    rows = await index_earnings_prints(ticker, fmp, db)
                    summary["prints_upserted"] += len(rows)
                    enriched = 0
                    for r in rows:
                        if await _enrich_one_print_with_guidance(r, fmp, db):
                            enriched += 1
                    summary["guidance_enriched"] += enriched
                    await db.commit()
                summary["tickers_processed"] += 1
            except Exception as e:
                logger.exception("[%s] earnings refresh failed", ticker)
                summary["errors"].append({"ticker": ticker, "error": str(e)})
            await asyncio.sleep(INTER_TICKER_SLEEP)
    finally:
        await fmp.close()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info(
        "earnings refresh complete: %s tickers, %s prints, %s guidance, %s errors, %.1fs",
        summary["tickers_processed"],
        summary["prints_upserted"],
        summary["guidance_enriched"],
        len(summary["errors"]),
        elapsed,
    )
    return summary
```

- [ ] **Step 2: Register the cron job in `main.py`**

In `backend/app/main.py`, locate the existing scheduler registration block (~lines 56-66):

```python
    # Daily signal scheduler — 2 AM local time
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _daily_refresh_job,
        trigger=CronTrigger(hour=2, minute=0),
        args=[app],
        id="daily_signal_refresh",
        name="Daily X Signal Refresh",
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Signal scheduler started (daily @ 02:00)")
```

Add a second `add_job` call BEFORE `scheduler.start()`:

```python
    scheduler.add_job(
        _daily_earnings_refresh_job,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app],
        id="daily_earnings_refresh",
        name="Daily Earnings Prints Refresh",
        replace_existing=True,
    )
```

Update the log line:

```python
    logger.info("Schedulers started: X signals @ 02:00 UTC, earnings @ 21:00 UTC")
```

Then add the wrapper function near the existing `_daily_refresh_job` definition (~lines 80-90):

```python
async def _daily_earnings_refresh_job(app: FastAPI) -> None:
    """APScheduler entry point — wraps run_daily_earnings_refresh with logging."""
    from backend.app.services.earnings_scheduler import run_daily_earnings_refresh
    try:
        summary = await run_daily_earnings_refresh()
        logger.info("Daily earnings refresh: %s", summary)
    except Exception:
        logger.exception("Daily earnings refresh crashed")
```

- [ ] **Step 3: Verify imports compile + scheduler can be invoked manually**

Run:
```bash
source backend/venv/bin/activate
PYTHONPATH=. python -c "
import asyncio
from backend.app.services.earnings_scheduler import run_daily_earnings_refresh
print(asyncio.run(run_daily_earnings_refresh()))
"
```

Expected: dict with `{tickers_processed: <N>, prints_upserted: <M>, guidance_enriched: <K>, errors: [...]}`. N matches the number of distinct active board tickers; M ≥ N (each ticker typically has 1-4 print rows after upsert). K is small in steady state — only newly-transitioned-to-actual prints enrich.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/earnings_scheduler.py backend/app/main.py
git commit -m "feat(earnings): daily APScheduler cron for earnings prints + guidance extraction"
```

---

## Task 9: Read-through enrichment — surprise numbers + summary prompt update

**Files:**
- Modify: `backend/app/services/read_through.py`

- [ ] **Step 1: Enrich peer-event payload with surprise numbers**

In `backend/app/services/read_through.py`, find the earnings-event branch of `compute_peer_events` where each `Catalyst` row is converted to a `PeerEvent`. Today the payload includes `description / type / timeframe / expected_date`. Extend the function to JOIN against `earnings_prints` and merge surprise fields when a matching row exists (matching = same ticker + earnings_date within ±7 days of `expected_window_start`).

Add this helper near the other helpers in `read_through.py`:

```python
async def _print_payload_for_peer(
    db: AsyncSession,
    peer_ticker: str,
    expected_window_start: date,
) -> dict[str, Any]:
    """Look up an EarningsPrint row whose earnings_date is within ±7 days
    of the catalyst's expected_window_start. Returns surprise numbers +
    guidance direction when actuals are present; empty dict otherwise.

    Per Tier 2.5 spec Q5-B: peer drawers see numbers, never the
    originator's narrative verdict."""
    from backend.app.models.earnings_print import EarningsPrint
    from sqlalchemy import and_

    lo = expected_window_start - timedelta(days=7)
    hi = expected_window_start + timedelta(days=7)
    q = (
        select(EarningsPrint)
        .where(EarningsPrint.ticker == peer_ticker.upper())
        .where(and_(EarningsPrint.earnings_date >= lo, EarningsPrint.earnings_date <= hi))
        .order_by(EarningsPrint.earnings_date.desc())
        .limit(1)
    )
    row = (await db.execute(q)).scalar_one_or_none()
    if row is None:
        return {}
    if row.eps_actual is None:
        # pre-print: estimates exist but no actuals yet; expose nothing
        return {}
    return {
        "eps_surprise_pct": row.eps_surprise_pct,
        "revenue_surprise_pct": row.revenue_surprise_pct,
        "guidance_direction": row.guidance_direction,
    }
```

In the earnings-event loop inside `compute_peer_events`, replace:

```python
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
```

with:

```python
    for c in cat_rows:
        if not c.expected_window_start:
            continue
        print_payload = await _print_payload_for_peer(
            db, c.ticker, c.expected_window_start
        )
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
                    **print_payload,  # eps_surprise_pct, revenue_surprise_pct, guidance_direction
                },
            )
        )
```

- [ ] **Step 2: Update the `summarize_read_through` system prompt**

Find the `READ_THROUGH_SUMMARY_SYSTEM` constant (or whatever the existing summary prompt is named — `grep -n "summarize_read_through\|READ_THROUGH" backend/app/services/read_through.py`).

Append one paragraph to the system prompt, after the existing "you are an analyst" framing and before any output-shape instructions:

```
If the peer event includes post-print actuals (`eps_surprise_pct`, `revenue_surprise_pct`, `guidance_direction`), treat them as the most recent objective signal about the peer's print and reason about implications for THIS thesis. Do not parrot or restate the peer thesis's verdict — it is not provided to you. Reason from the numbers, the relationship type, and this thesis's pillars.
```

- [ ] **Step 3: Smoke-check that surprise fields appear when a print exists**

Manual smoke (assumes you have at least one `EarningsPrint` row from Task 5's smoke):

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
        since = until - timedelta(days=120)  # widen so AAPL recent print is in range
        events = await compute_peer_events(db, since, until)
        for e in events:
            if e.event_type == 'earnings':
                print(e.peer_ticker, e.event_date, list(e.payload.keys()))

asyncio.run(main())
"
```

Expected: any earnings event whose ticker has a matching `earnings_prints` row with actuals populated should print payload keys including `eps_surprise_pct`. Earnings events without a matching print row print only the original keys.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/read_through.py
git commit -m "feat(read-through): enrich earnings peer-event payload with surprise numbers"
```

---

## Task 10: `api/earnings.py` + register router

**Files:**
- Create: `backend/app/api/earnings.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the API module**

Create `backend/app/api/earnings.py`. **No `from __future__ import annotations`** (FastAPI 0.115 / Python 3.12 footgun called out in CLAUDE.md and used by `api/status.py` / `api/read_through.py`).

```python
"""Earnings cycle navigator API.

Routes:
  GET   /api/earnings/board?window_days=14
  POST  /api/runs/{run_id}/earnings/{print_id}/brief
  POST  /api/runs/{run_id}/earnings/{print_id}/verdict
  GET   /api/earnings/prints/{ticker}
  POST  /api/earnings/refresh/{ticker}
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.services.earnings_brief import compute_brief
from backend.app.services.earnings_prints import index_earnings_prints
from backend.app.services.earnings_verdict import compute_verdict

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response models ─────────────────────────────────────────────────────────


class EarningsPrintRow(BaseModel):
    id: str
    ticker: str
    fiscal_year: int
    fiscal_quarter: int
    earnings_date: date
    eps_estimated: Optional[float]
    eps_actual: Optional[float]
    revenue_estimated: Optional[float]
    revenue_actual: Optional[float]
    eps_surprise_pct: Optional[float]
    revenue_surprise_pct: Optional[float]
    guidance_direction: Optional[str]


class ThesisPrintVerdictRow(BaseModel):
    id: str
    run_id: str
    earnings_print_id: str
    verdict: str
    summary_md: str
    pillars_addressed: list[str]
    generated_at: datetime


class MatchedEarningsCatalyst(BaseModel):
    ordinal: int
    signposts: list[str]
    description: str


class EarningsBoardEntry(BaseModel):
    run_id: str
    ticker: str
    theme_id: str
    phase: str  # "pre" | "post" | "none"
    print: Optional[EarningsPrintRow]
    matched_catalyst: Optional[MatchedEarningsCatalyst]
    verdict: Optional[ThesisPrintVerdictRow]


class EarningsBoardResponse(BaseModel):
    entries: list[EarningsBoardEntry]


class BriefResponse(BaseModel):
    summary_md: str
    pillars_addressed: list[str]
    generated_at: datetime


# ── Conversion helpers ──────────────────────────────────────────────────────


def _print_to_pydantic(p: EarningsPrint) -> EarningsPrintRow:
    return EarningsPrintRow(
        id=str(p.id),
        ticker=p.ticker,
        fiscal_year=p.fiscal_year,
        fiscal_quarter=p.fiscal_quarter,
        earnings_date=p.earnings_date,
        eps_estimated=p.eps_estimated,
        eps_actual=p.eps_actual,
        revenue_estimated=p.revenue_estimated,
        revenue_actual=p.revenue_actual,
        eps_surprise_pct=p.eps_surprise_pct,
        revenue_surprise_pct=p.revenue_surprise_pct,
        guidance_direction=p.guidance_direction,
    )


def _verdict_to_pydantic(v: ThesisPrintVerdict) -> ThesisPrintVerdictRow:
    return ThesisPrintVerdictRow(
        id=str(v.id),
        run_id=str(v.run_id),
        earnings_print_id=str(v.earnings_print_id),
        verdict=v.verdict,
        summary_md=v.summary_md,
        pillars_addressed=list(v.pillars_addressed or []),
        generated_at=v.generated_at,
    )
```

- [ ] **Step 2: Implement the board endpoint**

Append to `backend/app/api/earnings.py`:

```python
@router.get("/earnings/board", response_model=EarningsBoardResponse)
async def get_earnings_board(
    window_days: int = 14,
    db: AsyncSession = Depends(get_db),
) -> EarningsBoardResponse:
    """One entry per active status-board thesis with an upcoming print
    within window_days OR a past print within window_days. Empty array
    when no prints fall in window."""
    today = datetime.now(timezone.utc).date()
    lo = today - timedelta(days=window_days)
    hi = today + timedelta(days=window_days)

    sql = text(
        """
        SELECT DISTINCT ON (ticker, theme_id)
            id, ticker, theme_id
        FROM research_runs
        WHERE status = 'completed' AND archived_at IS NULL
        ORDER BY ticker, theme_id, updated_at DESC
        """
    )
    runs = (await db.execute(sql)).all()

    entries: list[EarningsBoardEntry] = []
    for run_row in runs:
        run_id = str(run_row.id)
        ticker = run_row.ticker.upper()
        theme_id = str(run_row.theme_id)

        prints_q = (
            select(EarningsPrint)
            .where(EarningsPrint.ticker == ticker)
            .where(EarningsPrint.earnings_date >= lo)
            .where(EarningsPrint.earnings_date <= hi)
            .order_by(EarningsPrint.earnings_date.desc())
        )
        candidates = (await db.execute(prints_q)).scalars().all()
        if not candidates:
            continue  # no print in window; skip row entirely

        # Pick the most recent post-print if any, else the nearest upcoming.
        post = next((p for p in candidates if p.eps_actual is not None), None)
        upcoming = next(
            (p for p in candidates if p.eps_actual is None and p.earnings_date >= today),
            None,
        )
        chosen = post or upcoming
        if chosen is None:
            continue

        phase = "post" if chosen.eps_actual is not None else "pre"

        cat_q = (
            select(Catalyst)
            .where(Catalyst.run_id == run_id)
            .where(Catalyst.type == "earnings")
            .order_by(Catalyst.ordinal)
            .limit(1)
        )
        matched = (await db.execute(cat_q)).scalars().first()
        matched_pyd: Optional[MatchedEarningsCatalyst] = None
        if matched is not None:
            matched_pyd = MatchedEarningsCatalyst(
                ordinal=matched.ordinal,
                signposts=list(matched.signposts or []),
                description=matched.description,
            )

        verdict_q = (
            select(ThesisPrintVerdict)
            .where(ThesisPrintVerdict.run_id == run_id)
            .where(ThesisPrintVerdict.earnings_print_id == chosen.id)
            .limit(1)
        )
        v = (await db.execute(verdict_q)).scalars().first()

        entries.append(
            EarningsBoardEntry(
                run_id=run_id,
                ticker=ticker,
                theme_id=theme_id,
                phase=phase,
                print=_print_to_pydantic(chosen),
                matched_catalyst=matched_pyd,
                verdict=_verdict_to_pydantic(v) if v is not None else None,
            )
        )

    # Sort: post-print first (most recent), then pre-print (nearest upcoming).
    def sort_key(e: EarningsBoardEntry) -> tuple[int, int]:
        if e.print is None:
            return (2, 0)
        ord_ = e.print.earnings_date.toordinal()
        return (0, -ord_) if e.phase == "post" else (1, ord_)
    entries.sort(key=sort_key)
    return EarningsBoardResponse(entries=entries)
```

- [ ] **Step 3: Implement brief, verdict, prints-by-ticker, refresh endpoints**

Append:

```python
@router.post(
    "/runs/{run_id}/earnings/{print_id}/brief",
    response_model=BriefResponse,
)
async def post_brief(
    run_id: str,
    print_id: str,
    db: AsyncSession = Depends(get_db),
) -> BriefResponse:
    try:
        out = await compute_brief(run_id, print_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("brief generation failed: run=%s print=%s", run_id, print_id)
        raise HTTPException(status_code=502, detail="brief generation failed")
    return BriefResponse(
        summary_md=out.summary_md,
        pillars_addressed=out.pillars_addressed,
        generated_at=datetime.now(timezone.utc),
    )


@router.post(
    "/runs/{run_id}/earnings/{print_id}/verdict",
    response_model=ThesisPrintVerdictRow,
)
async def post_verdict(
    run_id: str,
    print_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ThesisPrintVerdictRow:
    fmp = request.app.state.fmp
    try:
        row = await compute_verdict(run_id, print_id, fmp, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("verdict generation failed: run=%s print=%s", run_id, print_id)
        raise HTTPException(status_code=502, detail="verdict generation failed")
    return _verdict_to_pydantic(row)


@router.get("/earnings/prints/{ticker}", response_model=list[EarningsPrintRow])
async def get_prints_by_ticker(
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> list[EarningsPrintRow]:
    q = (
        select(EarningsPrint)
        .where(EarningsPrint.ticker == ticker.upper())
        .order_by(EarningsPrint.earnings_date.desc())
        .limit(8)
    )
    rows = (await db.execute(q)).scalars().all()
    return [_print_to_pydantic(r) for r in rows]


@router.post("/earnings/refresh/{ticker}")
async def post_refresh(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    fmp = request.app.state.fmp
    try:
        rows = await index_earnings_prints(ticker, fmp, db)
        await db.commit()
    except Exception:
        logger.exception("manual earnings refresh failed: %s", ticker)
        raise HTTPException(status_code=502, detail="refresh failed")
    return {"updated": len(rows), "ticker": ticker.upper()}
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/app/main.py`, alongside the other router imports (~line 14-22):

```python
from backend.app.api.earnings import router as earnings_router
```

Alongside the other `app.include_router` calls (~line 103-111):

```python
app.include_router(earnings_router, prefix="/api")
```

- [ ] **Step 5: Boot smoke check**

Run:
```bash
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload &
sleep 3
curl -s http://localhost:8000/api/earnings/board | head -c 200
echo
curl -s http://localhost:8000/api/earnings/prints/AAPL | head -c 200
echo
kill %1
```

Expected: first curl returns `{"entries":[...]}` (possibly empty), second returns a JSON array of up to 8 print rows.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/earnings.py backend/app/main.py
git commit -m "feat(earnings): API router with board, brief, verdict, prints, refresh endpoints"
```

---

## Task 11: Frontend types + client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add types**

In `frontend/lib/api.ts`, find a section that already declares status-board types (`StatusBoardEntry`, `Health`, etc.) and append after them:

```ts
// ── Earnings cycle navigator ────────────────────────────────────────────────

export type VerdictPhase = "pre" | "post" | "none";
export type Verdict = "confirms" | "threatens" | "neutral" | "insufficient";

export interface EarningsPrintRow {
  id: string;
  ticker: string;
  fiscal_year: number;
  fiscal_quarter: number;
  earnings_date: string; // YYYY-MM-DD
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
  eps_surprise_pct: number | null;
  revenue_surprise_pct: number | null;
  guidance_direction: "raised" | "maintained" | "lowered" | "n/a" | null;
}

export interface ThesisPrintVerdictRow {
  id: string;
  run_id: string;
  earnings_print_id: string;
  verdict: Verdict;
  summary_md: string;
  pillars_addressed: string[];
  generated_at: string; // ISO
}

export interface MatchedEarningsCatalyst {
  ordinal: number;
  signposts: string[];
  description: string;
}

export interface EarningsBoardEntry {
  run_id: string;
  ticker: string;
  theme_id: string;
  phase: VerdictPhase;
  print: EarningsPrintRow | null;
  matched_catalyst: MatchedEarningsCatalyst | null;
  verdict: ThesisPrintVerdictRow | null;
}

export interface EarningsBoardResponse {
  entries: EarningsBoardEntry[];
}

export interface BriefResponse {
  summary_md: string;
  pillars_addressed: string[];
  generated_at: string;
}
```

- [ ] **Step 2: Add client object**

Find the section where existing client objects are exported (`status`, `themes`, `readThroughs`, etc.) and append after them:

```ts
export const earnings = {
  board: async (windowDays: number = 14): Promise<EarningsBoardResponse> => {
    const r = await fetch(`${API_BASE}/api/earnings/board?window_days=${windowDays}`);
    if (!r.ok) throw new Error(`earnings.board failed: ${r.status}`);
    return r.json();
  },
  brief: async (runId: string, printId: string): Promise<BriefResponse> => {
    const r = await fetch(
      `${API_BASE}/api/runs/${runId}/earnings/${printId}/brief`,
      { method: "POST" }
    );
    if (!r.ok) throw new Error(`earnings.brief failed: ${r.status}`);
    return r.json();
  },
  verdict: async (runId: string, printId: string): Promise<ThesisPrintVerdictRow> => {
    const r = await fetch(
      `${API_BASE}/api/runs/${runId}/earnings/${printId}/verdict`,
      { method: "POST" }
    );
    if (!r.ok) throw new Error(`earnings.verdict failed: ${r.status}`);
    return r.json();
  },
  printsByTicker: async (ticker: string): Promise<EarningsPrintRow[]> => {
    const r = await fetch(`${API_BASE}/api/earnings/prints/${ticker}`);
    if (!r.ok) throw new Error(`earnings.printsByTicker failed: ${r.status}`);
    return r.json();
  },
  refresh: async (ticker: string): Promise<{ updated: number; ticker: string }> => {
    const r = await fetch(`${API_BASE}/api/earnings/refresh/${ticker}`, { method: "POST" });
    if (!r.ok) throw new Error(`earnings.refresh failed: ${r.status}`);
    return r.json();
  },
};
```

(`API_BASE` is the existing constant referencing `NEXT_PUBLIC_API_URL`. Use whatever the file already uses — the existing `status` and `readThroughs` client objects show the right pattern.)

- [ ] **Step 3: Verify types**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors. If there are, they should be unrelated to the earnings additions; only fix earnings-related issues here.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(earnings): typed frontend client + types for earnings cycle navigator"
```

---

## Task 12: `EarningsDrawer.tsx` component (with safe markdown renderer)

The frontend has no markdown library installed (existing thesis text in `ThesisCard.tsx` renders as plain JSX). To safely render Haiku output (`**bold**`, paragraphs, `- ` bullets) without `dangerouslySetInnerHTML`, this task includes an inline `SafeMarkdownBlock` React component that parses the small subset Haiku produces and returns React elements only — no HTML injection.

**Files:**
- Create: `frontend/components/status/EarningsDrawer.tsx`

- [ ] **Step 1: Create the drawer with the safe markdown renderer**

Create `frontend/components/status/EarningsDrawer.tsx`:

```tsx
"use client";

import { useState, type ReactNode } from "react";
import {
  earnings,
  type EarningsBoardEntry,
  type Verdict,
  type ThesisPrintVerdictRow,
  type BriefResponse,
} from "@/lib/api";

interface Props {
  entry: EarningsBoardEntry;
  onVerdictGenerated?: (verdict: ThesisPrintVerdictRow) => void;
}

const VERDICT_PILL: Record<Verdict, string> = {
  confirms:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  threatens:    "bg-red-500/10 text-red-400 border-red-500/30",
  neutral:      "bg-slate-500/10 text-slate-400 border-slate-500/30",
  insufficient: "bg-amber-500/10 text-amber-400 border-amber-500/30",
};

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function fmtUSD(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

// ── Safe markdown renderer (no innerHTML) ───────────────────────────────────

/**
 * Render a small subset of markdown as React nodes — paragraphs, bullet
 * lists (`- ` lines), and `**bold**` spans. Anything else is rendered as
 * plain text. Safe by construction: no innerHTML, no HTML injection.
 *
 * Haiku output for this feature is constrained to bullets + bold by the
 * system prompt, so this renderer is sufficient. If/when the project
 * adopts a markdown library (e.g. react-markdown), swap this for that.
 */
function SafeMarkdownBlock({ source }: { source: string }) {
  const blocks = source.split(/\n\n+/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="space-y-2 text-sm text-slate-200">
      {blocks.map((block, i) => {
        const lines = block.split("\n");
        const isList = lines.every((l) => l.trimStart().startsWith("- "));
        if (isList) {
          return (
            <ul key={i} className="list-disc list-inside space-y-1">
              {lines.map((l, j) => (
                <li key={j}>{renderInline(l.trimStart().slice(2))}</li>
              ))}
            </ul>
          );
        }
        return <p key={i}>{renderInline(block.replace(/\n/g, " "))}</p>;
      })}
    </div>
  );
}

function renderInline(text: string): ReactNode {
  // Split on **bold**, returning alternating text and <strong> nodes.
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

// ── Drawer dispatcher ───────────────────────────────────────────────────────

export function EarningsDrawer({ entry, onVerdictGenerated }: Props) {
  if (!entry.print) return null;
  if (entry.verdict) return <VerdictBlock entry={entry} />;
  if (entry.phase === "post") return <PostEarningsBlock entry={entry} onVerdictGenerated={onVerdictGenerated} />;
  return <PreEarningsBlock entry={entry} />;
}

// ── Pre-print ───────────────────────────────────────────────────────────────

function PreEarningsBlock({ entry }: { entry: EarningsBoardEntry }) {
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    if (!entry.print) return;
    setLoading(true);
    setErr(null);
    try {
      const out = await earnings.brief(entry.run_id, entry.print.id);
      setBrief(out);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }

  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-slate-900/40 border-t border-slate-800">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-300">
        <span><span className="text-slate-500">Date:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-slate-500">EPS est:</span> {p.eps_estimated?.toFixed(2) ?? "—"}</span>
        <span><span className="text-slate-500">Rev est:</span> {fmtUSD(p.revenue_estimated)}</span>
      </div>
      {entry.matched_catalyst && entry.matched_catalyst.signposts.length > 0 && (
        <div className="mt-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Signposts</div>
          <ul className="list-disc list-inside text-xs text-slate-300 space-y-0.5">
            {entry.matched_catalyst.signposts.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={generate}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-slate-700 hover:border-slate-500 disabled:opacity-50"
        >
          {loading ? "Generating…" : brief ? "Regenerate brief" : "Generate pre-earnings brief"}
        </button>
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
      {brief && (
        <div className="mt-3">
          <SafeMarkdownBlock source={brief.summary_md} />
        </div>
      )}
    </div>
  );
}

// ── Post-print, no verdict yet ──────────────────────────────────────────────

function PostEarningsBlock({
  entry,
  onVerdictGenerated,
}: {
  entry: EarningsBoardEntry;
  onVerdictGenerated?: (v: ThesisPrintVerdictRow) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    if (!entry.print) return;
    setLoading(true);
    setErr(null);
    try {
      const v = await earnings.verdict(entry.run_id, entry.print.id);
      onVerdictGenerated?.(v);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }

  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-slate-900/40 border-t border-slate-800">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-300">
        <span><span className="text-slate-500">Reported:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-slate-500">EPS surprise:</span> <strong>{fmtPct(p.eps_surprise_pct)}</strong></span>
        <span><span className="text-slate-500">Rev surprise:</span> <strong>{fmtPct(p.revenue_surprise_pct)}</strong></span>
        <span><span className="text-slate-500">Guidance:</span> {p.guidance_direction ?? "—"}</span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={generate}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-emerald-700 text-emerald-400 hover:border-emerald-500 disabled:opacity-50"
        >
          {loading ? "Running thesis-check…" : "Run thesis-check"}
        </button>
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
    </div>
  );
}

// ── Verdict rendered ────────────────────────────────────────────────────────

function VerdictBlock({ entry }: { entry: EarningsBoardEntry }) {
  const v = entry.verdict!;
  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-slate-900/40 border-t border-slate-800">
      <div className="flex items-center gap-3 mb-2">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-semibold ${VERDICT_PILL[v.verdict]}`}>
          {v.verdict}
        </span>
        <span className="text-xs text-slate-500">
          {p.earnings_date} · {p.fiscal_year}Q{p.fiscal_quarter} ·
          EPS {fmtPct(p.eps_surprise_pct)} · Rev {fmtPct(p.revenue_surprise_pct)} ·
          Guidance {p.guidance_direction ?? "—"}
        </span>
      </div>
      <SafeMarkdownBlock source={v.summary_md} />
      {v.pillars_addressed.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {v.pillars_addressed.map((pillar) => (
            <span key={pillar} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">
              {pillar}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/status/EarningsDrawer.tsx
git commit -m "feat(earnings): EarningsDrawer with safe markdown renderer (no innerHTML)"
```

---

## Task 13: Wire badge + drawer + polling into `/status` page

**Files:**
- Modify: `frontend/app/status/page.tsx`

- [ ] **Step 1: Add the polling hook**

In `frontend/app/status/page.tsx`, locate the existing read-throughs polling block (it polls `readThroughs.list()` on a 60s interval while the tab is visible). Add a parallel poll for earnings.

Imports — extend the existing `from "@/lib/api"` import to include the earnings client and types, and add the EarningsDrawer import:

```ts
import {
  earnings as earningsApi,
  // ...existing imports preserved...
  type EarningsBoardEntry,
  type ThesisPrintVerdictRow,
} from "@/lib/api";
import { EarningsDrawer } from "@/components/status/EarningsDrawer";
```

Add state alongside the existing `readThroughs` state:

```ts
const [earningsByRun, setEarningsByRun] = useState<Record<string, EarningsBoardEntry>>({});
const [earningsExpanded, setEarningsExpanded] = useState<Record<string, boolean>>({});
```

In the polling effect block, alongside the existing `readThroughs.list()` fetch, add:

```ts
useEffect(() => {
  let cancelled = false;
  async function refresh() {
    if (document.visibilityState !== "visible") return;
    try {
      const out = await earningsApi.board(14);
      if (cancelled) return;
      const next: Record<string, EarningsBoardEntry> = {};
      for (const e of out.entries) {
        next[e.run_id] = e;
      }
      setEarningsByRun(next);
    } catch {
      // soft fail; do not unmount the rest of the page
    }
  }
  refresh();
  const id = setInterval(refresh, 60_000);
  const onVis = () => { if (document.visibilityState === "visible") refresh(); };
  document.addEventListener("visibilitychange", onVis);
  return () => {
    cancelled = true;
    clearInterval(id);
    document.removeEventListener("visibilitychange", onVis);
  };
}, []);
```

- [ ] **Step 2: Add the badge to each row**

Find the existing per-row render (where `HealthPill` and the `⟿ N` read-through badge are rendered). Add a third badge right of the read-through badge:

```tsx
{(() => {
  const e = earningsByRun[entry.run_id];
  if (!e || !e.print) return null;
  const onClick = () => {
    setEarningsExpanded((m) => ({ ...m, [entry.run_id]: !m[entry.run_id] }));
  };
  if (e.verdict) {
    const colors = VERDICT_BADGE[e.verdict.verdict];
    return (
      <button
        onClick={onClick}
        data-print-hide="true"
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${colors}`}
      >
        📊 {e.verdict.verdict}
      </button>
    );
  }
  if (e.phase === "post") {
    const days = daysSince(e.print.earnings_date);
    return (
      <button
        onClick={onClick}
        data-print-hide="true"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-semibold"
      >
        📊 reported {days}d ago
      </button>
    );
  }
  if (e.phase === "pre") {
    const days = daysUntil(e.print.earnings_date);
    return (
      <button
        onClick={onClick}
        data-print-hide="true"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-blue-500/30 bg-blue-500/10 text-blue-400 text-[11px] font-semibold"
      >
        📅 T-{days}d
      </button>
    );
  }
  return null;
})()}
```

Add the helper constants and date utils near the top of the file (alongside `HEALTH_PILL` and `fmtDays`):

```tsx
const VERDICT_BADGE: Record<"confirms" | "threatens" | "neutral" | "insufficient", string> = {
  confirms:     "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  threatens:    "border-red-500/30 bg-red-500/10 text-red-400",
  neutral:      "border-slate-500/30 bg-slate-500/10 text-slate-400",
  insufficient: "border-amber-500/30 bg-amber-500/10 text-amber-400",
};

function daysUntil(isoDate: string): number {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const target = new Date(`${isoDate}T00:00:00Z`);
  return Math.max(0, Math.round((target.getTime() - today.getTime()) / 86400000));
}

function daysSince(isoDate: string): number {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const target = new Date(`${isoDate}T00:00:00Z`);
  return Math.max(0, Math.round((today.getTime() - target.getTime()) / 86400000));
}
```

- [ ] **Step 3: Mount the drawer below the row**

Find the existing read-through drawer mount (rendered conditionally beneath the row when expanded). Add a parallel mount for the earnings drawer:

```tsx
{earningsExpanded[entry.run_id] && earningsByRun[entry.run_id] && (
  <EarningsDrawer
    entry={earningsByRun[entry.run_id]}
    onVerdictGenerated={(v: ThesisPrintVerdictRow) => {
      setEarningsByRun((m) => ({
        ...m,
        [entry.run_id]: { ...m[entry.run_id], verdict: v },
      }));
    }}
  />
)}
```

- [ ] **Step 4: Run lint + build**

```bash
cd frontend
npm run lint
npm run build
```

Expected: lint passes, build succeeds. If type errors reference earnings types, fix them; if they reference unrelated existing code, leave alone.

- [ ] **Step 5: Manual Playwright walkthrough**

Start the dev stack:
```bash
cd frontend && npm run dev &
cd .. && uvicorn backend.app.main:app --reload &
```

Open http://localhost:3000/status. Expected on a board with at least one row whose ticker has an upcoming print within 14d: a blue `📅 T-{N}d` badge appears. Click expands the drawer with consensus + signposts + "Generate pre-earnings brief" button. Click button → 2-4s Haiku call → bullets render via `SafeMarkdownBlock`.

For a post-print row: badge is amber `📊 reported {N}d ago`. Click expands drawer with surprise % numbers + "Run thesis-check" button. Click button → Haiku call → drawer transitions to verdict-rendered state with green/red/amber/slate pill.

Kill the dev servers when done.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/status/page.tsx
git commit -m "feat(earnings): wire earnings badge + drawer + 60s poll into /status"
```

---

## Task 14: Smoke script + end-to-end verification

**Files:**
- Create: `backend/scripts/smoke_earnings_navigator.py`

- [ ] **Step 1: Create the smoke script**

Create `backend/scripts/smoke_earnings_navigator.py`:

```python
"""End-to-end smoke for Tier 2.5 — Earnings Cycle Navigator.

Runs three assertions against the live dev DB:
1. Indexer materializes a print row for an active board ticker.
2. Verdict round-trips Haiku → DB persist for a synthetic post-print row.
3. Read-through enrichment surfaces eps_surprise_pct on a peer-event
   payload when a matching earnings_print row exists.

Usage:
    PYTHONPATH=. python -m backend.scripts.smoke_earnings_navigator <run_id> <peer_ticker>

Exits 0 on green, 1 with the failed assertion's name on red.
Cleans up the synthetic earnings_print rows created in assertions 2 and 3.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.services.earnings_prints import (
    fetch_active_board_tickers,
    index_earnings_prints,
)
from backend.app.services.earnings_verdict import compute_verdict
from backend.app.services.read_through import compute_peer_events

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def assertion_1_indexer(fmp: FMPClient) -> None:
    async with async_session() as db:
        tickers = await fetch_active_board_tickers(db)
    assert tickers, "no active board tickers"
    ticker = tickers[0]
    async with async_session() as db:
        rows = await index_earnings_prints(ticker, fmp, db)
        await db.commit()
    assert any(r.eps_estimated is not None for r in rows), \
        f"[{ticker}] no eps_estimated in any of {len(rows)} rows"
    logger.info("assertion 1 passed: %s prints upserted for %s", len(rows), ticker)


async def assertion_2_verdict(run_id: str, fmp: FMPClient) -> str:
    """Synthesize a post-print row, compute verdict, assert shape. Returns
    the synthetic print_id so cleanup can remove it."""
    synth_ticker = "ZZZS"
    print_id = str(uuid4())
    async with async_session() as db:
        row = EarningsPrint(
            id=print_id,
            ticker=synth_ticker,
            fiscal_year=2026,
            fiscal_quarter=1,
            earnings_date=date(2026, 4, 30),
            eps_estimated=1.50,
            eps_actual=1.62,
            revenue_estimated=10_000_000_000,
            revenue_actual=10_300_000_000,
            eps_surprise_pct=0.08,
            revenue_surprise_pct=0.03,
            guidance_direction="raised",
        )
        db.add(row)
        await db.commit()

    async with async_session() as db:
        v = await compute_verdict(run_id, print_id, fmp, db)
        await db.commit()
        assert v.verdict in {"confirms", "threatens", "neutral", "insufficient"}, \
            f"unexpected verdict: {v.verdict!r}"
        assert isinstance(v.pillars_addressed, list)
        assert len(v.summary_md) > 50
    logger.info(
        "assertion 2 passed: verdict=%s pillars=%d summary_chars=%d",
        v.verdict, len(v.pillars_addressed), len(v.summary_md),
    )
    return print_id


async def assertion_3_read_through_enrichment(peer_ticker: str) -> None:
    """Insert a synthetic catalyst + post-print row for `peer_ticker`,
    verify the peer-event payload includes eps_surprise_pct, then clean up."""
    synth_print_id = str(uuid4())
    synth_cat_id = str(uuid4())
    today = datetime.now(timezone.utc).date()
    async with async_session() as db:
        any_run_q = select(ResearchRun).where(ResearchRun.status == "completed").limit(1)
        any_run = (await db.execute(any_run_q)).scalars().first()
        assert any_run is not None, "no completed runs to attach synthetic catalyst to"

        synth_cat = Catalyst(
            id=synth_cat_id,
            run_id=str(any_run.id),
            ticker=peer_ticker.upper(),
            ordinal=999,
            timeframe="Smoke synthetic",
            description="Smoke synthetic earnings",
            type="earnings",
            signposts=[],
            linked_pillar=None,
            expected_date=today + timedelta(days=2),
            expected_window_start=today + timedelta(days=2),
            expected_window_end=today + timedelta(days=3),
            date_source="smoke",
        )
        synth_print = EarningsPrint(
            id=synth_print_id,
            ticker=peer_ticker.upper(),
            fiscal_year=today.year,
            fiscal_quarter=(today.month - 1) // 3 + 1,
            earnings_date=today + timedelta(days=2),
            eps_estimated=1.0,
            eps_actual=1.1,
            revenue_estimated=1_000_000_000,
            revenue_actual=1_050_000_000,
            eps_surprise_pct=0.10,
            revenue_surprise_pct=0.05,
            guidance_direction="maintained",
        )
        db.add_all([synth_cat, synth_print])
        await db.commit()

    try:
        async with async_session() as db:
            until = datetime.now(timezone.utc) + timedelta(days=10)
            since = until - timedelta(days=30)
            events = await compute_peer_events(db, since, until)
        match = next(
            (e for e in events
             if e.event_type == "earnings"
             and e.peer_ticker == peer_ticker.upper()
             and e.payload.get("eps_surprise_pct") == 0.10),
            None,
        )
        assert match is not None, "no enriched earnings event with eps_surprise_pct=0.10"
        logger.info("assertion 3 passed: enriched payload keys=%s", list(match.payload.keys()))
    finally:
        async with async_session() as db:
            await db.execute(delete(Catalyst).where(Catalyst.id == synth_cat_id))
            await db.execute(delete(EarningsPrint).where(EarningsPrint.id == synth_print_id))
            await db.commit()


async def cleanup_assertion_2(print_id: str, run_id: str) -> None:
    async with async_session() as db:
        await db.execute(
            delete(ThesisPrintVerdict)
            .where(ThesisPrintVerdict.run_id == run_id)
            .where(ThesisPrintVerdict.earnings_print_id == print_id)
        )
        await db.execute(delete(EarningsPrint).where(EarningsPrint.id == print_id))
        await db.commit()


async def main(run_id: str, peer_ticker: str) -> int:
    fmp = FMPClient()
    print_id: str | None = None
    try:
        await assertion_1_indexer(fmp)
        print_id = await assertion_2_verdict(run_id, fmp)
        await assertion_3_read_through_enrichment(peer_ticker)
        return 0
    except AssertionError as e:
        logger.error("ASSERTION FAILED: %s", e)
        return 1
    finally:
        if print_id is not None:
            await cleanup_assertion_2(print_id, run_id)
        await fmp.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: smoke_earnings_navigator.py <run_id> <peer_ticker>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
```

- [ ] **Step 2: Run the smoke**

Pick an existing completed `run_id` from the dev DB:

```bash
psql "$(python -c "from backend.app.config import get_settings; print(get_settings().database_url_sync)")" -c "SELECT id, ticker FROM research_runs WHERE status='completed' AND archived_at IS NULL LIMIT 5;"
```

Pick any `id` and a peer ticker. Run:

```bash
source backend/venv/bin/activate
PYTHONPATH=. python -m backend.scripts.smoke_earnings_navigator <run_id> <peer_ticker>
```

Expected: three lines of `assertion N passed: ...` and exit 0.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/smoke_earnings_navigator.py
git commit -m "test(earnings): end-to-end smoke for indexer + verdict + read-through enrichment"
```

---

## Task 15: Final lint, build, type-check + push branch

- [ ] **Step 1: Backend import sanity**

Run:

```bash
source backend/venv/bin/activate
PYTHONPATH=. python -c "
from backend.app.main import app
print(f'routes: {len(app.routes)}')
"
```

Expected: a number that includes the 5 new earnings routes (typically 50+ total). If the import fails, fix the underlying issue — never skip.

- [ ] **Step 2: Frontend lint + build**

```bash
cd frontend
npm run lint
npm run build
cd ..
```

Expected: both pass.

- [ ] **Step 3: Re-run smoke**

```bash
source backend/venv/bin/activate
PYTHONPATH=. python -m backend.scripts.smoke_earnings_navigator <run_id> <peer_ticker>
```

Expected: 3/3 green.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin feat/earnings-navigator
```

If the branch was stacked on `feat/status-board-and-read-through` (PR #21 still open at branch-creation time), DO NOT open the PR until PR #21 lands. Instead: when PR #21 is squash-merged, run:

```bash
git fetch origin
git rebase origin/main
git push --force-with-lease origin feat/earnings-navigator
```

Then open the PR off `main`.

- [ ] **Step 5: Open the PR**

```bash
gh pr create \
  --base main \
  --title "feat: earnings cycle navigator (Tier 2.5)" \
  --body "$(cat <<'EOF'
Implements Tier 2.5 — pre/post-earnings layer over active status-board theses.

## Summary
- New `earnings_prints` and `thesis_print_verdicts` tables (idempotent indexer + lazy LLM verdict).
- Daily APScheduler cron at 21:00 UTC walks active board tickers, upserts prints, runs Haiku guidance-direction extraction on transcript when actuals first appear.
- `/api/earnings/*` router (5 endpoints; no `from __future__ import annotations` per the FastAPI 0.115 footgun).
- Read-through engine enriched with surprise numbers — narrative verdict stays scoped to originator per spec Q5-B.
- `/status` page grows a third badge slot + `EarningsDrawer.tsx` mirroring the read-through drawer.
- Symmetric slack window in `_try_fmp_earnings_override` (rolled in while in the area).

## Test plan
- [x] Backend smoke `smoke_earnings_navigator.py` 3/3 green.
- [x] Frontend lint + build clean.
- [x] Manual Playwright walkthrough on `/status` covers pre-print, post-print, and verdict states.
- [x] Alembic upgrade + downgrade both reverse cleanly.

Spec: `docs/superpowers/specs/2026-05-05-tier-2-5-earnings-navigator-design.md` (local-only).
Plan: `docs/superpowers/plans/2026-05-05-tier-2-5-earnings-navigator.md` (local-only).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review

Spec coverage check:

| Spec section | Plan task |
|---|---|
| `earnings_prints` table | Task 1 + 3 |
| `thesis_print_verdicts` table | Task 2 + 3 |
| Alembic migration (single, hand-written downgrade) | Task 3 |
| `index_earnings_prints` + `fetch_active_board_tickers` | Task 5 |
| `compute_brief` (pre-earnings Haiku) | Task 6 |
| `compute_verdict` (post-print Haiku, persisted) | Task 7 |
| `extract_guidance_direction` (small Haiku, scheduler-side) | Task 7 + 8 |
| Daily APScheduler cron, registered in `app/main.py::lifespan` | Task 8 |
| Symmetric slack window in `_try_fmp_earnings_override` | Task 4 |
| Read-through payload enrichment with surprise numbers | Task 9 |
| Read-through summary prompt update ("do not parrot") | Task 9 |
| 5 `/api/earnings/*` endpoints, no future annotations | Task 10 |
| `lib/api.ts` types + client | Task 11 |
| `EarningsDrawer.tsx` (3 sub-views) + safe markdown rendering | Task 12 |
| `/status` page badge slot + 60s polling + drawer mount | Task 13 |
| Smoke script with 3 assertions + cleanup | Task 14 |
| Final verification before PR | Task 15 |

Type / signature consistency check:

- `EarningsPrint` columns referenced consistently across model (Task 1), migration (Task 3), services (Tasks 5, 6, 7, 8, 9), API (Task 10), and smoke (Task 14). ✓
- `ThesisPrintVerdict` likewise. ✓
- Pydantic `VerdictOutput.verdict` is `Literal["confirms", "threatens", "neutral", "insufficient"]` everywhere; matches the API response model and the frontend `Verdict` union. ✓
- `BriefOutput.summary_md` (str) + `pillars_addressed` (list[str]) — the `BriefResponse` API model carries the same shape. ✓
- `compute_verdict` signature `(run_id: str, earnings_print_id: str, fmp: FMPClient, db: AsyncSession)` — matches the call sites in the API (Task 10) and the smoke script (Task 14). ✓
- Frontend `EarningsBoardEntry` mirrors the API's Pydantic shape. ✓
- `phase: "pre" | "post" | "none"` — backend never returns "none" today (rows without prints in window are filtered out). The "none" case is reserved in the type for future use. Acceptable as documented; not a contradiction.
- `SafeMarkdownBlock` consumes `string` and emits React nodes — used identically in `PreEarningsBlock` (with `BriefResponse.summary_md`) and `VerdictBlock` (with `ThesisPrintVerdictRow.summary_md`). ✓

No placeholder scan red flags: no `TBD`, `TODO`, `FIXME`, "implement later", or "similar to Task N" hand-waves.

Open implementation choice from spec: **resolved to Haiku for guidance extraction** (Task 7's `extract_guidance_direction`).

---

## Post-merge follow-ups (for the next session, not this plan)

- Watch the daily scheduler logs for a week of real earnings prints. If `guidance_enriched` is consistently zero despite known guidance language, revisit by adding a regex pre-pass.
- If `SafeMarkdownBlock` proves insufficient (Haiku producing tables, code blocks, links, etc.), evaluate adopting `react-markdown` repo-wide and replace the inline renderer.
- If `compute_brief` becomes a hot path (>5 calls/day per user), consider caching the brief in a `thesis_print_briefs` mirror table.
