# Unified Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge FMP economic releases, universe earnings, and thesis catalysts into one calendar surface on `/catalysts` — hybrid week-lanes + agenda layout behind a Calendar/List toggle.

**Architecture:** Stateless merged read model (spec Approach A): two new FMP client methods (date-range economic + earnings calendars, 6 h TTL cache) plus the existing `catalysts` table, merged at request time by a new read-only `services/calendar_events.py` and served by `GET /api/catalysts/calendar`. No new tables, no migrations, no scheduler. Frontend: new `components/catalysts/` module rendering "This week" lanes + "Coming up" agenda; existing bucket list untouched behind the List toggle.

**Tech Stack:** FastAPI + async SQLAlchemy (raw `text()` SQL), Pydantic v2, stdlib unittest, Next.js 16 App Router + React 19 + Tailwind v4.

**Spec:** `docs/superpowers/specs/2026-06-09-unified-calendar-design.md` — read it first. Live-verified FMP wire facts are recorded there; do not re-derive field names from memory.

**Branch:** `feat/unified-calendar` (create via superpowers:using-git-worktrees at execution start).

**Conventions that bite (from CLAUDE.md / handoff):**
- Backend runs from repo root with venv: `backend/venv/bin/python -m unittest backend.tests.<module> -v`.
- Every FMP client method returns `tuple[data, Citation]`.
- Route ordering: literal paths before path-param routes in the same router (`/catalysts/calendar` before `/catalysts/{catalyst_id}`).
- Use `request.app.state.fmp` in routes — never instantiate `FMPClient()`.
- Services are read-only / commit-free; callers own the session.
- Tickers are upper-cased at every boundary.
- Frontend: every backend call goes through `frontend/lib/api.ts`; Next.js 16 differs from training data — check `frontend/node_modules/next/dist/docs/` before editing pages.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/clients/fmp.py` | Modify | Add `TTL_CALENDAR`, `get_economic_calendar`, `get_earnings_calendar_range` |
| `backend/app/services/calendar_events.py` | Create | Schemas (`CalendarEvent`, `CalendarResponse`, `CitationOut`, `Universe`), pure event builders, universe derivation, catalyst range SQL, merge orchestrator |
| `backend/app/api/catalysts.py` | Modify | Add `GET /catalysts/calendar` route (before `/{catalyst_id}`) |
| `backend/tests/test_fmp_calendar.py` | Create | Client method contract tests |
| `backend/tests/test_calendar_events.py` | Create | Builders, universe, SQL pin, merge/partial-failure tests |
| `backend/tests/test_catalysts_calendar_api.py` | Create | Route ordering + validation + happy path |
| `frontend/lib/api.ts` | Modify | `CalendarEvent` discriminated union, `CalendarResponse`, `getCalendarEvents` |
| `frontend/components/catalysts/calendarDates.ts` | Create | Local-date helpers (Monday-of-week, add days, local ISO) |
| `frontend/components/catalysts/EventCard.tsx` | Create | Kind-discriminated rich card (week lanes) |
| `frontend/components/catalysts/AgendaRow.tsx` | Create | Kind-discriminated agenda row |
| `frontend/components/catalysts/WeekLanes.tsx` | Create | 7-column current-week strip |
| `frontend/components/catalysts/AgendaList.tsx` | Create | Day-grouped "Coming up" + dimmed windowed footer |
| `frontend/components/catalysts/CalendarView.tsx` | Create | Orchestrator: fetch, range toggle, filter chips, week/agenda split |
| `frontend/components/catalysts/CatalystsView.tsx` | Create | Calendar/List toggle wrapper |
| `frontend/app/catalysts/page.tsx` | Modify | Render `CatalystsView` instead of bare `CatalystCalendar` |
| `frontend/app/status/page.tsx` | Modify | Auto-expand EarningsDrawer from `?expand_earnings=<run_id>` |
| `CLAUDE.md`, `TODO.md` | Modify | Document the feature |

Kind color palette (consistent everywhere): economic `#a78bfa` (purple), earnings `#60a5fa` (blue), catalyst `#fbbf24` (amber).

---

### Task 1: FMP client calendar methods

**Files:**
- Modify: `backend/app/clients/fmp.py` (TTL block ~line 31; new methods after `get_earnings_calendar`, ~line 298)
- Test: `backend/tests/test_fmp_calendar.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fmp_calendar.py`:

```python
"""Contract tests for the two date-range calendar methods on FMPClient.

Wire facts live-verified 2026-06-09 (see the unified-calendar spec):
  - /stable/economic-calendar?from=&to=  → rows with country/impact/event/date(+time)/estimate/previous/actual/unit
  - /stable/earnings-calendar?from=&to=  → global firehose rows {symbol, date, epsActual, epsEstimated, revenueActual, revenueEstimated, lastUpdated}
"""
import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.clients.fmp import FMPClient, TTL_CALENDAR


class EconomicCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_economic_calendar_with_range_params(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"event": "CPI YoY"}])

        data, citation = await client.get_economic_calendar("2026-06-08", "2026-06-12")

        endpoint, params = client._request.await_args.args
        self.assertEqual(endpoint, "economic-calendar")
        self.assertEqual(params, {"from": "2026-06-08", "to": "2026-06-12"})
        self.assertEqual(client._request.await_args.kwargs["ttl"], TTL_CALENDAR)
        self.assertEqual(data, [{"event": "CPI YoY"}])
        self.assertEqual(citation.source_name, "FMP /economic-calendar")
        self.assertEqual(citation.tier, 1)

    async def test_non_list_response_returns_empty_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"error": "nope"})

        data, _ = await client.get_economic_calendar("2026-06-08", "2026-06-12")

        self.assertEqual(data, [])


class EarningsCalendarRangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_earnings_calendar_firehose_with_range_params(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "NVDA"}])

        data, citation = await client.get_earnings_calendar_range("2026-06-08", "2026-06-12")

        endpoint, params = client._request.await_args.args
        self.assertEqual(endpoint, "earnings-calendar")
        self.assertEqual(params, {"from": "2026-06-08", "to": "2026-06-12"})
        self.assertEqual(client._request.await_args.kwargs["ttl"], TTL_CALENDAR)
        self.assertEqual(data, [{"symbol": "NVDA"}])
        self.assertEqual(citation.source_name, "FMP /earnings-calendar")

    async def test_non_list_response_returns_empty_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=None)

        data, _ = await client.get_earnings_calendar_range("2026-06-08", "2026-06-12")

        self.assertEqual(data, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_fmp_calendar -v`
Expected: ImportError — `cannot import name 'TTL_CALENDAR'`.

- [ ] **Step 3: Implement**

In `backend/app/clients/fmp.py`, extend the TTL block (after `TTL_TRANSCRIPT = 604800`):

```python
TTL_CALENDAR = 21600    # 6 hours — calendar contents shift slowly, but same-day actuals should refresh a few times daily
```

Add after `get_earnings_calendar` (~line 298), matching the surrounding method style:

```python
    async def get_economic_calendar(
        self, from_date: str, to_date: str
    ) -> tuple[list[dict], Citation]:
        """Economic releases (all countries/impacts) for a date range.

        GET /stable/economic-calendar?from=YYYY-MM-DD&to=YYYY-MM-DD
        Rows: {date: 'YYYY-MM-DD HH:MM:SS' (UTC), country, event, impact
        (Low|Medium|High), estimate, previous, actual, unit, currency,
        change, changePercentage}. Filtering (US/High) is the caller's job.
        """
        params = {"from": from_date, "to": to_date}
        data = await self._request("economic-calendar", params, ttl=TTL_CALENDAR)
        citation = self._make_citation(
            "economic-calendar",
            "Economic Calendar",
            f"{from_date}..{to_date}",
            params,
        )
        return data if isinstance(data, list) else [], citation

    async def get_earnings_calendar_range(
        self, from_date: str, to_date: str
    ) -> tuple[list[dict], Citation]:
        """Global earnings firehose for a date range (all exchanges).

        GET /stable/earnings-calendar?from=&to=
        Rows: {symbol, date: 'YYYY-MM-DD', epsActual, epsEstimated,
        revenueActual, revenueEstimated, lastUpdated}. Distinct from the
        per-symbol get_earnings_calendar (/stable/earnings) — this variant
        ignores `symbol`; callers filter to their universe.
        """
        params = {"from": from_date, "to": to_date}
        data = await self._request("earnings-calendar", params, ttl=TTL_CALENDAR)
        citation = self._make_citation(
            "earnings-calendar",
            "Earnings Calendar",
            f"{from_date}..{to_date}",
            params,
        )
        return data if isinstance(data, list) else [], citation
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/python -m unittest backend.tests.test_fmp_calendar -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/fmp.py backend/tests/test_fmp_calendar.py
git commit -m "feat(fmp): date-range economic + earnings calendar client methods"
```

---

### Task 2: Calendar event schemas + pure builders (economic, earnings)

**Files:**
- Create: `backend/app/services/calendar_events.py`
- Test: `backend/tests/test_calendar_events.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_calendar_events.py`:

```python
"""calendar_events service: pure builders, universe derivation, catalyst
range SQL pin, and merge orchestration with partial-failure warnings."""
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.citation import Citation
from backend.app.services import calendar_events as ce


def _cit() -> Citation:
    return Citation(
        value="2026-06-08..2026-06-22",
        metric="Economic Calendar",
        source_name="FMP /economic-calendar",
        source_url="https://example/economic-calendar",
        tier=1,
    )


class EconEventsTests(unittest.TestCase):
    def test_keeps_only_us_high_impact(self):
        rows = [
            {"country": "US", "impact": "High", "event": "CPI YoY (May)",
             "date": "2026-06-10 12:30:00", "estimate": 4.2, "previous": 3.8,
             "actual": None, "unit": "%"},
            {"country": "US", "impact": "Medium", "event": "CFTC Nasdaq",
             "date": "2026-06-12 19:30:00"},
            {"country": "DE", "impact": "High", "event": "German CPI",
             "date": "2026-06-10 06:00:00"},
        ]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.kind, "economic")
        self.assertEqual(ev.title, "CPI YoY (May)")
        self.assertEqual(ev.date, date(2026, 6, 10))
        self.assertEqual(
            ev.timestamp, datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
        )
        self.assertIsNone(ev.ticker)
        self.assertEqual(ev.detail["estimate"], 4.2)
        self.assertEqual(ev.detail["previous"], 3.8)
        self.assertIsNone(ev.detail["actual"])
        self.assertEqual(ev.citation.source_name, "FMP /economic-calendar")
        self.assertIsInstance(ev.citation.value, str)

    def test_unparseable_date_row_is_skipped(self):
        rows = [{"country": "US", "impact": "High", "event": "X", "date": "junk"}]
        self.assertEqual(ce._econ_events(rows, _cit()), [])

    def test_date_only_string_parses_with_midnight_timestamp(self):
        rows = [{"country": "US", "impact": "High", "event": "X",
                 "date": "2026-06-10"}]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(events[0].date, date(2026, 6, 10))


class EarningsEventsTests(unittest.TestCase):
    def _universe(self):
        return ce.Universe(
            tickers={"NVDA", "ASML"},
            thesis_runs={"NVDA": "run-nvda-1"},
        )

    def test_filters_firehose_to_universe_and_flags_thesis(self):
        rows = [
            {"symbol": "NVDA", "date": "2026-06-10", "epsEstimated": 1.62,
             "epsActual": None, "revenueEstimated": 6.2e10, "revenueActual": None},
            {"symbol": "ASML", "date": "2026-06-09", "epsEstimated": 4.21,
             "epsActual": None, "revenueEstimated": None, "revenueActual": None},
            {"symbol": "3988.T", "date": "2026-06-12"},
        ]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual({e.ticker for e in events}, {"NVDA", "ASML"})
        nvda = next(e for e in events if e.ticker == "NVDA")
        self.assertEqual(nvda.kind, "earnings")
        self.assertEqual(nvda.date, date(2026, 6, 10))
        self.assertTrue(nvda.detail["has_thesis"])
        self.assertEqual(nvda.detail["run_id"], "run-nvda-1")
        asml = next(e for e in events if e.ticker == "ASML")
        self.assertFalse(asml.detail["has_thesis"])
        self.assertIsNone(asml.detail["run_id"])

    def test_lowercase_symbol_matches_universe(self):
        rows = [{"symbol": "nvda", "date": "2026-06-10"}]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual(events[0].ticker, "NVDA")

    def test_bad_date_row_is_skipped(self):
        rows = [{"symbol": "NVDA", "date": "not-a-date"}]
        self.assertEqual(ce._earnings_events(rows, self._universe(), _cit()), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: ImportError — `backend.app.services.calendar_events` does not exist.

- [ ] **Step 3: Implement schemas + the two builders**

Create `backend/app/services/calendar_events.py`:

```python
"""Unified calendar read model: economic releases + universe earnings +
thesis catalysts, merged statelessly at request time.

No tables, no scheduler (spec Approach A). Read-only; never commits —
callers own the session. Spec:
docs/superpowers/specs/2026-06-09-unified-calendar-design.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation
# Private import is deliberate: the status board owns the "active thesis"
# semantics (completed/watchlist, non-archived, theme-attached). Duplicating
# that SQL here is the bigger hazard.
from backend.app.services.status_board import _build_latest_runs_sql

logger = logging.getLogger(__name__)


# ── Wire schemas ──────────────────────────────────────────────────────────────


class CitationOut(BaseModel):
    """JSON-safe projection of the Citation dataclass (value coerced to str
    to match the frontend Citation type)."""

    metric: str
    source_name: str
    source_url: str
    tier: int
    value: str


class CalendarEvent(BaseModel):
    kind: Literal["economic", "earnings", "catalyst"]
    date: date
    timestamp: datetime | None = None   # econ rows carry intraday UTC time
    ticker: str | None = None           # None for economic
    title: str
    detail: dict[str, Any]
    citation: CitationOut | None = None


class CalendarResponse(BaseModel):
    events: list[CalendarEvent]
    universe_size: int
    warnings: list[str]


@dataclass
class Universe:
    """Theme seeds ∪ active theses (spec decision #1)."""

    tickers: set[str]
    thesis_runs: dict[str, str]  # ticker -> latest active run_id


def _citation_out(c: Citation) -> CitationOut:
    return CitationOut(
        metric=c.metric,
        source_name=c.source_name,
        source_url=c.source_url,
        tier=c.tier,
        value=str(c.value),
    )


# ── Pure event builders ───────────────────────────────────────────────────────


def _econ_events(rows: list[dict], citation: Citation) -> list[CalendarEvent]:
    """US high-impact releases only (spec decision #2)."""
    out: list[CalendarEvent] = []
    cit = _citation_out(citation)
    for r in rows:
        if r.get("country") != "US" or r.get("impact") != "High":
            continue
        raw = r.get("date") or ""
        ts: datetime | None = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if ts is None:
            continue
        out.append(CalendarEvent(
            kind="economic",
            date=ts.date(),
            timestamp=ts,
            ticker=None,
            title=r.get("event") or "Economic release",
            detail={
                "estimate": r.get("estimate"),
                "previous": r.get("previous"),
                "actual": r.get("actual"),
                "unit": r.get("unit"),
            },
            citation=cit,
        ))
    return out


def _earnings_events(
    rows: list[dict], universe: Universe, citation: Citation
) -> list[CalendarEvent]:
    """Firehose rows filtered to the universe; thesis tickers carry the
    run_id so the UI can deep-link the EarningsDrawer."""
    out: list[CalendarEvent] = []
    cit = _citation_out(citation)
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if sym not in universe.tickers:
            continue
        try:
            d = date.fromisoformat(str(r.get("date") or ""))
        except ValueError:
            continue
        run_id = universe.thesis_runs.get(sym)
        out.append(CalendarEvent(
            kind="earnings",
            date=d,
            ticker=sym,
            title=sym,
            detail={
                "eps_estimated": r.get("epsEstimated"),
                "eps_actual": r.get("epsActual"),
                "revenue_estimated": r.get("revenueEstimated"),
                "revenue_actual": r.get("revenueActual"),
                "has_thesis": run_id is not None,
                "run_id": run_id,
            },
            citation=cit,
        ))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calendar_events.py backend/tests/test_calendar_events.py
git commit -m "feat(calendar): event schemas + econ/earnings builders"
```

---

### Task 3: Universe derivation

**Files:**
- Modify: `backend/app/services/calendar_events.py`
- Test: `backend/tests/test_calendar_events.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_calendar_events.py`:

```python
class _Result:
    """Mimics the two access patterns the service uses on db.execute results."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)


class GetUniverseTests(unittest.IsolatedAsyncioTestCase):
    async def test_union_of_seeds_and_active_theses_uppercased(self):
        db = AsyncMock()
        db.execute.side_effect = [
            # SELECT seed_tickers FROM themes → one JSONB list per theme
            _Result([["nvda", "ASML"], ["amd"], None]),
            # latest-runs CTE rows (status board semantics)
            _Result([
                {"ticker": "NVDA", "id": "run-nvda-1"},
                {"ticker": "pltr", "id": "run-pltr-1"},
            ]),
        ]

        universe = await ce.get_universe(db)

        self.assertEqual(universe.tickers, {"NVDA", "ASML", "AMD", "PLTR"})
        self.assertEqual(
            universe.thesis_runs,
            {"NVDA": "run-nvda-1", "PLTR": "run-pltr-1"},
        )

    async def test_duplicate_thesis_ticker_keeps_first_run(self):
        # DISTINCT ON (ticker, theme_id) can emit one row per theme for the
        # same ticker; the first row wins (setdefault).
        db = AsyncMock()
        db.execute.side_effect = [
            _Result([]),
            _Result([
                {"ticker": "NVDA", "id": "run-a"},
                {"ticker": "NVDA", "id": "run-b"},
            ]),
        ]

        universe = await ce.get_universe(db)

        self.assertEqual(universe.thesis_runs, {"NVDA": "run-a"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: 2 failures — `ce.get_universe` does not exist.

- [ ] **Step 3: Implement**

Append to `backend/app/services/calendar_events.py`:

```python
# ── Universe ──────────────────────────────────────────────────────────────────


async def get_universe(db: AsyncSession) -> Universe:
    """Theme seeds ∪ active theses (latest completed/watchlist, non-archived
    run per (ticker, theme) — the status board's universe)."""
    tickers: set[str] = set()

    seed_rows = (await db.execute(text("SELECT seed_tickers FROM themes"))).scalars().all()
    for seeds in seed_rows:
        tickers.update(str(s).upper() for s in (seeds or []))

    sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
    run_rows = (await db.execute(text(sql), params)).mappings().all()
    thesis_runs: dict[str, str] = {}
    for r in run_rows:
        thesis_runs.setdefault(str(r["ticker"]).upper(), str(r["id"]))
    tickers.update(thesis_runs)

    return Universe(tickers=tickers, thesis_runs=thesis_runs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calendar_events.py backend/tests/test_calendar_events.py
git commit -m "feat(calendar): universe derivation (theme seeds ∪ active theses)"
```

---

### Task 4: Catalyst range query + merge orchestrator

**Files:**
- Modify: `backend/app/services/calendar_events.py`
- Test: `backend/tests/test_calendar_events.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_calendar_events.py`:

```python
class CatalystRangeSqlTests(unittest.TestCase):
    def test_sql_pins_latest_thesis_cte_and_range_overlap(self):
        sql = ce.CATALYST_RANGE_SQL
        # Same latest-run semantics as the List view (api/catalysts.py)
        self.assertIn(
            "jsonb_typeof(state->'phase_outputs'->'thesis'->'structured') = 'object'",
            sql,
        )
        # Windowed rows: overlap test; dated rows: BETWEEN
        self.assertIn("c.expected_window_end >= :start_date", sql)
        self.assertIn("BETWEEN :start_date AND :end_date", sql)


class CatalystEventsTests(unittest.TestCase):
    def _row(self, **overrides):
        base = {
            "id": "cat-1", "run_id": "run-1", "ticker": "NVDA",
            "ordinal": 1, "timeframe": "Q3 2026", "description": "Rubin volume ship",
            "type": "product", "linked_pillar": None,
            "expected_date": date(2026, 8, 15),
            "expected_window_start": None, "expected_window_end": None,
        }
        base.update(overrides)
        return base

    def test_dated_row_maps_to_event(self):
        events = ce._catalyst_events([self._row()])
        ev = events[0]
        self.assertEqual(ev.kind, "catalyst")
        self.assertEqual(ev.date, date(2026, 8, 15))
        self.assertEqual(ev.ticker, "NVDA")
        self.assertEqual(ev.title, "Rubin volume ship")
        self.assertEqual(ev.detail["run_id"], "run-1")
        self.assertEqual(ev.detail["catalyst_id"], "cat-1")
        self.assertFalse(ev.detail["windowed"])
        self.assertIsNone(ev.citation)  # catalysts cite via their run

    def test_windowed_row_flagged_and_carries_window(self):
        events = ce._catalyst_events([self._row(
            expected_window_start=date(2026, 7, 1),
            expected_window_end=date(2026, 9, 30),
        )])
        ev = events[0]
        self.assertTrue(ev.detail["windowed"])
        self.assertEqual(ev.detail["window_start"], "2026-07-01")
        self.assertEqual(ev.detail["window_end"], "2026-09-30")

    def test_windowed_row_without_midpoint_uses_window_end_as_date(self):
        events = ce._catalyst_events([self._row(
            expected_date=None,
            expected_window_start=date(2026, 7, 1),
            expected_window_end=date(2026, 9, 30),
        )])
        self.assertEqual(events[0].date, date(2026, 9, 30))


class GetCalendarEventsTests(unittest.IsolatedAsyncioTestCase):
    def _db(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _Result([["NVDA"]]),                                  # seeds
            _Result([{"ticker": "NVDA", "id": "run-1"}]),         # latest runs
            _Result([]),                                          # catalysts
        ]
        return db

    async def test_partial_failure_warns_and_returns_other_sources(self):
        fmp = AsyncMock()
        fmp.get_economic_calendar.side_effect = RuntimeError("FMP down")
        fmp.get_earnings_calendar_range.return_value = (
            [{"symbol": "NVDA", "date": "2026-06-10", "epsEstimated": 1.0}],
            _cit(),
        )

        resp = await ce.get_calendar_events(
            self._db(), fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(len(resp.warnings), 1)
        self.assertIn("Economic calendar unavailable", resp.warnings[0])
        self.assertEqual([e.kind for e in resp.events], ["earnings"])
        self.assertEqual(resp.universe_size, 1)

    async def test_events_sorted_by_date_then_kind(self):
        fmp = AsyncMock()
        fmp.get_economic_calendar.return_value = (
            [{"country": "US", "impact": "High", "event": "CPI",
              "date": "2026-06-10 12:30:00"}],
            _cit(),
        )
        fmp.get_earnings_calendar_range.return_value = (
            [{"symbol": "NVDA", "date": "2026-06-09"},
             {"symbol": "NVDA", "date": "2026-06-10"}],
            _cit(),
        )

        resp = await ce.get_calendar_events(
            self._db(), fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(
            [(e.date.isoformat(), e.kind) for e in resp.events],
            [("2026-06-09", "earnings"),
             ("2026-06-10", "economic"),
             ("2026-06-10", "earnings")],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: failures — `CATALYST_RANGE_SQL`, `_catalyst_events`, `get_calendar_events` do not exist.

- [ ] **Step 3: Implement**

Append to `backend/app/services/calendar_events.py`:

```python
# ── Thesis catalysts ──────────────────────────────────────────────────────────

# Same "latest run with structured thesis" CTE as the List view
# (api/catalysts._build_list_catalysts_sql) — kept in sync by the pin test.
# Range filter happens in SQL: windowed rows by overlap, dated rows by BETWEEN.
# Undated rows are excluded by construction (spec: they live in the List view).
CATALYST_RANGE_SQL = """
    WITH latest AS (
        SELECT DISTINCT ON (ticker) id, ticker, created_at
        FROM research_runs
        WHERE jsonb_typeof(state->'phase_outputs'->'thesis'->'structured') = 'object'
        ORDER BY ticker, created_at DESC
    )
    SELECT c.*
    FROM catalysts c
    JOIN latest l ON c.run_id = l.id
    WHERE (
        (c.expected_window_end IS NOT NULL
         AND COALESCE(c.expected_window_start, c.expected_date) <= :end_date
         AND c.expected_window_end >= :start_date)
        OR
        (c.expected_window_end IS NULL
         AND c.expected_date IS NOT NULL
         AND c.expected_date BETWEEN :start_date AND :end_date)
    )
    ORDER BY c.expected_date NULLS LAST, c.ticker, c.ordinal
"""


def _catalyst_events(rows: list[dict]) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for r in rows:
        windowed = r["expected_window_end"] is not None
        d = r["expected_date"] or r["expected_window_end"]
        out.append(CalendarEvent(
            kind="catalyst",
            date=d,
            ticker=r["ticker"],
            title=r["description"],
            detail={
                "run_id": str(r["run_id"]),
                "catalyst_id": str(r["id"]),
                "type": r["type"],
                "timeframe": r["timeframe"],
                "linked_pillar": r["linked_pillar"],
                "windowed": windowed,
                "window_start": r["expected_window_start"].isoformat()
                if r["expected_window_start"] else None,
                "window_end": r["expected_window_end"].isoformat()
                if r["expected_window_end"] else None,
            },
            citation=None,  # catalysts carry provenance via their run
        ))
    return out


# ── Merge orchestrator ────────────────────────────────────────────────────────

_KIND_ORDER = {"economic": 0, "earnings": 1, "catalyst": 2}


async def get_calendar_events(
    db: AsyncSession, fmp: FMPClient, start: date, end: date
) -> CalendarResponse:
    """Merge the three sources. FMP failures degrade to warnings — never
    500 on a partial outage (spec error-handling section)."""
    universe = await get_universe(db)
    events: list[CalendarEvent] = []
    warnings: list[str] = []

    try:
        rows, cit = await fmp.get_economic_calendar(start.isoformat(), end.isoformat())
        events.extend(_econ_events(rows, cit))
    except Exception:
        logger.exception("economic calendar fetch failed")
        warnings.append("Economic calendar unavailable (FMP error)")

    try:
        rows, cit = await fmp.get_earnings_calendar_range(start.isoformat(), end.isoformat())
        events.extend(_earnings_events(rows, universe, cit))
    except Exception:
        logger.exception("earnings calendar fetch failed")
        warnings.append("Earnings calendar unavailable (FMP error)")

    cat_rows = (await db.execute(
        text(CATALYST_RANGE_SQL), {"start_date": start, "end_date": end}
    )).mappings().all()
    events.extend(_catalyst_events(list(cat_rows)))

    events.sort(key=lambda e: (e.date, _KIND_ORDER[e.kind], e.ticker or ""))
    return CalendarResponse(
        events=events,
        universe_size=len(universe.tickers),
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/python -m unittest backend.tests.test_calendar_events -v`
Expected: 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/calendar_events.py backend/tests/test_calendar_events.py
git commit -m "feat(calendar): catalyst range query + three-source merge with partial-failure warnings"
```

---

### Task 5: API endpoint `GET /api/catalysts/calendar`

**Files:**
- Modify: `backend/app/api/catalysts.py`
- Test: `backend/tests/test_catalysts_calendar_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_catalysts_calendar_api.py`:

```python
"""Pins the /api/catalysts/calendar contract: route ordering ('calendar'
must NOT be swallowed by /catalysts/{catalyst_id} — same footgun as
peers /compare), range validation, and response pass-through."""
import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.catalysts import router
from backend.app.db import get_db
from backend.app.services.calendar_events import CalendarEvent, CalendarResponse


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = AsyncMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.state.fmp = AsyncMock()
    return TestClient(app)


def _fake_response() -> CalendarResponse:
    return CalendarResponse(
        events=[CalendarEvent(
            kind="earnings", date=date(2026, 6, 10), ticker="NVDA",
            title="NVDA", detail={"has_thesis": True, "run_id": "run-1"},
        )],
        universe_size=12,
        warnings=[],
    )


class CalendarRouteTests(unittest.TestCase):
    def test_calendar_not_shadowed_by_catalyst_id_route(self):
        # Without correct declaration order, GET /api/catalysts/calendar
        # hits /catalysts/{catalyst_id} with id='calendar'. With it, the
        # missing start/end query params produce a 422 from the calendar
        # route itself.
        client = make_client()
        resp = client.get("/api/catalysts/calendar")
        self.assertEqual(resp.status_code, 422)
        detail = str(resp.json())
        self.assertIn("start", detail)
        self.assertIn("end", detail)

    def test_start_after_end_rejected(self):
        client = make_client()
        resp = client.get("/api/catalysts/calendar?start=2026-06-22&end=2026-06-08")
        self.assertEqual(resp.status_code, 422)

    def test_range_over_120_days_rejected(self):
        client = make_client()
        resp = client.get("/api/catalysts/calendar?start=2026-01-01&end=2026-06-01")
        self.assertEqual(resp.status_code, 422)

    def test_happy_path_passes_through_service_response(self):
        client = make_client()
        with patch(
            "backend.app.api.catalysts.get_calendar_events",
            new=AsyncMock(return_value=_fake_response()),
        ) as svc:
            resp = client.get("/api/catalysts/calendar?start=2026-06-08&end=2026-06-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["universe_size"], 12)
        self.assertEqual(body["events"][0]["kind"], "earnings")
        self.assertEqual(body["events"][0]["detail"]["run_id"], "run-1")
        # service received parsed dates and the shared FMP singleton
        args = svc.await_args.args
        self.assertEqual(args[2], date(2026, 6, 8))
        self.assertEqual(args[3], date(2026, 6, 22))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_catalysts_calendar_api -v`
Expected: FAIL — `/api/catalysts/calendar` falls through to `/catalysts/{catalyst_id}` with `catalyst_id="calendar"`, so the ordering test gets a non-422 response (the mocked `db.get` blows up inside `from_orm_row`), and the validation/happy-path tests fail the same way.

- [ ] **Step 3: Implement the route**

In `backend/app/api/catalysts.py`:

1. Extend imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.app.services.calendar_events import (
    CalendarResponse,
    get_calendar_events,
)
```

2. Add the route **physically above** `@router.get("/catalysts/{catalyst_id}", ...)` (FastAPI matches in declaration order — `"calendar"` parses as a catalyst_id):

```python
@router.get("/catalysts/calendar", response_model=CalendarResponse)
async def get_calendar(
    request: Request,
    start: date = Query(...),
    end: date = Query(...),
    db: AsyncSession = Depends(get_db),
) -> CalendarResponse:
    """Unified calendar: US high-impact econ + universe earnings + thesis
    catalysts for [start, end].

    Declared BEFORE /catalysts/{catalyst_id} — 'calendar' would otherwise
    parse as a catalyst id (same footgun as peers /compare; pinned by test).
    """
    if start > end:
        raise HTTPException(status_code=422, detail="start must be <= end")
    if (end - start).days > 120:
        raise HTTPException(status_code=422, detail="range too large (max 120 days)")
    return await get_calendar_events(db, request.app.state.fmp, start, end)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/venv/bin/python -m unittest backend.tests.test_catalysts_calendar_api backend.tests.test_catalysts_api -v`
Expected: all PASS (including the pre-existing catalysts API tests — the bucket routes are untouched).

- [ ] **Step 5: Live smoke test**

With the backend running (`uvicorn backend.app.main:app --reload` from repo root):

```bash
curl -s "http://127.0.0.1:8000/api/catalysts/calendar?start=2026-06-08&end=2026-06-22" | python3 -m json.tool | head -40
```

Expected: JSON with `events` (econ events present for the FOMC week), `universe_size` > 0, `warnings: []`. Note `127.0.0.1`, not `localhost` (Docker IPv6 collision).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/catalysts.py backend/tests/test_catalysts_calendar_api.py
git commit -m "feat(api): GET /api/catalysts/calendar merged-events endpoint"
```

---

### Task 6: Frontend API types + client function

**Files:**
- Modify: `frontend/lib/api.ts` (types near the existing `CatalystRow`/`CatalystListResponse` block; function next to `getCatalysts`, ~line 1019)

- [ ] **Step 1: Add types and fetcher**

Add near the existing catalyst types:

```typescript
// ── Unified calendar (GET /api/catalysts/calendar) ──────────────────────────

export interface EconomicEventDetail {
  estimate: number | null;
  previous: number | null;
  actual: number | null;
  unit: string | null;
}

export interface EarningsEventDetail {
  eps_estimated: number | null;
  eps_actual: number | null;
  revenue_estimated: number | null;
  revenue_actual: number | null;
  has_thesis: boolean;
  run_id: string | null;
}

export interface CatalystEventDetail {
  run_id: string;
  catalyst_id: string;
  type: string | null;
  timeframe: string;
  linked_pillar: string | null;
  windowed: boolean;
  window_start: string | null;
  window_end: string | null;
}

interface CalendarEventBase {
  date: string;             // YYYY-MM-DD
  timestamp: string | null; // econ rows carry intraday UTC time
  title: string;
  citation: Citation | null;
}

export type CalendarEvent =
  | (CalendarEventBase & { kind: "economic"; ticker: null; detail: EconomicEventDetail })
  | (CalendarEventBase & { kind: "earnings"; ticker: string; detail: EarningsEventDetail })
  | (CalendarEventBase & { kind: "catalyst"; ticker: string; detail: CatalystEventDetail });

export type CalendarEventKind = CalendarEvent["kind"];

export interface CalendarResponse {
  events: CalendarEvent[];
  universe_size: number;
  warnings: string[];
}
```

Add next to `getCatalysts`:

```typescript
export async function getCalendarEvents(
  start: string,
  end: string
): Promise<CalendarResponse> {
  return apiFetch<CalendarResponse>(
    `/api/catalysts/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
  );
}
```

Note: the backend `CitationOut` sends `tier` as `number`; the existing `Citation` interface types it `1 | 2` — backend tier is always 1 here, so reuse `Citation` rather than minting a parallel type.

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npm run lint && npm run build`
Expected: no new lint errors; build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): calendar event types + getCalendarEvents client"
```

---

### Task 7: Presentational components (dates, EventCard, AgendaRow, WeekLanes, AgendaList)

**Files:**
- Create: `frontend/components/catalysts/calendarDates.ts`
- Create: `frontend/components/catalysts/EventCard.tsx`
- Create: `frontend/components/catalysts/AgendaRow.tsx`
- Create: `frontend/components/catalysts/WeekLanes.tsx`
- Create: `frontend/components/catalysts/AgendaList.tsx`

Approved layout reference: `.superpowers/brainstorm/52556-1781059441/content/grid-layout-v2.html` (week lanes w/ rich cards on top, day-grouped agenda below, windowed catalysts dimmed at the agenda's end).

- [ ] **Step 1: Date helpers**

Create `frontend/components/catalysts/calendarDates.ts`. All-local-time on purpose — `toISOString()` would shift evening ET to tomorrow's UTC date:

```typescript
/** Local-date helpers for the calendar. Never use Date.toISOString() for
 * day math here — it converts to UTC and shifts evening local dates. */

export function isoLocal(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function parseIsoLocal(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function mondayOf(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

const DAY_FMT = new Intl.DateTimeFormat("en-US", { weekday: "short", day: "numeric" });
const AGENDA_FMT = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });

export function dayLabel(d: Date): string {
  return DAY_FMT.format(d); // "Tue 9"-style
}

export function agendaLabel(iso: string): string {
  return AGENDA_FMT.format(parseIsoLocal(iso)); // "Tue, Jun 16"-style
}
```

- [ ] **Step 2: EventCard (week lanes)**

Create `frontend/components/catalysts/EventCard.tsx`:

```tsx
import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";

export const KIND_COLOR: Record<CalendarEvent["kind"], string> = {
  economic: "#a78bfa",
  earnings: "#60a5fa",
  catalyst: "#fbbf24",
};

function fmtNum(v: number | null): string | null {
  if (v === null || v === undefined) return null;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  return String(v);
}

export function eventHref(ev: CalendarEvent): string | null {
  if (ev.kind === "earnings" && ev.detail.has_thesis && ev.detail.run_id) {
    return `/status?expand_earnings=${ev.detail.run_id}`;
  }
  if (ev.kind === "catalyst") return `/pipeline/${ev.detail.run_id}`;
  return null;
}

export function eventSubtitle(ev: CalendarEvent): string {
  if (ev.kind === "economic") {
    const parts: string[] = [];
    if (ev.detail.actual !== null) parts.push(`actual ${fmtNum(ev.detail.actual)}`);
    if (ev.detail.estimate !== null) parts.push(`est ${fmtNum(ev.detail.estimate)}`);
    if (ev.detail.previous !== null) parts.push(`prev ${fmtNum(ev.detail.previous)}`);
    return parts.join(" · ");
  }
  if (ev.kind === "earnings") {
    const parts: string[] = [];
    if (ev.detail.eps_actual !== null) parts.push(`EPS ${fmtNum(ev.detail.eps_actual)}`);
    else if (ev.detail.eps_estimated !== null) parts.push(`EPS est ${fmtNum(ev.detail.eps_estimated)}`);
    if (ev.detail.has_thesis) parts.push("thesis tracked");
    return parts.join(" · ") || "Earnings";
  }
  return ev.detail.timeframe;
}

export function EventCard({ event }: { event: CalendarEvent }) {
  const href = eventHref(event);
  const body = (
    <div
      className="rounded-md px-2 py-1.5 mb-1.5 bg-[var(--surface-2,rgba(127,127,127,0.12))] border-l-[3px]"
      style={{ borderLeftColor: KIND_COLOR[event.kind] }}
    >
      <div className="text-[11px] font-medium text-[var(--text)] leading-tight">
        {event.kind === "earnings" ? event.ticker : event.title}
      </div>
      <div className="text-[10px] text-[var(--text-muted)] leading-tight">
        {event.kind === "catalyst" ? event.title : eventSubtitle(event)}
      </div>
      {event.kind === "catalyst" && (
        <div className="text-[9px] text-[var(--text-muted)] opacity-70">{event.ticker}</div>
      )}
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-80">{body}</Link> : body;
}
```

- [ ] **Step 3: AgendaRow**

Create `frontend/components/catalysts/AgendaRow.tsx`:

```tsx
import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";
import { KIND_COLOR, eventHref, eventSubtitle } from "./EventCard";

const KIND_PILL: Record<CalendarEvent["kind"], string> = {
  economic: "ECON",
  earnings: "EARN",
  catalyst: "CAT",
};

export function AgendaRow({
  event,
  dateLabel,
  dimmed = false,
}: {
  event: CalendarEvent;
  dateLabel: string; // empty string when a previous row already showed the day
  dimmed?: boolean;
}) {
  const href = eventHref(event);
  const body = (
    <div
      className={`flex items-baseline gap-2.5 rounded-md px-2.5 py-1.5 mb-1 bg-[var(--surface-2,rgba(127,127,127,0.07))] text-xs ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="w-20 flex-none text-[11px] font-semibold text-[var(--text-muted)]">
        {dateLabel}
      </span>
      <span
        className="flex-none rounded-full px-2 py-px text-[9px] font-semibold text-black"
        style={{ backgroundColor: KIND_COLOR[event.kind] }}
      >
        {KIND_PILL[event.kind]}
      </span>
      <span className="text-[var(--text)]">
        <span className="font-semibold">
          {event.kind === "economic" ? event.title : event.ticker}
        </span>
        {event.kind !== "economic" && (
          <span className="text-[var(--text-muted)]"> — {event.kind === "catalyst" ? event.title : eventSubtitle(event)}</span>
        )}
        {event.kind === "economic" && eventSubtitle(event) && (
          <span className="text-[var(--text-muted)]"> — {eventSubtitle(event)}</span>
        )}
      </span>
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-80">{body}</Link> : body;
}
```

- [ ] **Step 4: WeekLanes**

Create `frontend/components/catalysts/WeekLanes.tsx`:

```tsx
import type { CalendarEvent } from "@/lib/api";
import { EventCard } from "./EventCard";
import { addDays, dayLabel, isoLocal } from "./calendarDates";

export function WeekLanes({
  monday,
  events,
}: {
  monday: Date;
  events: CalendarEvent[]; // already filtered to this week
}) {
  const todayIso = isoLocal(new Date());
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const byDate = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const list = byDate.get(ev.date) ?? [];
    list.push(ev);
    byDate.set(ev.date, list);
  }

  return (
    <div className="grid grid-cols-7 gap-1.5">
      {days.map((d) => {
        const iso = isoLocal(d);
        const isToday = iso === todayIso;
        return (
          <div
            key={iso}
            className={`rounded-md bg-[var(--surface-2,rgba(127,127,127,0.07))] p-1.5 min-h-[140px] ${isToday ? "outline outline-1 outline-blue-400/40" : ""}`}
          >
            <div className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
              {dayLabel(d)}
            </div>
            {(byDate.get(iso) ?? []).map((ev, i) => (
              <EventCard key={`${ev.kind}-${ev.ticker ?? "us"}-${i}`} event={ev} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: AgendaList**

Create `frontend/components/catalysts/AgendaList.tsx`:

```tsx
import type { CalendarEvent } from "@/lib/api";
import { AgendaRow } from "./AgendaRow";
import { agendaLabel } from "./calendarDates";

export function AgendaList({ events }: { events: CalendarEvent[] }) {
  // Windowed catalysts get a dimmed footer block (approved mockup) —
  // their "date" is a window midpoint/end, not a day they happen on.
  const dated = events.filter(
    (e) => !(e.kind === "catalyst" && e.detail.windowed)
  );
  const windowed = events.filter(
    (e) => e.kind === "catalyst" && e.detail.windowed
  );

  if (dated.length === 0 && windowed.length === 0) {
    return (
      <p className="text-xs text-[var(--text-muted)] py-3">
        Nothing on the calendar for this range.
      </p>
    );
  }

  let lastDate = "";
  return (
    <div>
      {dated.map((ev, i) => {
        const label = ev.date === lastDate ? "" : agendaLabel(ev.date);
        lastDate = ev.date;
        return <AgendaRow key={`d-${i}`} event={ev} dateLabel={label} />;
      })}
      {windowed.map((ev, i) => (
        <AgendaRow
          key={`w-${i}`}
          event={ev}
          dateLabel={ev.kind === "catalyst" ? ev.detail.timeframe : ""}
          dimmed
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Verify it compiles**

Run: `cd frontend && npm run lint && npm run build`
Expected: success (components unused so far — that's fine, no lint rule forbids it; if `no-unused-vars` style errors surface, they'll resolve in Task 8 — in that case defer the lint gate to Task 8 but the build must pass).

- [ ] **Step 7: Commit**

```bash
git add frontend/components/catalysts/
git commit -m "feat(frontend): calendar presentational components (week lanes, agenda, event cards)"
```

---

### Task 8: CalendarView orchestrator

**Files:**
- Create: `frontend/components/catalysts/CalendarView.tsx`

- [ ] **Step 1: Implement**

Create `frontend/components/catalysts/CalendarView.tsx`:

```tsx
"use client";

/**
 * Unified calendar: "This week" lanes + "Coming up" agenda.
 * One fetch covers both (Monday of this week → end of week + range).
 * Filter chips gate kinds client-side; range changes refetch.
 */

import { useEffect, useMemo, useState } from "react";
import { getCalendarEvents } from "@/lib/api";
import type { CalendarEventKind, CalendarResponse } from "@/lib/api";
import { WeekLanes } from "./WeekLanes";
import { AgendaList } from "./AgendaList";
import { KIND_COLOR } from "./EventCard";
import { addDays, isoLocal, mondayOf } from "./calendarDates";

const RANGES = [14, 30, 90] as const;
type RangeDays = (typeof RANGES)[number];

const KIND_CHIPS: Array<{ kind: CalendarEventKind; label: string }> = [
  { kind: "economic", label: "Econ" },
  { kind: "earnings", label: "Earnings" },
  { kind: "catalyst", label: "Catalysts" },
];

export function CalendarView() {
  const [rangeDays, setRangeDays] = useState<RangeDays>(14);
  const [kinds, setKinds] = useState<Set<CalendarEventKind>>(
    () => new Set<CalendarEventKind>(["economic", "earnings", "catalyst"])
  );
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const monday = useMemo(() => mondayOf(new Date()), []);
  const sundayIso = useMemo(() => isoLocal(addDays(monday, 6)), [monday]);

  useEffect(() => {
    let cancelled = false;
    getCalendarEvents(isoLocal(monday), isoLocal(addDays(monday, 6 + rangeDays)))
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Could not load calendar.");
      });
    return () => {
      cancelled = true;
    };
  }, [monday, rangeDays]);

  const visible = useMemo(
    () => (data?.events ?? []).filter((e) => kinds.has(e.kind)),
    [data, kinds]
  );
  const thisWeek = visible.filter((e) => e.date <= sundayIso);
  const comingUp = visible.filter((e) => e.date > sundayIso);

  function toggleKind(kind: CalendarEventKind) {
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between" data-print-hide="true">
        <div className="flex gap-3 text-[11px] text-[var(--text-muted)]">
          {KIND_CHIPS.map(({ kind, label }) => (
            <button
              key={kind}
              onClick={() => toggleKind(kind)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 ${
                kinds.has(kind)
                  ? "border-[var(--text-muted)] text-[var(--text)]"
                  : "border-transparent opacity-50"
              }`}
            >
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ backgroundColor: KIND_COLOR[kind] }}
              />
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
          {error}
        </div>
      )}
      {data?.warnings.map((w) => (
        <div
          key={w}
          className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-400"
        >
          {w}
        </div>
      ))}

      <section>
        <h2 className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
          This week
        </h2>
        <WeekLanes monday={monday} events={thisWeek} />
      </section>

      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-[11px] uppercase tracking-widest text-[var(--text-muted)]">
            Coming up
          </h2>
          <div
            className="flex overflow-hidden rounded-md border border-[var(--text-muted)]/30 text-[10px]"
            data-print-hide="true"
          >
            {RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setRangeDays(r)}
                className={`px-2.5 py-1 ${
                  rangeDays === r
                    ? "bg-blue-400/20 font-semibold text-[var(--text)]"
                    : "text-[var(--text-muted)]"
                }`}
              >
                {r} days
              </button>
            ))}
          </div>
        </div>
        <AgendaList events={comingUp} />
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend && npm run lint && npm run build`
Expected: success.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/catalysts/CalendarView.tsx
git commit -m "feat(frontend): CalendarView orchestrator (fetch, range toggle, kind filters)"
```

---

### Task 9: Page integration — Calendar/List toggle on /catalysts

**Files:**
- Create: `frontend/components/catalysts/CatalystsView.tsx`
- Modify: `frontend/app/catalysts/page.tsx`

- [ ] **Step 1: Check Next.js 16 conventions**

Before editing the page, skim the relevant guide (server/client component composition):

```bash
ls frontend/node_modules/next/dist/docs/ | head -30
```

Read whichever doc covers server/client components if anything below looks off. The page stays a server component fetching buckets; the toggle lives in a client child — that pattern is version-safe, but verify nothing about `"use client"` or props serialization changed.

- [ ] **Step 2: CatalystsView toggle wrapper**

Create `frontend/components/catalysts/CatalystsView.tsx`:

```tsx
"use client";

/**
 * Calendar/List toggle for /catalysts. Calendar (default) renders the
 * unified CalendarView; List renders the pre-existing proximity-bucket
 * CatalystCalendar, untouched.
 */

import { useState } from "react";
import type { CatalystBuckets } from "@/lib/api";
import { CatalystCalendar } from "@/components/CatalystCalendar";
import { CalendarView } from "./CalendarView";

export function CatalystsView({ buckets }: { buckets: CatalystBuckets }) {
  const [view, setView] = useState<"calendar" | "list">("calendar");

  return (
    <div className="flex flex-col gap-4">
      <div
        className="flex w-fit overflow-hidden rounded-md border border-[var(--text-muted)]/30 text-[11px]"
        data-print-hide="true"
      >
        {(["calendar", "list"] as const).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`px-3 py-1 capitalize ${
              view === v
                ? "bg-blue-400/20 font-semibold text-[var(--text)]"
                : "text-[var(--text-muted)]"
            }`}
          >
            {v}
          </button>
        ))}
      </div>
      {view === "calendar" ? <CalendarView /> : <CatalystCalendar buckets={buckets} />}
    </div>
  );
}
```

- [ ] **Step 3: Wire into the page**

In `frontend/app/catalysts/page.tsx`, replace the `CatalystCalendar` import and usage:

```tsx
import { CatalystsView } from "@/components/catalysts/CatalystsView";
```

and swap line 42:

```tsx
      {data && <CatalystsView buckets={data.buckets} />}
```

Update the header description (line 31-33) to:

```tsx
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Economic releases, universe earnings, and thesis catalysts in one view.
        </p>
```

- [ ] **Step 4: Verify in the browser**

```bash
cd frontend && npm run lint && npm run build
```

Then with both servers running, load `http://localhost:3000/catalysts`:
- Calendar view renders by default: week lanes with today outlined, agenda below.
- Econ events show (CPI/PPI/FOMC are in the current range — verified live).
- Kind filter chips toggle event types; range toggle refetches.
- List toggle shows the original bucket view unchanged.
- Earnings rows for thesis-tracked names link to `/status?expand_earnings=...`; catalyst rows link to `/pipeline/{run_id}`.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/catalysts/CatalystsView.tsx frontend/app/catalysts/page.tsx
git commit -m "feat(frontend): Calendar/List toggle on /catalysts, calendar default"
```

---

### Task 10: Status page deep link (`?expand_earnings=<run_id>`)

**Files:**
- Modify: `frontend/app/status/page.tsx` (client component; earnings state lives at ~line 263-264, board fetch at ~line 349)

- [ ] **Step 1: Implement the auto-expand effect**

In the component that owns `earningsByRun` / `earningsExpanded` state, add after the earnings-board fetch effect. Read `window.location.search` directly — it avoids the `useSearchParams` Suspense requirement and this runs client-side only:

```tsx
  // Deep link from the unified calendar: /status?expand_earnings=<run_id>
  // auto-opens that run's EarningsDrawer once the board has loaded.
  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("expand_earnings");
    if (runId && earningsByRun[runId]) {
      setEarningsExpanded((prev) => (prev[runId] ? prev : { ...prev, [runId]: true }));
    }
  }, [earningsByRun]);
```

- [ ] **Step 2: Verify in the browser**

`cd frontend && npm run lint && npm run build`, then visit `http://localhost:3000/status?expand_earnings=<a run_id from the earnings board>` — the matching row's EarningsDrawer should be open on load. (Get a run_id from `curl -s "http://127.0.0.1:8000/api/earnings/board?window_days=14"`.) If no earnings are in the 14-day board window, verify the no-op case: page loads cleanly with no console errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/status/page.tsx
git commit -m "feat(status): auto-expand EarningsDrawer via ?expand_earnings deep link"
```

---

### Task 11: Docs, full suite, wrap-up

**Files:**
- Modify: `CLAUDE.md` (the "Status board, catalysts, and questions" section)
- Modify: `TODO.md` ("Done (recent)" log)

- [ ] **Step 1: Update CLAUDE.md**

In the "Status board, catalysts, and questions" section, extend the catalysts bullet:

```markdown
- `GET /api/catalysts/calendar?start=&end=` (`services/calendar_events.py`) → unified calendar: US high-impact economic releases + universe earnings (theme seeds ∪ active theses) + thesis catalysts, merged statelessly at request time (no tables, no scheduler). Two date-range FMP methods (`get_economic_calendar`, `get_earnings_calendar_range`, `TTL_CALENDAR` 6 h). FMP failures degrade to `warnings[]`, never 500. **Route-ordering footgun:** `/catalysts/calendar` must stay declared before `/catalysts/{catalyst_id}` (pinned by test). Frontend: `/catalysts` defaults to the calendar (week lanes + agenda, `components/catalysts/`), with the original bucket list behind the List toggle. Earnings rows deep-link `/status?expand_earnings=<run_id>` to auto-open the EarningsDrawer.
```

- [ ] **Step 2: Update TODO.md**

Add to "Done (recent)" (match the existing entry style in the file):

```markdown
- **Unified calendar (investor-portal sub-project 2)** — `/catalysts` Calendar view: US high-impact econ + universe earnings + thesis catalysts merged by stateless `calendar_events` service; week lanes + agenda UI; EarningsDrawer deep link. Spec: `docs/superpowers/specs/2026-06-09-unified-calendar-design.md`.
```

- [ ] **Step 3: Run the full backend suite**

From repo root:

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: all green (323 pre-existing + ~20 new). Any failure in a pre-existing test is a regression — stop and fix before proceeding.

- [ ] **Step 4: Frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: unified calendar — CLAUDE.md section + TODO done log"
```

- [ ] **Step 6: Finish the branch**

Use superpowers:finishing-a-development-branch — PR against `main` titled `feat: unified calendar — econ + earnings + catalysts on /catalysts`. After merge, update the auto-memory file `project_investor_portal_roadmap.md` (sub-project 2 shipped) per the handoff.

---

## Post-merge follow-ups (do NOT fold into this branch)

- Handoff quick-fix #1 (deep-dive valuation ratios silently None) is independent — separate branch.
- Today dashboard (sub-project 3) consumes `GET /api/catalysts/calendar` with a 1-day range; no extra backend work expected.
