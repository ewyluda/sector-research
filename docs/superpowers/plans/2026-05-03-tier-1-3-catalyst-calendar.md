# Tier 1.3 Catalyst Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote catalysts from thesis JSONB to first-class rows in a `catalysts` table, parse free-form timeframes into dates, optionally bind earnings catalysts to FMP's earnings calendar, and surface a proximity-bucketed calendar at `/catalysts` (plus a per-ticker view inside `/pipeline/[runId]`).

**Architecture:** New `catalysts` table FK'd to `research_runs`. Upsert hook at the end of `node_thesis_construction` writes one row per parsed catalyst. Per-run scoping (re-runs produce a fresh set; old rows remain as history). Stateless lifecycle (display layer derives `upcoming/imminent/passed` from `expected_date`). One Alembic migration; no DB triggers. Frontend reads a single proximity-bucketed JSON shape from `GET /api/catalysts`.

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 / Alembic / Pydantic / asyncpg on the backend; Next.js 16 / React 19 / Tailwind v4 / TypeScript on the frontend. No new external dependencies.

**Verification convention:** No backend test framework is configured per CLAUDE.md, and no frontend test runner is referenced. Each backend task uses an import smoke check + a short stdlib-only sanity script. Each frontend task uses `npm run lint` and `npx tsc --noEmit`. End-to-end verification (Tasks 13 + 14) is manual.

**Spec:** `docs/superpowers/specs/2026-05-03-tier-1-3-catalyst-calendar-design.md`

---

## File map

**Backend (5 new files, 3 modified):**
- Create: `backend/app/models/catalyst.py` — Catalyst SQLAlchemy model.
- Create: `backend/migrations/versions/<rev>_add_catalysts_table.py` — Alembic migration.
- Create: `backend/app/services/catalyst_dates.py` — `parse_timeframe(timeframe, anchor) -> ParsedDates`.
- Create: `backend/app/services/catalyst_promotion.py` — `promote_catalysts(state, parsed, fmp, db)`.
- Create: `backend/app/api/catalysts.py` — `GET /api/catalysts`, `GET /api/catalysts/{id}`.
- Create: `backend/scripts/backfill_catalysts.py` — one-shot rebuilder.
- Modify: `backend/app/clients/fmp.py` — add `get_earnings_calendar(ticker)`.
- Modify: `backend/app/graph/nodes.py` — wire `promote_catalysts(...)` into `node_thesis_construction` (around line 1276 after the structured parse succeeds).
- Modify: `backend/app/main.py` — `app.include_router(catalysts_router, prefix="/api")`.

**Frontend (3 new files, 3 modified):**
- Create: `frontend/app/catalysts/page.tsx` — fleet-wide calendar page.
- Create: `frontend/components/CatalystCalendar.tsx` — proximity-bucketed list component.
- Create: `frontend/components/CatalystRow.tsx` — single-row presentational component (kept separate so both the page and the per-ticker panel reuse it).
- Modify: `frontend/lib/api.ts` — add `CatalystRow`, `CatalystBuckets` types and `getCatalysts`/`getCatalyst` client methods.
- Modify: `frontend/components/Nav.tsx` — add the "Catalysts" link.
- Modify: `frontend/app/pipeline/[runId]/page.tsx` — render `<CatalystCalendar>` filtered to the current ticker, between the deep-dive dashboard and the `<ThesisCard>`.

---

## Task 1: Catalyst SQLAlchemy model + Alembic migration

**Files:**
- Create: `backend/app/models/catalyst.py`
- Create: `backend/migrations/versions/<rev>_add_catalysts_table.py` (Alembic generates the filename)
- Modify: `backend/app/models/__init__.py` (export Catalyst alongside the other models — match the existing pattern).

- [ ] **Step 1.1: Write the SQLAlchemy model**

Create `backend/app/models/catalyst.py`:

```python
"""Catalyst — first-class catalyst event row, FK'd to a thesis run.

One row per catalyst per thesis run. Re-running the thesis produces a
fresh set; old rows remain as historical record (per-run scoping, not
identity-merged across re-runs).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Catalyst(Base):
    __tablename__ = "catalysts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)

    # Sonnet-emitted (Tier 1.1 catalyst schema)
    timeframe: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str | None] = mapped_column(String(20))
    signposts: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    linked_pillar: Mapped[str | None] = mapped_column(String(10))

    # Date inference
    expected_date: Mapped[date | None]
    expected_window_start: Mapped[date | None]
    expected_window_end: Mapped[date | None]
    date_source: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_catalysts_run_id", "run_id"),
        Index("ix_catalysts_ticker_expected_date", "ticker", "expected_date"),
    )
```

- [ ] **Step 1.2: Re-export the model**

Open `backend/app/models/__init__.py`. Add `from backend.app.models.catalyst import Catalyst` next to the existing imports, and append `"Catalyst"` to the `__all__` list if it exists. (If the file doesn't have `__all__`, just adding the import is enough — match whatever the neighbouring entries do.)

- [ ] **Step 1.3: Verify the model imports cleanly**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
from backend.app.models.catalyst import Catalyst
print('table:', Catalyst.__tablename__)
print('fields:', list(Catalyst.__table__.columns.keys()))
print('indexes:', [i.name for i in Catalyst.__table__.indexes])
"
```

Expected output:

```
table: catalysts
fields: ['id', 'run_id', 'ticker', 'ordinal', 'timeframe', 'description', 'type', 'signposts', 'linked_pillar', 'expected_date', 'expected_window_start', 'expected_window_end', 'date_source', 'created_at']
indexes: ['ix_catalysts_run_id', 'ix_catalysts_ticker_expected_date']
```

- [ ] **Step 1.4: Generate the Alembic migration**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend
alembic revision --autogenerate -m "add catalysts table"
```

Expected: a new file appears under `backend/migrations/versions/<short_sha>_add_catalysts_table.py`. Open it and verify the `upgrade()` function creates the `catalysts` table with all 14 columns and both indices, plus a `op.create_index(...)` for `ix_research_runs_ticker_created_at` if Alembic noticed it's missing. If Alembic generated extra unrelated migrations (e.g., dropping unused indices), edit them out — keep ONLY the catalysts table + the research_runs index.

If the autogenerated migration does not include the `(ticker, created_at)` index on `research_runs`, manually append to `upgrade()`:

```python
op.create_index(
    "ix_research_runs_ticker_created_at",
    "research_runs",
    ["ticker", "created_at"],
)
```

And to `downgrade()`:

```python
op.drop_index("ix_research_runs_ticker_created_at", table_name="research_runs")
```

- [ ] **Step 1.5: Apply the migration**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend
alembic upgrade head
```

Expected output ends with `INFO  [alembic.runtime.migration] Running upgrade ... -> <new_rev>, add catalysts table`.

- [ ] **Step 1.6: Verify the migration applied**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
import asyncio
from sqlalchemy import text
from backend.app.db.session import async_session

async def main():
    async with async_session() as db:
        rows = await db.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'catalysts' ORDER BY ordinal_position\"))
        cols = [r[0] for r in rows]
        idx = await db.execute(text(\"SELECT indexname FROM pg_indexes WHERE tablename = 'catalysts'\"))
        names = sorted(r[0] for r in idx)
        print('cols:', cols)
        print('indexes:', names)

asyncio.run(main())
"
```

Expected: `cols` includes all 14 fields; `indexes` includes `ix_catalysts_run_id` and `ix_catalysts_ticker_expected_date` (plus the implicit primary-key index `catalysts_pkey`).

- [ ] **Step 1.7: Commit**

```bash
git add backend/app/models/catalyst.py backend/app/models/__init__.py backend/migrations/versions/
git commit -m "$(cat <<'EOF'
feat(catalysts): add Catalyst model + Alembic migration

Creates the catalysts table with FK to research_runs, two indices
(run_id; ticker + expected_date), and the (ticker, created_at) index on
research_runs needed for the latest-run-per-ticker subquery. Per-run
scoping: each thesis run produces its own rows; re-runs do not merge.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Date parser

**Files:**
- Create: `backend/app/services/catalyst_dates.py`

- [ ] **Step 2.1: Write the parser**

Create `backend/app/services/catalyst_dates.py`:

```python
"""Best-effort mapping of free-form catalyst timeframe strings to date windows.

Sonnet emits creative timeframes — "Q2 2026", "Next 1-3 mo", "H2 2027".
This module handles the common shapes and falls back to (None, None,
"untimed") for the rest. Untimed catalysts surface in a separate bucket
in the calendar UI rather than getting bogus parsed dates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

DateSource = Literal[
    "fmp_earnings",
    "parsed_quarter",
    "parsed_relative",
    "parsed_year",
    "parsed_half",
    "untimed",
]


@dataclass(frozen=True)
class ParsedDates:
    window_start: date | None
    window_end: date | None
    source: DateSource


_QUARTER = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE)
_HALF = re.compile(r"\bH([12])\s+(\d{4})\b", re.IGNORECASE)
_YEAR = re.compile(r"^\s*(\d{4})\s*$")
_RELATIVE = re.compile(
    r"(?:next\s+|in\s+)?(\d+)\s*(?:[-–]\s*(\d+))?\s*(mo|month|months|wk|week|weeks|day|days)\b",
    re.IGNORECASE,
)
_UNTIMED_HINTS = {"pending", "eventually", "tbd", "tbd date", "n/a", "long-term", "long term"}


def parse_timeframe(timeframe: str, anchor: datetime) -> ParsedDates:
    """Parse a Sonnet-emitted timeframe string into a date window.

    Args:
        timeframe: free-form string like "Q2 2026", "Next 1-3 mo".
        anchor: reference datetime for relative timeframes (typically now).

    Returns:
        ParsedDates with window_start/window_end populated when the shape is
        recognised, else (None, None, "untimed").
    """
    s = (timeframe or "").strip()
    if not s or s.lower() in _UNTIMED_HINTS:
        return ParsedDates(None, None, "untimed")

    if (m := _QUARTER.search(s)):
        q, year = int(m.group(1)), int(m.group(2))
        start = date(year, 3 * q - 2, 1)
        end_month = 3 * q
        if end_month == 12:
            end = date(year, 12, 31)
        else:
            end = date(year, end_month + 1, 1) - timedelta(days=1)
        return ParsedDates(start, end, "parsed_quarter")

    if (m := _HALF.search(s)):
        h, year = int(m.group(1)), int(m.group(2))
        if h == 1:
            return ParsedDates(date(year, 1, 1), date(year, 6, 30), "parsed_half")
        return ParsedDates(date(year, 7, 1), date(year, 12, 31), "parsed_half")

    if (m := _YEAR.match(s)):
        year = int(m.group(1))
        return ParsedDates(date(year, 1, 1), date(year, 12, 31), "parsed_year")

    if (m := _RELATIVE.search(s)):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        unit = m.group(3).lower()
        days_per = {
            "day": 1, "days": 1,
            "wk": 7, "week": 7, "weeks": 7,
            "mo": 30, "month": 30, "months": 30,
        }[unit]
        anchor_date = anchor.date()
        return ParsedDates(
            anchor_date + timedelta(days=lo * days_per),
            anchor_date + timedelta(days=hi * days_per),
            "parsed_relative",
        )

    return ParsedDates(None, None, "untimed")
```

- [ ] **Step 2.2: Verify the parser end-to-end**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
from datetime import datetime, date, timezone
from backend.app.services.catalyst_dates import parse_timeframe, ParsedDates

anchor = datetime(2026, 5, 4, tzinfo=timezone.utc)

cases = [
    ('Q2 2026',      ParsedDates(date(2026, 4, 1),  date(2026, 6, 30), 'parsed_quarter')),
    ('Q4 2026',      ParsedDates(date(2026, 10, 1), date(2026, 12, 31), 'parsed_quarter')),
    ('H1 2027',      ParsedDates(date(2027, 1, 1),  date(2027, 6, 30), 'parsed_half')),
    ('H2 2027',      ParsedDates(date(2027, 7, 1),  date(2027, 12, 31), 'parsed_half')),
    ('2027',         ParsedDates(date(2027, 1, 1),  date(2027, 12, 31), 'parsed_year')),
    ('Next 1-3 mo',  ParsedDates(date(2026, 6, 3),  date(2026, 8, 2),  'parsed_relative')),
    ('6-12 mo',      ParsedDates(date(2026, 11, 0o00) if False else date(2026, 11, 0o00) if False else None, None, None)),  # checked below
    ('Pending',      ParsedDates(None, None, 'untimed')),
    ('TBD',          ParsedDates(None, None, 'untimed')),
    ('N/A',          ParsedDates(None, None, 'untimed')),
    ('asdfgh',       ParsedDates(None, None, 'untimed')),
]
for tf, want in cases[:5] + cases[7:]:
    got = parse_timeframe(tf, anchor)
    assert got == want, f'{tf!r} -> {got} (wanted {want})'
    print(f'OK  {tf!r}: {got.source}')

# Relative cases (anchor-dependent — assert shape only)
got = parse_timeframe('Next 1-3 mo', anchor)
assert got.source == 'parsed_relative'
assert got.window_start == date(2026, 6, 3)   # anchor + 30
assert got.window_end   == date(2026, 8, 2)   # anchor + 90
print(f'OK  Next 1-3 mo: {got}')

got = parse_timeframe('6-12 mo', anchor)
assert got.source == 'parsed_relative'
assert got.window_start == date(2026, 10, 31)  # anchor + 180
assert got.window_end   == date(2027, 4, 29)   # anchor + 360
print(f'OK  6-12 mo: {got}')

print()
print('All parser cases pass.')
"
```

Expected: prints `OK <case>` for each, then `All parser cases pass.`. Any assertion failure means the parser logic is wrong — fix and re-run.

- [ ] **Step 2.3: Commit**

```bash
git add backend/app/services/catalyst_dates.py
git commit -m "$(cat <<'EOF'
feat(catalysts): timeframe parser for Q/H/year/relative shapes

parse_timeframe(timeframe, anchor) -> ParsedDates(start, end, source).
Handles Q[1-4] YYYY, H[12] YYYY, bare YYYY, "next N-M mo|wk|days", and
known untimed phrases (Pending, TBD, N/A). Anything else falls back to
(None, None, "untimed") so the calendar UI can put it in a separate
bucket rather than render bogus dates.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: FMP earnings calendar method

**Files:**
- Modify: `backend/app/clients/fmp.py` (add a new method following the existing `get_earnings_transcript` pattern at line ~236).

- [ ] **Step 3.1: Add the method**

Open `backend/app/clients/fmp.py`. Locate `get_earnings_transcript` at line ~236. Immediately above it (or just after it — pick a spot that keeps related methods together), insert:

```python
    async def get_earnings_calendar(
        self, ticker: str, limit: int = 4
    ) -> tuple[list[dict], Citation]:
        """Upcoming earnings dates for a ticker.

        Returns up to `limit` upcoming events, each typically:
        {date: 'YYYY-MM-DD', symbol, eps, epsEstimated, time,
         revenue, revenueEstimated, fiscalDateEnding, ...}.

        FMP's /earning_calendar?symbol={ticker} endpoint may return both
        past and future entries; callers should filter to future dates.
        """
        params = {"symbol": ticker, "limit": limit}
        data = await self._request("earning_calendar", params, ttl=TTL_FUNDAMENTAL)
        if not isinstance(data, list):
            data = []
        citation = self._make_citation(
            "earning_calendar",
            "Earnings Calendar",
            ticker,
            params,
        )
        return data, citation
```

The exact endpoint name is `earning_calendar` (singular `earning_`, matches FMP's existing transcript endpoint naming). If a smoke run in Task 13 returns an empty list for a known ticker (e.g., NVDA), check the endpoint slug — older FMP versions used `earning-calendar` (kebab-case).

- [ ] **Step 3.2: Verify the method imports and is callable**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
import inspect
from backend.app.clients.fmp import FMPClient
sig = inspect.signature(FMPClient.get_earnings_calendar)
print('signature:', sig)
print('source line count:', len(inspect.getsource(FMPClient.get_earnings_calendar).splitlines()))
"
```

Expected: prints something like `signature: (self, ticker: str, limit: int = 4) -> tuple[list[dict], app.models.citation.Citation]` and a small line count (~15-20).

- [ ] **Step 3.3: Commit**

```bash
git add backend/app/clients/fmp.py
git commit -m "$(cat <<'EOF'
feat(fmp): add get_earnings_calendar(ticker, limit=4)

Wraps FMP's earning_calendar endpoint. Returns up to N upcoming earnings
events plus the standard FMP citation. Used by the Tier 1.3 catalyst
upsert path to override expected_date on type=earnings catalysts with
the real next-earnings date.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Catalyst promotion service

**Files:**
- Create: `backend/app/services/catalyst_promotion.py`

- [ ] **Step 4.1: Write the service**

Create `backend/app/services/catalyst_promotion.py`:

```python
"""Promote parsed Catalyst objects from a thesis into first-class DB rows.

Called from node_thesis_construction immediately after parse_structured_output
succeeds. Per-run scoping: each call inserts a fresh set of rows; old
rows from prior runs of the same ticker remain as historical record.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.graph.state import ResearchState
from backend.app.models.catalyst import Catalyst
from backend.app.models.phase_schemas import Catalyst as CatalystSchema, ThesisOutput
from backend.app.services.catalyst_dates import ParsedDates, parse_timeframe

logger = logging.getLogger(__name__)

# Slack window for matching FMP earnings dates against parsed timeframes.
# A "Q2 2026" parsed window ends Jun 30, but the actual earnings print may
# fall a few weeks later (mid-July). Allow this much buffer past window_end.
_FMP_EARNINGS_SLACK_DAYS = 30


def _midpoint(parsed: ParsedDates) -> date | None:
    """Best single date for the calendar from a parsed window.

    Picks the midpoint when both ends are present, falls back to either
    end alone, returns None when both are None.
    """
    if parsed.window_start and parsed.window_end:
        delta_days = (parsed.window_end - parsed.window_start).days
        return date.fromordinal(parsed.window_start.toordinal() + delta_days // 2)
    return parsed.window_start or parsed.window_end


async def _try_fmp_earnings_override(
    fmp: FMPClient, ticker: str, parsed: ParsedDates
) -> date | None:
    """Fetch FMP earnings calendar; return the earliest upcoming earnings
    date that falls inside the parsed window (with a small slack), else None."""
    try:
        events, _ = await fmp.get_earnings_calendar(ticker)
    except Exception as e:  # network / FMP errors are non-fatal
        logger.warning("[%s] FMP earnings calendar fetch failed: %s", ticker, e)
        return None
    if not events:
        return None

    today = datetime.now(timezone.utc).date()

    # Build a window: prefer parsed window, else "next 365 days" as fallback
    if parsed.window_start and parsed.window_end:
        from datetime import timedelta
        lower = max(parsed.window_start, today)
        upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
    else:
        from datetime import timedelta
        lower = today
        upper = today + timedelta(days=365)

    candidates: list[date] = []
    for ev in events:
        raw = ev.get("date") if isinstance(ev, dict) else None
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if lower <= d <= upper:
            candidates.append(d)
    if not candidates:
        return None
    return min(candidates)


async def promote_catalysts(
    state: ResearchState,
    parsed: ThesisOutput,
    fmp: FMPClient,
    db: AsyncSession,
) -> int:
    """Insert one Catalyst row per parsed.catalysts entry. Returns count.

    Anchors relative-date parsing to "now" — ResearchState carries no
    timestamp, and the thesis phase runs minutes after run creation, so
    the difference is negligible.
    """
    relative_anchor = datetime.now(timezone.utc)
    inserted = 0

    for ordinal, c in enumerate(parsed.catalysts, start=1):
        assert isinstance(c, CatalystSchema)
        parsed_dates = parse_timeframe(c.timeframe, relative_anchor)
        expected_date: date | None = _midpoint(parsed_dates)
        date_source = parsed_dates.source

        if c.type == "earnings":
            override = await _try_fmp_earnings_override(fmp, state.ticker, parsed_dates)
            if override is not None:
                expected_date = override
                date_source = "fmp_earnings"

        db.add(Catalyst(
            run_id=state.run_id,
            ticker=state.ticker,
            ordinal=ordinal,
            timeframe=c.timeframe,
            description=c.description,
            type=c.type,
            signposts=list(c.signposts or []),
            linked_pillar=c.linked_pillar,
            expected_date=expected_date,
            expected_window_start=parsed_dates.window_start,
            expected_window_end=parsed_dates.window_end,
            date_source=date_source,
        ))
        inserted += 1

    await db.commit()
    logger.info("[%s] promoted %d catalyst rows for run %s",
                state.ticker, inserted, state.run_id)
    return inserted
```

- [ ] **Step 4.2: Verify imports + helpers**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
from datetime import date, datetime, timezone
from backend.app.services.catalyst_promotion import _midpoint
from backend.app.services.catalyst_dates import ParsedDates

p1 = ParsedDates(date(2026, 4, 1), date(2026, 6, 30), 'parsed_quarter')
print('quarter midpoint:', _midpoint(p1))  # expect ~2026-05-15

p2 = ParsedDates(date(2026, 1, 1), date(2026, 12, 31), 'parsed_year')
print('year midpoint:', _midpoint(p2))  # expect ~2026-07-02

p3 = ParsedDates(None, None, 'untimed')
print('untimed midpoint:', _midpoint(p3))  # expect None

p4 = ParsedDates(date(2027, 1, 15), None, 'parsed_relative')
print('start-only midpoint:', _midpoint(p4))  # expect 2027-01-15
"
```

Expected:

```
quarter midpoint: 2026-05-16
year midpoint: 2026-07-02
untimed midpoint: None
start-only midpoint: 2027-01-15
```

(Quarter midpoint may be 2026-05-15 or 2026-05-16 depending on rounding — either is acceptable.)

- [ ] **Step 4.3: Commit**

```bash
git add backend/app/services/catalyst_promotion.py
git commit -m "$(cat <<'EOF'
feat(catalysts): promote_catalysts service writes thesis catalysts to DB

Turns each parsed.catalysts entry into a Catalyst row. For type=earnings,
fetches FMP's earnings calendar and overrides expected_date with the real
next-earnings date when one falls inside the parsed window (+30d slack).

Errors during FMP fetch are logged and non-fatal: the row still gets
written with the parsed-midpoint date and source remains "parsed_*".

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Wire promotion into the thesis-construction node

**Files:**
- Modify: `backend/app/graph/nodes.py` (around the `node_thesis_construction` function starting at line 1218; specifically just after `parsed = parse_structured_output(response, ThesisOutput)` succeeds).

- [ ] **Step 5.1: Add the import at the top of `nodes.py`**

In the import block near the top of `backend/app/graph/nodes.py`, add (next to the other `services` imports — match the existing style):

```python
from backend.app.services.catalyst_promotion import promote_catalysts
```

Also add this near the other `db.session` / `async_session` imports (look at how other in-node DB writes are structured — `_fetch_filing_sections`, `_fetch_counterparty_context` patterns):

```python
from backend.app.db.session import async_session
```

(If `async_session` is already imported in this file, skip the second import.)

- [ ] **Step 5.2: Insert the promotion call**

Locate `node_thesis_construction` at line ~1218. Inside the `try:` block, immediately after the line:

```python
        parsed, parse_err = parse_structured_output(response, ThesisOutput)
```

…and BEFORE the `if parsed is not None:` branch sets `state.phase_outputs["thesis"]`, add a separate block AFTER `state.phase_outputs["thesis"] = {...}` is written but still INSIDE the `if parsed is not None:` branch. Concretely, the existing block looks like:

```python
        if parsed is not None:
            conviction = parsed.conviction_score
            structured = parsed.model_dump()
        else:
            ...

        state.phase_outputs["thesis"] = {
            "__type__": "PhaseOutput",
            "content": response,
            "structured": structured,
            "conviction_score": conviction,
            "parse_error": parse_err,
        }
        state.conviction_score = conviction
        state.thesis_status = "ON TRACK"
        ...
```

Immediately after `state.thesis_status = "ON TRACK"` and before the existing logger line, add:

```python
        # Tier 1.3: promote parsed catalysts into first-class DB rows.
        # Failure here is non-fatal — JSONB still has the canonical copy.
        if parsed is not None:
            try:
                async with async_session() as cat_db:
                    fmp = FMPClient()  # use the same construction pattern as elsewhere; if there's a shared client on app.state, use that instead
                    await promote_catalysts(state, parsed, fmp, cat_db)
            except Exception as cat_err:
                logger.warning(
                    "[%s] catalyst promotion failed: %s", state.ticker, cat_err
                )
```

Important caveats:
1. `FMPClient` instantiation: check how other call sites in `nodes.py` get their FMP client (often via `app.state.fmp` or a module-level singleton). Reuse that pattern. If unsure, instantiate `FMPClient()` directly — its constructor reads `FMP_API_KEY` from settings.
2. The `async with async_session() as cat_db` block: this matches the existing pattern in `PipelineService._fetch_filing_sections` (per CLAUDE.md). The session must commit explicitly (which `promote_catalysts` already does internally).
3. The wrapping `try/except` is critical: a network failure on the FMP earnings call must NOT fail the thesis run. The JSONB copy is still authoritative.

If the existing nodes.py uses a different DB-session-acquisition idiom, copy that idiom verbatim — do not invent a new one.

- [ ] **Step 5.3: Verify the file imports cleanly**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
from backend.app.graph.nodes import node_thesis_construction
from backend.app.services.catalyst_promotion import promote_catalysts
import inspect
src = inspect.getsource(node_thesis_construction)
assert 'promote_catalysts' in src, 'promote_catalysts not wired into node_thesis_construction'
assert 'except' in src and 'catalyst' in src.lower(), 'promotion call missing its try/except guard'
print('node_thesis_construction wires promote_catalysts correctly')
"
```

Expected output:

```
node_thesis_construction wires promote_catalysts correctly
```

- [ ] **Step 5.4: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(catalysts): wire promote_catalysts into node_thesis_construction

Promotion runs immediately after parse_structured_output succeeds.
Wrapped in try/except so an FMP/DB failure does not fail the thesis run
itself — the JSONB copy in phase_outputs.thesis.structured.catalysts
remains the canonical record.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Catalyst API endpoints

**Files:**
- Create: `backend/app/api/catalysts.py`
- Modify: `backend/app/main.py` (mount the new router).

- [ ] **Step 6.1: Write the API module**

Create `backend/app/api/catalysts.py`:

```python
"""GET /api/catalysts and GET /api/catalysts/{id}.

Returns proximity-bucketed catalysts from the latest completed thesis
run per ticker. Same endpoint serves both the fleet view (no ticker
filter) and the per-ticker view inside /pipeline/[runId].
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db
from backend.app.models.catalyst import Catalyst
from pydantic import BaseModel

router = APIRouter()


class CatalystRow(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    ticker: str
    ordinal: int
    timeframe: str
    description: str
    type: str | None
    signposts: list[str]
    linked_pillar: str | None
    expected_date: date | None
    expected_window_start: date | None
    expected_window_end: date | None
    date_source: str
    created_at: datetime

    @classmethod
    def from_orm_row(cls, row: Catalyst) -> "CatalystRow":
        return cls(
            id=row.id,
            run_id=row.run_id,
            ticker=row.ticker,
            ordinal=row.ordinal,
            timeframe=row.timeframe,
            description=row.description,
            type=row.type,
            signposts=list(row.signposts or []),
            linked_pillar=row.linked_pillar,
            expected_date=row.expected_date,
            expected_window_start=row.expected_window_start,
            expected_window_end=row.expected_window_end,
            date_source=row.date_source,
            created_at=row.created_at,
        )


class CatalystBuckets(BaseModel):
    this_week: list[CatalystRow]
    next_30d: list[CatalystRow]
    next_90d: list[CatalystRow]
    later: list[CatalystRow]
    untimed: list[CatalystRow]


class CatalystListResponse(BaseModel):
    buckets: CatalystBuckets
    total: int


def _bucket(row: CatalystRow, today: date) -> str:
    if row.expected_date is None:
        return "untimed"
    days = (row.expected_date - today).days
    if days < 0:
        return "passed"  # filtered out before bucketing
    if days <= 7:
        return "this_week"
    if days <= 30:
        return "next_30d"
    if days <= 90:
        return "next_90d"
    return "later"


@router.get("/catalysts", response_model=CatalystListResponse)
async def list_catalysts(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> CatalystListResponse:
    """Catalysts from the latest completed thesis run per ticker.

    If `ticker` is supplied, restricts to that ticker.
    """
    today = datetime.now(timezone.utc).date()

    # Latest completed-thesis run per ticker. We treat a run as having
    # completed thesis-construction if its phase_outputs.thesis.structured
    # exists and is non-null (matches what the upsert path needs to fire).
    sql = """
        WITH latest AS (
            SELECT DISTINCT ON (ticker) id, ticker, created_at
            FROM research_runs
            WHERE phase_outputs->'thesis'->>'structured' IS NOT NULL
            ORDER BY ticker, created_at DESC
        )
        SELECT c.*
        FROM catalysts c
        JOIN latest l ON c.run_id = l.id
        WHERE (:ticker IS NULL OR c.ticker = :ticker)
        ORDER BY
            (c.expected_date IS NULL),
            c.expected_date NULLS LAST,
            c.ticker,
            c.ordinal
    """
    result = await db.execute(text(sql), {"ticker": ticker})
    rows = result.mappings().all()

    catalysts: list[CatalystRow] = []
    for row in rows:
        catalysts.append(CatalystRow(
            id=row["id"],
            run_id=row["run_id"],
            ticker=row["ticker"],
            ordinal=row["ordinal"],
            timeframe=row["timeframe"],
            description=row["description"],
            type=row["type"],
            signposts=row["signposts"] or [],
            linked_pillar=row["linked_pillar"],
            expected_date=row["expected_date"],
            expected_window_start=row["expected_window_start"],
            expected_window_end=row["expected_window_end"],
            date_source=row["date_source"],
            created_at=row["created_at"],
        ))

    buckets: dict[str, list[CatalystRow]] = {
        "this_week": [], "next_30d": [], "next_90d": [], "later": [], "untimed": []
    }
    for r in catalysts:
        b = _bucket(r, today)
        if b == "passed":
            continue
        buckets[b].append(r)

    return CatalystListResponse(
        buckets=CatalystBuckets(**buckets),
        total=sum(len(v) for v in buckets.values()),
    )


@router.get("/catalysts/{catalyst_id}", response_model=CatalystRow)
async def get_catalyst(
    catalyst_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CatalystRow:
    row = await db.get(Catalyst, catalyst_id)
    if row is None:
        raise HTTPException(status_code=404, detail="catalyst not found")
    return CatalystRow.from_orm_row(row)
```

If the project already exposes a `get_db` dependency, use it as imported above. If the existing pattern is different (e.g., `async_session` directly), match what the other `backend/app/api/*.py` modules do.

- [ ] **Step 6.2: Mount the router in `main.py`**

Open `backend/app/main.py`. Add the import at the top alongside the existing router imports:

```python
from backend.app.api.catalysts import router as catalysts_router
```

Inside the section where existing routers are mounted (around line 100-105), add:

```python
app.include_router(catalysts_router, prefix="/api")
```

Place it next to the other resource routers (themes, discovery, pipeline, filings, fanouts) — pick a spot that keeps the alphabetical/categorical ordering tidy.

- [ ] **Step 6.3: Verify the routes register**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
from backend.app.main import app
paths = sorted({route.path for route in app.routes if hasattr(route, 'path')})
catalyst_paths = [p for p in paths if 'catalyst' in p.lower()]
print('catalyst routes:', catalyst_paths)
assert '/api/catalysts' in catalyst_paths
assert '/api/catalysts/{catalyst_id}' in catalyst_paths
print('routes mounted OK')
"
```

Expected:

```
catalyst routes: ['/api/catalysts', '/api/catalysts/{catalyst_id}']
routes mounted OK
```

- [ ] **Step 6.4: Commit**

```bash
git add backend/app/api/catalysts.py backend/app/main.py
git commit -m "$(cat <<'EOF'
feat(catalysts): GET /api/catalysts and /api/catalysts/{id}

Returns proximity-bucketed catalysts (this_week / next_30d / next_90d /
later / untimed) from the latest completed thesis run per ticker.
Optional ticker filter scopes to a single ticker for the per-ticker
panel inside /pipeline/[runId]. Past-date catalysts are filtered out.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Backfill script

**Files:**
- Create: `backend/scripts/backfill_catalysts.py`

- [ ] **Step 7.1: Write the script**

Create `backend/scripts/backfill_catalysts.py`:

```python
"""One-shot backfill: walk every research_run with a parsed thesis and
insert Catalyst rows for any run that doesn't have them yet.

Usage:
    cd /Users/ericwyluda/Development/projects/sector-research
    source backend/venv/bin/activate
    python -m backend.scripts.backfill_catalysts
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select

from backend.app.clients.fmp import FMPClient
from backend.app.db.session import async_session
from backend.app.graph.state import ResearchState
from backend.app.models.catalyst import Catalyst
from backend.app.models.phase_schemas import ThesisOutput
from backend.app.models.research_run import ResearchRun
from backend.app.services.catalyst_promotion import promote_catalysts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_catalysts")


async def main() -> int:
    fmp = FMPClient()

    async with async_session() as db:
        result = await db.execute(select(ResearchRun))
        runs = result.scalars().all()

    log.info("scanning %d total runs", len(runs))
    promoted = skipped_no_thesis = skipped_already = parse_failed = 0

    for run in runs:
        po = (run.state or {}).get("phase_outputs", {}) if isinstance(run.state, dict) else {}
        thesis = po.get("thesis", {}) if isinstance(po, dict) else {}
        structured = thesis.get("structured") if isinstance(thesis, dict) else None
        if not structured:
            skipped_no_thesis += 1
            continue

        async with async_session() as db:
            existing = await db.execute(
                select(Catalyst.id).where(Catalyst.run_id == run.id).limit(1)
            )
            if existing.first() is not None:
                skipped_already += 1
                continue

            try:
                parsed = ThesisOutput.model_validate(structured)
            except Exception as e:
                log.warning("[%s] thesis parse failed: %s", run.id, e)
                parse_failed += 1
                continue

            # Reconstruct a minimal ResearchState (we only need ticker + run_id).
            state = ResearchState(
                ticker=run.ticker,
                theme_id=str(run.theme_id) if run.theme_id else "",
                run_id=str(run.id),
            )

            await promote_catalysts(state, parsed, fmp, db)
            promoted += 1
            log.info("[%s/%s] promoted %d catalysts", run.ticker, run.id, len(parsed.catalysts))

    log.info(
        "done: promoted=%d skipped_already=%d skipped_no_thesis=%d parse_failed=%d",
        promoted, skipped_already, skipped_no_thesis, parse_failed,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 7.2: Verify the script imports**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -c "
import importlib
m = importlib.import_module('backend.scripts.backfill_catalysts')
assert hasattr(m, 'main') and callable(m.main)
print('backfill_catalysts module imports cleanly')
"
```

Expected:

```
backfill_catalysts module imports cleanly
```

- [ ] **Step 7.3: Commit (run separately during smoke test)**

```bash
git add backend/scripts/backfill_catalysts.py
git commit -m "$(cat <<'EOF'
feat(catalysts): backfill script for existing thesis JSONB

Walks every research_run with a parsed thesis and inserts Catalyst rows
for any run that doesn't already have them. Idempotent — safe to re-run.
Run manually after migration applies:

    python -m backend.scripts.backfill_catalysts

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

(Do not run the script as part of this task's verification — the script needs the live DB and FMP key. It runs as part of Task 13's smoke test.)

---

## Task 8: Frontend TS types and API client

**Files:**
- Modify: `frontend/lib/api.ts` (add types and client methods at the end of the file).

- [ ] **Step 8.1: Add the types and client methods**

Open `frontend/lib/api.ts`. Append at the bottom (before any default export, if there is one):

```typescript
// ── Catalysts (Tier 1.3) ──────────────────────────────────────────────────────

export type CatalystDateSource =
  | "fmp_earnings"
  | "parsed_quarter"
  | "parsed_relative"
  | "parsed_year"
  | "parsed_half"
  | "untimed";

export interface CatalystRow {
  id: string;
  run_id: string;
  ticker: string;
  ordinal: number;
  timeframe: string;
  description: string;
  type?: CatalystType | null;
  signposts: string[];
  linked_pillar?: string | null;
  expected_date: string | null;          // ISO date "YYYY-MM-DD"
  expected_window_start: string | null;
  expected_window_end: string | null;
  date_source: CatalystDateSource;
  created_at: string;                     // ISO datetime
}

export interface CatalystBuckets {
  this_week: CatalystRow[];
  next_30d: CatalystRow[];
  next_90d: CatalystRow[];
  later: CatalystRow[];
  untimed: CatalystRow[];
}

export interface CatalystListResponse {
  buckets: CatalystBuckets;
  total: number;
}

export async function getCatalysts(ticker?: string): Promise<CatalystListResponse> {
  const url = ticker
    ? `${API_BASE}/api/catalysts?ticker=${encodeURIComponent(ticker)}`
    : `${API_BASE}/api/catalysts`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`getCatalysts ${res.status}`);
  return res.json();
}

export async function getCatalyst(id: string): Promise<CatalystRow> {
  const res = await fetch(`${API_BASE}/api/catalysts/${id}`);
  if (!res.ok) throw new Error(`getCatalyst ${res.status}`);
  return res.json();
}
```

`CatalystType` is already exported from earlier in the file (added in Tier 1.1). `API_BASE` is the existing module-local constant — match its name precisely (it might be called `API_URL` or imported differently; use whatever the existing client functions use).

- [ ] **Step 8.2: Verify lint and types**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
npm run lint
```

Expected: exits 0.

```bash
npx tsc --noEmit
```

Expected: exits 0.

- [ ] **Step 8.3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
feat(api): catalyst row + buckets types and client methods

Adds CatalystRow, CatalystBuckets, CatalystListResponse types mirroring
the new /api/catalysts and /api/catalysts/{id} backend endpoints. Field
names use snake_case matching the backend wire format. Reuses the
CatalystType union introduced in Tier 1.1 for the row's type field.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: CatalystRow + CatalystCalendar components

**Files:**
- Create: `frontend/components/CatalystRow.tsx`
- Create: `frontend/components/CatalystCalendar.tsx`

- [ ] **Step 9.1: Write `CatalystRow.tsx`**

Create `frontend/components/CatalystRow.tsx`:

```tsx
"use client";

/**
 * Single row inside the CatalystCalendar — ticker badge, type pill,
 * description, expected date, signposts toggle. Reused by both the fleet
 * page (/catalysts) and the per-ticker panel inside /pipeline/[runId].
 */

import Link from "next/link";
import { useState } from "react";
import type { CatalystRow as CatalystRowT, CatalystType } from "@/lib/api";

const TYPE_COLORS: Record<CatalystType, string> = {
  earnings:   "bg-[var(--primary)]/10 text-[var(--primary)] border-[var(--primary)]/30",
  product:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  regulatory: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  m_and_a:    "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  macro:      "bg-[var(--text-muted)]/10 text-[var(--text-muted)] border-[var(--text-muted)]/30",
  other:      "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]",
};

const TYPE_LABELS: Record<CatalystType, string> = {
  earnings:   "EARNINGS",
  product:    "PRODUCT",
  regulatory: "REGULATORY",
  m_and_a:    "M&A",
  macro:      "MACRO",
  other:      "OTHER",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  // "2026-05-22" -> "May 22"
  const d = new Date(iso + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function CatalystRow({ row }: { row: CatalystRowT }) {
  const [open, setOpen] = useState(false);
  const hasSignposts = (row.signposts ?? []).length > 0;
  const typeClass = row.type ? TYPE_COLORS[row.type] : "";
  const typeLabel = row.type ? TYPE_LABELS[row.type] : null;
  const isFmp = row.date_source === "fmp_earnings";

  return (
    <div className="grid grid-cols-[64px_72px_1fr_72px] gap-3 items-baseline py-2 border-b border-[var(--border)]/40">
      <Link
        href={`/pipeline/${row.run_id}`}
        className="font-mono font-bold text-[var(--text)] hover:text-[var(--primary)]"
      >
        {row.ticker}
      </Link>
      <div>
        {typeLabel && (
          <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${typeClass}`}>
            {typeLabel}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-[11px] text-[var(--text)] leading-snug">
            {row.description}
          </span>
          {row.linked_pillar && (
            <span className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)]">
              tests {row.linked_pillar}
            </span>
          )}
          {hasSignposts && (
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
              className="text-[9px] font-mono text-[var(--text-faint)] hover:text-[var(--primary)] underline-offset-2"
            >
              {open ? "− signposts" : `+ ${row.signposts.length} signpost${row.signposts.length === 1 ? "" : "s"}`}
            </button>
          )}
        </div>
        {hasSignposts && open && (
          <ul className="ml-3 list-disc text-[10px] text-[var(--text-muted)] leading-relaxed">
            {row.signposts.map((s, j) => <li key={j}>{s}</li>)}
          </ul>
        )}
      </div>
      <div className="text-right">
        <span className={`text-[11px] font-mono ${isFmp ? "text-[var(--primary)]" : "text-[var(--text-muted)]"}`}>
          {formatDate(row.expected_date)}
        </span>
        {row.expected_date && (
          <div className="text-[8px] uppercase tracking-wider text-[var(--text-faint)]">
            {row.date_source.replace(/_/g, " ")}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 9.2: Write `CatalystCalendar.tsx`**

Create `frontend/components/CatalystCalendar.tsx`:

```tsx
"use client";

/**
 * Proximity-bucketed catalyst calendar. Renders five sections (this week,
 * next 30 days, next 90 days, later, untimed) using CatalystRow. Empty
 * sections collapse so a ticker with only one upcoming catalyst doesn't
 * scroll past four blank headers.
 */

import type { CatalystBuckets, CatalystRow as CatalystRowT } from "@/lib/api";
import { CatalystRow } from "@/components/CatalystRow";

const SECTIONS: Array<{ key: keyof CatalystBuckets; label: string }> = [
  { key: "this_week", label: "This week" },
  { key: "next_30d",  label: "Next 30 days" },
  { key: "next_90d",  label: "Next 90 days" },
  { key: "later",     label: "Later" },
  { key: "untimed",   label: "Untimed" },
];

export function CatalystCalendar({ buckets, emptyMessage }: { buckets: CatalystBuckets; emptyMessage?: string }) {
  const total =
    buckets.this_week.length +
    buckets.next_30d.length +
    buckets.next_90d.length +
    buckets.later.length +
    buckets.untimed.length;

  if (total === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <p className="text-xs text-[var(--text-muted)]">
          {emptyMessage ?? "No catalysts yet. Run a thesis to populate the calendar."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {SECTIONS.map(({ key, label }) => {
        const rows: CatalystRowT[] = buckets[key];
        if (rows.length === 0) return null;
        return (
          <section key={key}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
                {label} · {rows.length}
              </span>
              <span className="flex-1 h-px bg-[var(--border)]" />
            </div>
            <div>
              {rows.map((r) => <CatalystRow key={r.id} row={r} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 9.3: Verify lint and types**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
npm run lint && npx tsc --noEmit
```

Expected: both exit 0.

- [ ] **Step 9.4: Commit**

```bash
git add frontend/components/CatalystRow.tsx frontend/components/CatalystCalendar.tsx
git commit -m "$(cat <<'EOF'
feat(catalysts): CatalystRow + CatalystCalendar components

CatalystRow renders one row: ticker (link to pipeline page), type badge,
description, optional pillar reference, optional signposts toggle,
expected date with source breadcrumb. Reuses Tier 1.1 type colour
palette so the visual language stays consistent.

CatalystCalendar groups rows into five proximity buckets; empty sections
collapse so a sparse calendar doesn't scroll past blank headers.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `/catalysts` page

**Files:**
- Create: `frontend/app/catalysts/page.tsx`

- [ ] **Step 10.1: Write the page**

Create `frontend/app/catalysts/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { CatalystCalendar } from "@/components/CatalystCalendar";
import { getCatalysts, type CatalystListResponse } from "@/lib/api";

export default function CatalystsPage() {
  const [data, setData] = useState<CatalystListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCatalysts()
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold text-[var(--text)] tracking-wide">
          Catalysts
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Upcoming events from the latest thesis run for each tracked ticker.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
          {error}
        </div>
      )}

      {data && <CatalystCalendar buckets={data.buckets} />}

      {!data && !error && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <p className="text-xs text-[var(--text-muted)]">Loading…</p>
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 10.2: Verify lint and types**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
npm run lint && npx tsc --noEmit
```

Expected: both exit 0.

- [ ] **Step 10.3: Commit**

```bash
git add frontend/app/catalysts/page.tsx
git commit -m "$(cat <<'EOF'
feat(catalysts): /catalysts page renders fleet-wide calendar

Top-level page that fetches /api/catalysts (no filter), shows the
proximity-bucketed calendar for the latest thesis run per ticker. Each
row is a Link to /pipeline/[run_id] for drill-down.

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Per-ticker `<CatalystCalendar>` panel inside `/pipeline/[runId]`

**Files:**
- Modify: `frontend/app/pipeline/[runId]/page.tsx` (add a new section between the deep-dive dashboard render and the `<ThesisCard>` render at line ~648).

- [ ] **Step 11.1: Add the import and state**

Open `frontend/app/pipeline/[runId]/page.tsx`. In the import block at the top, add:

```tsx
import { CatalystCalendar } from "@/components/CatalystCalendar";
import { getCatalysts, type CatalystBuckets } from "@/lib/api";
```

In the component body where other `useState` declarations live (alongside `thesisStructured`, `riskStructured`, etc.), add:

```tsx
const [catalystBuckets, setCatalystBuckets] = useState<CatalystBuckets | null>(null);
```

In the `useEffect` block that loads the report data — find the path that fires once `ticker` is known — append a second fetch:

```tsx
// Tier 1.3: per-ticker catalyst panel.
useEffect(() => {
  if (!ticker) return;
  let cancelled = false;
  getCatalysts(ticker)
    .then((d) => { if (!cancelled) setCatalystBuckets(d.buckets); })
    .catch(() => { /* non-fatal — panel just hides */ });
  return () => { cancelled = true; };
}, [ticker]);
```

(If the existing file has a single combined `useEffect` for report loading, you can merge into it instead — but a separate `useEffect` keyed on `[ticker]` is cleaner since `ticker` is the only dep.)

- [ ] **Step 11.2: Render the panel**

Locate the `{/* Thesis */}` render block at line ~648. Immediately above it, add:

```tsx
{/* Tier 1.3: catalyst panel for this ticker */}
{catalystBuckets && (
  <section id="catalyst_section">
    <h2 className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
      Catalyst Calendar · {ticker}
    </h2>
    <CatalystCalendar
      buckets={catalystBuckets}
      emptyMessage={`No catalysts yet for ${ticker}.`}
    />
  </section>
)}
```

The header style mirrors the existing `text-[10px] uppercase tracking-wider` headers used elsewhere on this page.

- [ ] **Step 11.3: Verify lint and types**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
npm run lint && npx tsc --noEmit
```

Expected: both exit 0.

- [ ] **Step 11.4: Commit**

```bash
git add frontend/app/pipeline/\[runId\]/page.tsx
git commit -m "$(cat <<'EOF'
feat(catalysts): per-ticker calendar panel inside /pipeline/[runId]

Fetches /api/catalysts?ticker={ticker} and renders the same
CatalystCalendar component above the ThesisCard. Hides silently on
error so the run page still works for tickers with no catalyst rows
(legacy runs before backfill).

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Nav entry

**Files:**
- Modify: `frontend/components/Nav.tsx` (add a new link to `/catalysts`).

- [ ] **Step 12.1: Add the link**

Open `frontend/components/Nav.tsx`. Locate the array (or JSX list) of nav links (likely entries for Themes, Filings, Library — the existing top nav per CLAUDE.md). Add a new entry for Catalysts in the same shape:

```tsx
{ href: "/catalysts", label: "Catalysts" }
```

Insert it next to the other resource links — alphabetical order is fine, or place it after "Filings" since they share a "data overview" feel. Match exactly whatever data structure the existing nav uses.

- [ ] **Step 12.2: Verify lint and types**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
npm run lint && npx tsc --noEmit
```

Expected: both exit 0.

- [ ] **Step 12.3: Commit**

```bash
git add frontend/components/Nav.tsx
git commit -m "$(cat <<'EOF'
feat(catalysts): add Catalysts link to top nav

Part of Tier 1.3 catalyst calendar.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Backend smoke test

**Files:** none modified — verification only.

- [ ] **Step 13.1: Restart the backend**

If a backend is already running from prior work, restart it so it picks up the new router and node wiring:

```bash
cd /Users/ericwyluda/Development/projects/sector-research
# kill existing if any
lsof -ti :8000 | xargs -r kill
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload &
```

Wait for `Uvicorn running on http://127.0.0.1:8000` then continue.

- [ ] **Step 13.2: Run the backfill script**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -m backend.scripts.backfill_catalysts
```

Expected output ends with a line like:

```
done: promoted=N skipped_already=0 skipped_no_thesis=M parse_failed=0
```

`promoted` should equal the number of historical runs that have a parsed thesis structured output. Re-running the script should produce `promoted=0 skipped_already=N` (idempotent).

Re-run to verify idempotency:

```bash
python -m backend.scripts.backfill_catalysts
```

Expected: `promoted=0`, `skipped_already=N` matches the previous `promoted` count.

- [ ] **Step 13.3: Verify the API endpoint**

```bash
curl -s http://localhost:8000/api/catalysts | python3 -m json.tool | head -60
```

Expected: a JSON object with `buckets` (5 keys: this_week, next_30d, next_90d, later, untimed) and `total`. At least one bucket should be non-empty if there are upcoming catalysts in the historical thesis runs.

Filter by ticker:

```bash
curl -s "http://localhost:8000/api/catalysts?ticker=NVDA" | python3 -m json.tool | head -40
```

Expected: only NVDA rows appear in the buckets.

- [ ] **Step 13.4: Run a fresh thesis to confirm live promotion**

Trigger a new thesis run on a ticker that already has historical runs (so the new one supersedes them as "latest"):

```bash
curl -s -X POST http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"NVDA","theme_id":"<existing-theme-id>"}' | python3 -m json.tool
```

Note the new `id` (run_id). Wait ~3 minutes for thesis_construction to complete, then:

```bash
RUN_ID=<id-from-above>
curl -s "http://localhost:8000/api/runs/$RUN_ID" | python3 -c "
import json, sys
r = json.load(sys.stdin)
print('phase:', r.get('phase'))
print('thesis_status:', r.get('thesis_status'))
"
```

Wait until `phase` is past `thesis_construction`. Then verify catalyst rows were created for the new run:

```bash
curl -s "http://localhost:8000/api/catalysts?ticker=NVDA" | python3 -c "
import json, sys
r = json.load(sys.stdin)
all_rows = sum(r['buckets'].values(), [])
print(f'total NVDA rows from latest run: {len(all_rows)}')
for row in all_rows[:3]:
    print(f'  {row[\"timeframe\"]:12} type={row[\"type\"]:10} expected={row[\"expected_date\"]} source={row[\"date_source\"]}')
"
```

Expected: 3-5 rows, all from the new `RUN_ID` (verify that one of the rows has `run_id` matching the new ID). At least one `type=earnings` catalyst should have `date_source="fmp_earnings"` if FMP has upcoming earnings within the parsed window. If FMP data is unavailable, the row falls back to `parsed_*` source — that's expected behaviour, not a failure.

- [ ] **Step 13.5: Capture findings**

If anything misbehaves (parse failures, empty catalysts, FMP errors flooding logs), record the symptoms but continue — Task 13 is a verification gate, not a code-change task. Issues are surfaced for remediation in a follow-up commit, not by editing the steps above.

---

## Task 14: Frontend E2E verification

**Files:** none modified — verification only.

- [ ] **Step 14.1: Restart the frontend dev server**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend
lsof -ti :3000 | xargs -r kill 2>/dev/null
npm run dev
```

Wait for `Ready in N ms`. Open http://localhost:3000 in a browser.

- [ ] **Step 14.2: Verify the Catalysts page**

Navigate to `/catalysts` (or click the new "Catalysts" nav entry). Confirm:

- Header reads "Catalysts" with the subtitle "Upcoming events from the latest thesis run for each tracked ticker."
- At least one section ("This week" / "Next 30 days" / "Next 90 days" / "Later" / "Untimed") renders with rows.
- Empty sections are hidden — you should not see four headers with `· 0` next to them.
- Each row shows: ticker (link), type badge (when set), description, optional `tests bull:N` chip, optional signposts toggle, expected date on the right, and the date_source breadcrumb under the date.
- Rows with `date_source="fmp_earnings"` show the date in the primary colour (slightly highlighted).
- Click a ticker on any row → navigates to `/pipeline/{run_id}`.
- Click a signposts toggle → bullets reveal; aria-expanded toggles correctly (verify in DevTools).

- [ ] **Step 14.3: Verify the per-ticker panel**

On a `/pipeline/{run_id}` page (use the run from Task 13.4), scroll to the Catalyst Calendar section. Confirm:

- Section appears between the deep-dive dashboard and the ThesisCard.
- Header reads "Catalyst Calendar · {TICKER}".
- The same buckets render but only with this ticker's rows.

- [ ] **Step 14.4: Browser console**

Open DevTools (F12 → Console). Confirm:

- No red errors (warnings about React keys or hydration are tolerated; runtime errors are not).
- No 404 / 500 fetches in Network tab.

- [ ] **Step 14.5: Capture findings**

Same as Task 13.5: any issues are flagged for follow-up, not by editing the steps.

---

## Self-review checklist (post-implementation)

- [ ] All 12 implementation tasks committed; smoke (Task 13) and E2E (Task 14) pass.
- [ ] `alembic downgrade -1 && alembic upgrade head` round-trips cleanly (rolls back the catalysts table and the research_runs index, then re-applies).
- [ ] Re-running `python -m backend.scripts.backfill_catalysts` is idempotent (promoted=0, skipped_already=N).
- [ ] If Sonnet emits a frequent unparsed timeframe shape during smoke testing, log it for a future parser regex addition. Don't fix in this branch.
- [ ] Empty-bucket collapse in `CatalystCalendar` works for a ticker with only one upcoming row.
- [ ] FMP-override path is exercised: at least one `type=earnings` row in `/api/catalysts` shows `date_source="fmp_earnings"`. If none, double-check the FMP endpoint slug (`earning_calendar` vs. `earning-calendar`).
