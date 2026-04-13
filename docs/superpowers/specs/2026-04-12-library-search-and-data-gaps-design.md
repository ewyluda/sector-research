# Library Search, Theme Filtering & Data Gaps

**Date:** 2026-04-12
**Status:** Approved

## Problem

The Research Library page lists past runs but lacks search, theme-based filtering, and visibility into data quality issues. Users cannot quickly find all analyses for a given ticker, filter by theme, or identify recurring data gaps that should be fixed at the source.

## Solution

Enhance the existing Library page and backend list endpoint — no new pages or tables. Add ticker search, theme filtering, per-run gap counts, and an aggregate data gaps view.

---

## 1. Backend — Library query enhancements

### `GET /api/runs` — new query params

| Param    | Type   | Behavior |
|----------|--------|----------|
| `ticker` | string | Exact case-insensitive match on `research_runs.ticker` |
| `search` | string | Substring match (`ILIKE '%{search}%'`) on ticker. If both `ticker` and `search` are sent, `ticker` wins |

Existing `status`, `theme_id`, and `limit` params remain. All filters compose via AND.

### `RunSummary` response — new fields

| Field       | Type           | Source |
|-------------|----------------|--------|
| `theme_name` | string \| null | JOIN on `themes` table by `theme_id` |
| `gap_count`  | int            | `len(compute_data_gaps(state))` — computed on read from JSONB |

No schema migration needed. No new tables.

---

## 2. Backend — Data gaps detection

### Gap types

Two severity levels, both derived from existing JSONB state:

1. **Hard errors** — `CategoryError` entries in `phase_outputs` (already have `__type__: "CategoryError"`, category name, and reason).

2. **Soft gaps** — null/empty fields in data the analysis expected:
   - `CuratedFinancials`: `dcf_intrinsic_value` null, `forward_revenue_estimates` empty, `daily_prices` empty, `beta` null, etc.
   - `CategoryResult.structured`: structured output has null fields that should have data (e.g., thesis with no catalysts).
   - Missing citations: a category result with zero associated citations.

### `compute_data_gaps(state: dict) -> list[dict]`

Pure function over existing state. Returns:

```python
{
    "gap_type": "hard_error" | "soft_gap",
    "category": "financial_health",
    "field": "dcf_intrinsic_value",       # null for hard errors
    "description": "DCF valuation data unavailable from FMP"
}
```

### `GET /api/runs/data-gaps`

Aggregates gaps across runs. Optional filters: `theme_id`, `ticker`, `status`.

Response:

```json
{
    "total_runs_scanned": 30,
    "gaps": [
        {
            "gap_type": "soft_gap",
            "category": "financial_health",
            "field": "dcf_intrinsic_value",
            "description": "DCF valuation data unavailable from FMP",
            "occurrences": 12,
            "frequency": 0.40,
            "example_tickers": ["PLTR", "RKLB", "IONQ"]
        }
    ]
}
```

Sorted by `occurrences` descending. `example_tickers` capped at 3.

---

## 3. Frontend — Library page enhancements

### Search bar + theme filter

Added above the existing status filter tabs in a single row:

- **Ticker search input** — text field with search icon, debounced ~300ms. Sends `search` param to `GET /api/runs`. Placeholder: "Search by ticker..."
- **Theme dropdown** — `<select>` populated from `GET /api/themes` on mount. Default "All Themes". Sends `theme_id` filter.

Both compose with status tabs (search "TSL" + status "Complete" + theme "AI Infrastructure" simultaneously).

### RunCard updates

- **Theme name**: subtle label below the ticker in muted text.
- **Gap count**: amber badge showing "N gaps" when `gap_count > 0`, positioned next to the loop count indicator.

### Data Gaps tab

New tab in the existing FilterBar alongside All / Complete / Awaiting / Running / Watchlist.

When selected, replaces the run card list with an aggregate view:

- Fetches `GET /api/runs/data-gaps` (applies current theme filter if set).
- Renders a table: gap description, category, visual frequency bar, occurrence count, 2-3 example tickers as links (clicking filters library to that ticker).
- Sorted by frequency descending.
- Header: "X gaps found across Y runs".

### `api.ts` updates

- Add `theme_name: string | null` and `gap_count: number` to `RunSummary` interface.
- Add `search` param to `pipeline.list()` options.
- Add `pipeline.dataGaps(opts?)` function for the new endpoint.
- Add `DataGapsResponse` and `DataGap` interfaces.

---

## 4. Scope boundaries

### In scope

- Ticker search (substring) and theme filter dropdown on Library page
- `theme_name` and `gap_count` on RunSummary responses
- `compute_data_gaps()` pure function over existing JSONB state
- `GET /api/runs/data-gaps` aggregate endpoint
- Data Gaps tab on Library page with frequency-ranked table
- Frontend type updates

### Out of scope

- Ticker timeline/comparison page (inflection studies — future work, data model supports it)
- Persisted `data_gaps` table (only if query perf becomes an issue)
- Pagination / infinite scroll (fine at `limit=50` for local tool)
- Fuzzy search (substring ILIKE is sufficient)
- Gap alerting or automated fix suggestions
- Changes to pipeline nodes — read-only over existing data
