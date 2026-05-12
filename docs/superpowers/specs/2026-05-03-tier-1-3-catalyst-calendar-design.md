# Tier 1.3 — Catalyst Calendar + Signposts

**Date:** 2026-05-03
**Parent roadmap:** `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md`
**Exoskeleton step:** Step 9 — Catalyst Path & Maintenance (sub-actions: Catalyst Calendar, Signposts)
**Depends on:** Tier 1.1 (thesis enrichment) — already shipped on `main`. Catalysts now carry `type`, `signposts`, `linked_pillar` inside `phase_outputs.thesis.structured.catalysts`.
**Status:** Design approved, ready for implementation plan

---

## Context

Tier 1.1 added structured catalyst fields to the thesis output, but catalysts still live as embedded JSONB rows inside `research_runs.state.phase_outputs.thesis.structured.catalysts`. They are not queryable across theses without scanning every run row, the `timeframe` is a free-form string with no date semantics, and there is no way to bind earnings catalysts to actual FMP earnings dates.

Tier 1.3 promotes catalysts to first-class rows in a `catalysts` table, parses timeframes into actual dates, optionally overrides earnings dates with the FMP earnings calendar, and surfaces a cross-thesis vertical-list calendar at `/catalysts` (plus a per-ticker filtered version inside `/pipeline/[runId]`). The per-run scoping model means re-runs naturally produce a fresh set of catalysts; old runs' catalysts stay queryable as historical record but are not "current."

This is the foundation for the Tier 2.6 status board (which will key on `expected_date` proximity) and for Tier 2.5 earnings navigator (which needs accurate next-earnings dates per ticker).

## Strategic decisions captured upstream

- **Source of truth: first-class rows.** New `catalysts` table, FK to `research_runs`. JSONB stays as the audit log; the table is the operational source. Dual write at the end of `node_thesis_construction`.
- **Date semantics: heuristic parser at write time.** The parser maps timeframe strings (`"Q2 2026"`, `"Next 1-3 mo"`, `"H2 2026"`) to date ranges. Sonnet's prompt is unchanged.
- **FMP earnings auto-binding: yes, at upsert time.** For `type=earnings` catalysts, fetch the FMP earnings calendar and override `expected_date` with the real date when one falls inside the parsed window.
- **Lifecycle: per-run scoping + stateless.** Each thesis run produces a fresh set of catalyst rows (FK to `run_id`); display layer derives `upcoming/imminent/passed` from `expected_date` vs. today. No state column. Annotations are deferred to Tier 2.5/2.6 in a separate observation table.
- **Calendar layout: vertical list grouped by proximity.** Sections: This week / Next 30 days / Next 90 days / Later / Untimed. Same component renders the per-ticker view inside `/pipeline/[runId]` with a filter applied.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  node_thesis_construction (existing)                            │
│  ─────────────────────────                                      │
│  Sonnet → parse_structured_output(ThesisOutput) → state.phase_outputs["thesis"] │
│                            │                                    │
│                            ▼  (NEW)                             │
│  ┌─────────────────────────────────────────────────┐            │
│  │ promote_catalysts(state, db)                    │            │
│  │   for catalyst in parsed.catalysts:             │            │
│  │     parse_timeframe(...) → window               │            │
│  │     if type=earnings: FMP override → date       │            │
│  │     INSERT INTO catalysts (...)                 │            │
│  │   await db.commit()                             │            │
│  └─────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  GET /api/catalysts?ticker=...&proximity=...                    │
│  ─────────────────────────────────                              │
│  SELECT … FROM catalysts                                        │
│  WHERE run_id = (latest completed thesis run for ticker)        │
│  GROUP into {this_week, next_30d, next_90d, later, untimed}     │
└─────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  /catalysts (Next.js page)                                      │
│  /pipeline/[runId] (CatalystCalendar panel, ticker-filtered)    │
└─────────────────────────────────────────────────────────────────┘
```

- **No new pipeline nodes.** Upsert is a side effect after `parse_structured_output` succeeds inside `node_thesis_construction`.
- **One Alembic migration** creating the `catalysts` table + indices.
- **Backfill script** populates rows from existing thesis JSONB. Idempotent (skips runs with rows already present).

## Schema

```python
# backend/app/models/catalyst.py
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Catalyst(Base):
    """A catalyst event predicted by a thesis run.

    One row per catalyst per thesis run. Re-running the thesis produces a
    fresh set; old rows remain as historical record.
    """
    __tablename__ = "catalysts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)             # 1..5

    # Sonnet-emitted (Tier 1.1 schema)
    timeframe: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str | None] = mapped_column(String(20))             # earnings|product|regulatory|m_and_a|macro|other|null
    signposts: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    linked_pillar: Mapped[str | None] = mapped_column(String(10))    # "bull:N"|"bear:N"|null

    # Date inference
    expected_date: Mapped[date | None]
    expected_window_start: Mapped[date | None]
    expected_window_end: Mapped[date | None]
    date_source: Mapped[str] = mapped_column(String(20), nullable=False)
    # one of: fmp_earnings | parsed_quarter | parsed_relative | parsed_year | parsed_half | untimed

    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_catalysts_run_id", "run_id"),
        Index("ix_catalysts_ticker_expected_date", "ticker", "expected_date"),
    )
```

Alembic migration adds the table + both indices. No DB triggers; no JSON-column generated columns; no view.

## Date parser

`backend/app/services/catalyst_dates.py`:

```python
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re

DateSource = Literal[
    "fmp_earnings", "parsed_quarter", "parsed_relative",
    "parsed_year", "parsed_half", "untimed",
]

@dataclass(frozen=True)
class ParsedDates:
    window_start: date | None
    window_end: date | None
    source: DateSource

QUARTER = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.IGNORECASE)
HALF    = re.compile(r"\bH([12])\s+(\d{4})\b", re.IGNORECASE)
YEAR    = re.compile(r"^\s*(\d{4})\s*$")
RELATIVE = re.compile(
    r"(?:next\s+|in\s+)?(\d+)\s*(?:[-–]\s*(\d+))?\s*(mo|month|months|wk|week|weeks|day|days)\b",
    re.IGNORECASE,
)
UNTIMED_HINTS = {"pending", "eventually", "tbd", "tbd date", "n/a", "long-term"}

def parse_timeframe(timeframe: str, run_created_at: datetime) -> ParsedDates:
    """Best-effort mapping of a free-form timeframe string to a date window.

    Sonnet emits creative phrasings; this parser handles the common shapes
    and falls back to (None, None, "untimed") for the rest.
    """
    s = (timeframe or "").strip()
    if not s or s.lower() in UNTIMED_HINTS:
        return ParsedDates(None, None, "untimed")
    if (m := QUARTER.search(s)):
        q, year = int(m.group(1)), int(m.group(2))
        start = date(year, 3 * q - 2, 1)
        end_month = 3 * q
        end = date(year + (end_month // 12), (end_month % 12) + 1, 1) - timedelta(days=1)
        return ParsedDates(start, end, "parsed_quarter")
    if (m := HALF.search(s)):
        h, year = int(m.group(1)), int(m.group(2))
        if h == 1:
            return ParsedDates(date(year, 1, 1), date(year, 6, 30), "parsed_half")
        return ParsedDates(date(year, 7, 1), date(year, 12, 31), "parsed_half")
    if (m := YEAR.match(s)):
        year = int(m.group(1))
        return ParsedDates(date(year, 1, 1), date(year, 12, 31), "parsed_year")
    if (m := RELATIVE.search(s)):
        lo, hi = int(m.group(1)), int(m.group(2)) if m.group(2) else int(m.group(1))
        unit = m.group(3).lower()
        days = {"day": 1, "days": 1, "wk": 7, "week": 7, "weeks": 7,
                "mo": 30, "month": 30, "months": 30}[unit]
        anchor = run_created_at.date()
        return ParsedDates(
            anchor + timedelta(days=lo * days),
            anchor + timedelta(days=hi * days),
            "parsed_relative",
        )
    return ParsedDates(None, None, "untimed")
```

Single pure function; ~60 lines including imports. No I/O. Called from the upsert path.

## FMP earnings binding

`backend/app/clients/fmp.py` gains:

```python
async def get_earnings_calendar(self, ticker: str) -> tuple[list[dict], Citation]:
    """Fetch upcoming earnings dates for a ticker from FMP.

    Returns up to 4 quarters of upcoming earnings rows, each with
    {date, eps, epsEstimated, time, revenue, revenueEstimated}.
    """
    # /api/v3/earning_calendar?symbol={ticker}
    ...
```

Existing FMP-citation pattern preserved (`tier=1` for primary FMP). The method follows the same shape as `get_earnings_transcript` already in the file.

## Upsert path

`backend/app/services/catalyst_promotion.py`:

```python
async def promote_catalysts(
    state: ResearchState,
    parsed: ThesisOutput,
    fmp_client: FMPClient,
    db: AsyncSession,
) -> None:
    """Insert one Catalyst row per parsed.catalysts entry. Called from
    node_thesis_construction immediately after a successful parse."""
    # Anchor for relative-date parsing ("Next 1-3 mo"). ResearchState carries no
    # timestamp; the thesis phase runs minutes after run creation, so "now" is a
    # close-enough proxy for the run's created_at.
    relative_anchor = datetime.now(timezone.utc)
    for ordinal, c in enumerate(parsed.catalysts, start=1):
        parsed_dates = parse_timeframe(c.timeframe, relative_anchor)
        expected_date = _midpoint(parsed_dates) if parsed_dates.window_start else None
        date_source = parsed_dates.source

        if c.type == "earnings":
            fmp_match = await _try_fmp_earnings_override(
                fmp_client, state.ticker, parsed_dates,
            )
            if fmp_match is not None:
                expected_date = fmp_match
                date_source = "fmp_earnings"

        db.add(Catalyst(
            run_id=state.run_id,
            ticker=state.ticker,
            ordinal=ordinal,
            timeframe=c.timeframe,
            description=c.description,
            type=c.type,
            signposts=list(c.signposts),
            linked_pillar=c.linked_pillar,
            expected_date=expected_date,
            expected_window_start=parsed_dates.window_start,
            expected_window_end=parsed_dates.window_end,
            date_source=date_source,
        ))
    await db.commit()
```

Helpers:
- `_midpoint(parsed: ParsedDates) -> date | None` — average of start/end (or start if end is null).
- `_try_fmp_earnings_override(client, ticker, window) -> date | None` — fetch the calendar, return the earliest earnings date that falls within `[window_start, window_end + 30 days]` (the +30d slack handles "Q2 2026" overlapping a late-July earnings).

`node_thesis_construction` invokes `promote_catalysts(...)` immediately after `parsed = parse_structured_output(...)` succeeds. On parse failure, no rows are written (matches the existing pattern where structured failures fall through to text content). Errors during promotion are logged but do not fail the run — the JSONB still contains the canonical catalysts.

## Backfill script

`backend/scripts/backfill_catalysts.py`. Walks every `research_run` where `state.phase_outputs.thesis.structured.catalysts` exists. For each run, checks whether any `catalysts` rows already exist for that `run_id`; skips if so. Otherwise reconstructs `ThesisOutput` from the JSONB and calls `promote_catalysts(...)`. Run once after migration applies, then deleted or kept as a maintenance utility.

The script must run from project root with the venv active so `backend.app.*` imports resolve, matching the existing `alembic` invocation pattern.

## Backend API

`backend/app/api/catalysts.py`:

- `GET /api/catalysts?ticker={ticker?}&proximity={all|week|month|quarter|untimed}` — Returns catalysts from the latest *completed* thesis run per ticker. Filters:
  - No ticker → all tickers with completed theses; one row per (ticker, latest run).
  - Ticker → only that ticker's latest run.
  - Proximity → restricts to the matching bucket (default `all`).
  - Response shape:
    ```json
    {
      "buckets": {
        "this_week": [{...row}, ...],
        "next_30d": [...],
        "next_90d": [...],
        "later": [...],
        "untimed": [...]
      },
      "total": 27
    }
    ```
- `GET /api/catalysts/{catalyst_id}` — single row by id; used for deeplinks.

The "latest completed run per ticker" subquery uses a CTE: `WITH latest AS (SELECT DISTINCT ON (ticker) id, ticker FROM research_runs WHERE phase = 'completed' AND ... ORDER BY ticker, created_at DESC) SELECT c.* FROM catalysts c JOIN latest l ON c.run_id = l.id ...`. Indexed via `(ticker, created_at)` on `research_runs` — verify this index exists; add if not.

Bucket assignment is computed in Python after fetch:
- `this_week` → expected_date in `[today, today+7]`
- `next_30d` → `(today+7, today+30]`
- `next_90d` → `(today+30, today+90]`
- `later` → `> today+90`
- `untimed` → `expected_date IS NULL`

Items in the past are excluded from `this_week` (they are filtered out client-side or in a `passed` bucket if added later).

## Frontend

- **New page:** `frontend/app/catalysts/page.tsx` — fetches `/api/catalysts` (no ticker filter), passes the buckets to `CatalystCalendar`.
- **New component:** `frontend/components/CatalystCalendar.tsx` — receives `buckets: CatalystBuckets`. Renders 5 sections (This week / Next 30 days / Next 90 days / Later / Untimed). Each row:
  - Ticker badge (mono, bold, links to `/pipeline/{run_id}`)
  - Type pill (reuses the colour palette from `CatalystList.tsx` — earnings/product/regulatory/m_and_a/macro/other)
  - Description
  - Expected date (right-aligned, mono)
  - Signposts toggle (`+ N signpost(s)` / `− signposts`) using existing `usePersistedCollapse` per-row pattern.
  - On click anywhere on the row → navigate to `/pipeline/{run_id}#thesis_section`.
- **Per-ticker reuse:** add a `<CatalystCalendar>` panel inside `frontend/app/pipeline/[runId]/page.tsx` between the deep-dive dashboard and the ThesisCard. Fetches `/api/catalysts?ticker={ticker}`. Keeps the bucket structure but with a single ticker's worth of rows.
- **Nav entry:** add `"Catalysts"` to `Nav.tsx` linking to `/catalysts`.
- **Types in `lib/api.ts`:** `CatalystRow`, `CatalystBuckets`, plus `getCatalysts(ticker?, proximity?)` and `getCatalyst(id)` client methods. `CatalystRow` mirrors the SQLAlchemy fields with snake_case wire format (`expected_date`, `expected_window_start`, etc.).

## Backwards compatibility

- Old runs work unchanged: catalysts remain in JSONB, frontend ThesisCard still reads from `phase_outputs.thesis.structured.catalysts`. The new `/catalysts` page just doesn't see them until backfill is run.
- After backfill, all historical runs contribute rows. The "latest completed run per ticker" query naturally surfaces only the most recent thesis per ticker, so historical runs remain queryable but don't pollute the current view.
- A run that fails parse_structured_output still works — no catalyst rows are created (matches the existing JSONB-only fallback path).

## Definition of done

1. Alembic migration creates `catalysts` table + indices.
2. New thesis runs auto-promote catalysts to the table at the end of `node_thesis_construction`.
3. Earnings catalysts get real FMP dates when an earnings event falls within the parsed window; non-earnings get parsed dates; unparseable cases land in the `untimed` bucket.
4. `GET /api/catalysts` returns the proximity-bucketed JSON shape.
5. `/catalysts` page renders the vertical-list calendar grouping all catalysts from the latest run per ticker.
6. `/pipeline/[runId]` shows a `<CatalystCalendar>` filtered to the current run's ticker.
7. Nav has a "Catalysts" entry.
8. Backfill script populates rows for all existing completed runs, idempotent on re-run.
9. `npm run lint` and `npx tsc --noEmit` pass; `python -c "from backend.app.models.catalyst import Catalyst"` imports cleanly; alembic migration applies and rolls back cleanly.

## Out of scope (deferred)

- **Catalyst lifecycle annotations** (`fired/missed/dismissed`) — Tier 2.5/2.6. Will live in a separate `catalyst_observations` table keyed on (ticker, type, expected_date) so it survives thesis re-runs.
- **Cross-thesis aggregation by theme** — current API filters by ticker, not theme. Add later if needed.
- **Signpost observation tracking** ("I observed signpost X on date Y") — Tier 2.5.
- **Sliding-window catalyst evolution** (tracking how a catalyst changed across thesis re-runs) — Tier 2.6 if requested.
- **FMP earnings-calendar refresh job** — earnings dates are fetched at upsert time only; future thesis re-runs pick up updates naturally.
- **Tests** — no test framework configured per CLAUDE.md. Verification is manual: trigger a thesis run, inspect the new rows, hit the endpoints, view the page.

## Open questions / risks

- **FMP earnings calendar data quality.** If the endpoint returns stale or missing dates for some tickers, the upsert path silently falls back to the parsed midpoint. Track during smoke testing — if a ticker's calendar is consistently empty, log a warning at upsert time.
- **Date parser coverage.** Sonnet's timeframe phrasings are creative; the regex set above covers ~80% of common shapes. Untimed bucket catches the rest. If a frequent unparsed shape emerges, add a regex (one-line change). Don't reach for fuzzy/LLM parsing unless coverage drops below ~70%.
- **Per-run scoping vs. user expectations.** If a user runs the thesis twice in a day, the second run replaces the first as "current." Confirm via smoke test that re-runs don't leave stale rows visible in the calendar.
- **`research_runs.created_at` index.** The "latest run per ticker" subquery needs `(ticker, created_at)` on `research_runs`. Verify the index exists or add it in this migration.
