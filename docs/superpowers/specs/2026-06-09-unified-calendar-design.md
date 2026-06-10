# Unified Calendar — Design Spec

**Date:** 2026-06-09
**Sub-project:** 2 of the investor-portal roadmap (see `docs/superpowers/2026-06-09-investor-portal-handoff.md`)
**Status:** Approved in brainstorming; ready for implementation planning.

## What this is

One calendar surface merging three event streams — FMP economic releases, earnings for "my universe", and thesis catalysts — into the existing `/catalysts` page. The page gains a Calendar/List toggle: Calendar (new, default) is a hybrid week-lanes + agenda view; List is the existing proximity-bucket view, untouched.

## Decisions made (don't re-litigate)

1. **Universe = theme seeds ∪ active theses.** Every ticker in any theme's `seed_tickers` plus every ticker with a latest completed, non-archived research run (the status board's universe). No new watchlist primitive.
2. **Economic events: US-only, `impact == "High"`.** Live-verified 2026-06-09: this yields CPI, PPI, FOMC decision/projections/presser, Michigan sentiment, housing starts — ~14 events per 12 days. No curated whitelist to maintain.
3. **Architecture: stateless merged read model (Approach A).** No new tables, no migration, no scheduler job. Two FMP calls (cached) + one catalysts query at request time.
4. **Page shape: view toggle on `/catalysts`.** Calendar default, List = existing buckets. No new nav entry.
5. **Calendar layout: hybrid.** Current week as 7-column rich-card lanes ("This week"), followed by a day-grouped agenda ("Coming up") with a 14/30/90-day range toggle. Validated via mockup (`.superpowers/brainstorm/52556-1781059441/content/grid-layout-v2.html`).

## Live-verified FMP facts (2026-06-09)

Per the handoff's FMP gotcha, both endpoints were dumped live before this spec:

- `GET /stable/economic-calendar?from=YYYY-MM-DD&to=YYYY-MM-DD` → rows with keys `actual, change, changePercentage, country, currency, date, estimate, event, impact, previous, unit`. `country` is `"US"`; `impact` ∈ `Low | Medium | High`; `date` is `"YYYY-MM-DD HH:MM:SS"` (UTC).
- `GET /stable/earnings-calendar?from=&to=` → global firehose (~760 rows/week, all exchanges) with keys `symbol, date, epsActual, epsEstimated, revenueActual, revenueEstimated, lastUpdated`. `date` is `"YYYY-MM-DD"`. **One date-range call filtered to the universe replaces N per-ticker `get_earnings_calendar` calls.**

## Backend

### FMP client (`backend/app/clients/fmp.py`)

Two new methods, both returning `tuple[data, Citation]` per convention:

- `get_economic_calendar(from_date: str, to_date: str)` → `economic-calendar` endpoint. Returns raw rows (list); filtering is the service's job.
- `get_earnings_calendar_range(from_date: str, to_date: str)` → `earnings-calendar` endpoint (the firehose; distinct from the existing per-symbol `get_earnings_calendar` which stays as-is for its existing consumers).

New TTL constant `TTL_CALENDAR = 21600` (6 h): calendar contents shift slowly, but same-day `actual` values should refresh a few times a day. Both methods use it.

### Service (`backend/app/services/calendar_events.py`)

New module. Read-only; no commits (matches the `peer_sets` "callers own the session" convention).

- `get_universe(db) -> set[str]` — union of:
  - every ticker in every theme's `seed_tickers` (JSONB list), and
  - tickers from the status board's latest-completed-non-archived-runs CTE. Reuse/extract that SQL from `services/status_board.py` rather than duplicating it (extract a shared helper if needed — surgical, don't refactor the board).
  - Tickers normalized upper-case.
- `get_calendar_events(db, fmp, start: date, end: date) -> CalendarResponse` — merge pipeline:
  1. Econ: fetch range, keep `country == "US" and impact == "High"`.
  2. Earnings: fetch firehose range, keep `symbol ∈ universe`. Flag `has_thesis` (ticker in the active-thesis subset of the universe) so the UI knows the EarningsDrawer/workspace link applies.
  3. Catalysts: existing latest-run-per-ticker SQL from `api/catalysts.py`, restricted to rows whose `expected_date` ∈ [start, end]. Windowed rows (`expected_window_end` set) are included when their window overlaps the range and flagged `windowed: true` so the UI can dim them; undated rows are excluded (they live in the List view).
  4. Sort by date, then kind, then ticker.

### Event shape (discriminated union)

```python
CalendarEvent:
  kind: Literal["economic", "earnings", "catalyst"]
  date: date                 # day the event lands on the calendar
  timestamp: datetime | None # econ rows carry intraday time; others None
  ticker: str | None         # None for economic
  title: str                 # event name / ticker / catalyst description
  detail: dict               # kind-specific payload, see below
  citation: Citation | None  # econ + earnings carry FMP citations; catalysts carry none (they cite via their run)

# detail by kind:
#   economic: {estimate, previous, actual, unit}
#   earnings: {eps_estimated, eps_actual, revenue_estimated, revenue_actual, has_thesis}
#   catalyst: {run_id, catalyst_id, type, timeframe, windowed, window_start, window_end, linked_pillar}

CalendarResponse:
  events: list[CalendarEvent]
  universe_size: int
  warnings: list[str]        # partial-failure notes, e.g. "economic calendar unavailable"
```

### API (`backend/app/api/catalysts.py`)

- `GET /api/catalysts/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD` → `CalendarResponse` (Pydantic models in the route module, mirroring how `CatalystRow` lives there today).
- Range validation: `start <= end`, span clamped to ≤ 120 days (covers the 90-day agenda + week padding).
- **Route ordering:** declare `/catalysts/calendar` before `/catalysts/{catalyst_id}` — "calendar" parses as a path param otherwise (same footgun as `peers/compare`; pin with a test).
- Existing `GET /api/catalysts` (buckets) and `GET /api/catalysts/{id}` are untouched.
- FMP singleton: use `request.app.state.fmp` (do NOT instantiate `FMPClient()` in the route).

### Error handling

If either FMP call raises, log it, append a human-readable note to `warnings`, and return the remaining sources — never 500 on a partial failure. The catalysts query failing is a real 500 (local DB; if that's down the whole app is down).

## Frontend

### API client (`frontend/lib/api.ts`)

`getCalendarEvents(start: string, end: string): Promise<CalendarResponse>` + `CalendarEvent` discriminated-union type mirroring the backend shape.

### Components (`frontend/components/catalysts/`)

- `CalendarView.tsx` — client orchestrator. Computes the current week (Mon–Sun) plus the agenda range; one fetch covering both; owns range-toggle (14/30/90d after this week) and type-filter chip state (Econ / Earnings / Catalysts, all on by default); refetches when the range extends. Splits events into this-week vs coming-up.
- `WeekLanes.tsx` — 7-column current-week strip; today's column outlined; rich cards (econ: estimate · prev; earnings: EPS est; catalyst: description).
- `AgendaList.tsx` — day-grouped rows below; windowed catalysts render dimmed at the bottom of the agenda.
- `EventCard.tsx` / `AgendaRow.tsx` — kind-discriminated rendering. Color code: economic purple, earnings blue, catalyst amber — consistent across both sections, with a legend.
- Linking: earnings rows with `has_thesis` link to the status board's earnings flow (`EarningsDrawer`); catalyst rows link to `/pipeline/{run_id}`; economic rows don't link.

### Page (`frontend/app/catalysts/page.tsx`)

Gains a Calendar/List toggle (Calendar default). List renders the existing `CatalystCalendar` with the existing bucket fetch, unchanged. Check `node_modules/next/dist/docs/` for current server/client-component and fetch conventions before editing (Next.js 16 caveat).

New sticky/interactive UI gets `data-print-hide="true"` per the print-view convention.

## Testing

`backend/tests/test_calendar_events.py` (stdlib unittest, run from repo root with venv):

- Universe: seeds ∪ theses union, archived runs excluded, upper-casing, dedup.
- Econ filter: non-US and Medium/Low dropped; High/US kept; date parse (`"YYYY-MM-DD HH:MM:SS"` → date + timestamp).
- Earnings filter: firehose filtered to universe; `has_thesis` flag correct for seed-only vs thesis tickers.
- Catalysts: dated row in/out of range; windowed row overlapping range included + flagged; undated excluded.
- Partial failure: econ fetch raising → earnings + catalysts still returned with a warning; same for earnings.
- Route ordering: `/catalysts/calendar` does not match `/catalysts/{id}` (pin test).
- Range validation: start > end → 422; span > 120 days → 422.

Frontend: no test harness exists in this repo; verify via `npm run build` + `npm run lint` and a manual smoke pass against live data.

## Out of scope

- No watchlist primitive (universe is derived).
- No persisted calendar tables, no scheduler job.
- No changes to the List/bucket view, catalyst promotion, or `catalyst_dates`.
- Medium/Low-impact or non-US economic events (revisit only if High/US proves too sparse in practice).
- Today-dashboard integration (sub-project 3 will consume `GET /api/catalysts/calendar` with a 1-day range).
