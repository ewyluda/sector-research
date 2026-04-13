# Library Search, Theme Filtering & Data Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the Research Library with ticker search, theme filtering, per-run gap counts, and an aggregate data gaps view so users can find past analyses and identify recurring data quality issues.

**Architecture:** Pure read-side enhancements — no new tables or migrations. A `compute_data_gaps()` function scans existing JSONB state for hard errors (CategoryError) and soft gaps (null CuratedFinancials fields + LLM-reported `data_gaps` from deep dive categories). The library API gains search/filter params and a new `/data-gaps` aggregate endpoint. The frontend Library page gets a search bar, theme dropdown, updated cards, and a Data Gaps tab.

**Tech Stack:** FastAPI, SQLAlchemy (async), PostgreSQL JSONB, Next.js App Router, React 19, Tailwind v4

**Note:** No backend test framework is configured. Verification uses curl against the running dev server. Frontend verification uses the browser.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/app/services/data_gaps.py` | `compute_data_gaps()` pure function + `aggregate_data_gaps()` helper |
| Modify | `backend/app/api/pipeline.py:56-134` | Add `ticker`/`search` params, theme join, gap_count to summary, `/data-gaps` endpoint |
| Modify | `frontend/lib/api.ts:120-131,368-374` | Add `theme_name`, `gap_count` to `RunSummary`; `search` to list opts; `dataGaps()` method + types |
| Modify | `frontend/app/library/page.tsx` | Search bar, theme dropdown, RunCard updates, Data Gaps tab |

---

### Task 1: Create `compute_data_gaps()` backend service

**Files:**
- Create: `backend/app/services/data_gaps.py`

This is the core logic — a pure function over the JSONB state dict that returns a list of gap descriptors. Also an aggregation helper that groups gaps across multiple runs.

- [ ] **Step 1: Create `backend/app/services/data_gaps.py` with `compute_data_gaps()`**

```python
"""Data gap detection — pure functions over ResearchState JSONB dicts.

compute_data_gaps(state)  → list of gaps for a single run
aggregate_data_gaps(runs) → frequency-ranked gaps across runs
"""

from __future__ import annotations

# Deep-dive categories that should exist when deep_dive phase completes
_DEEP_DIVE_CATEGORIES = [
    "business_quality", "financial_health", "growth_earnings",
    "management_governance", "technical_market_structure", "macro_regime",
    "sentiment_narrative", "risk_assessment", "future_durability",
]

# CuratedFinancials fields that indicate soft gaps when null/empty
_CURATED_FINANCIAL_GAPS: list[tuple[str, str]] = [
    ("dcf_intrinsic_value", "DCF valuation data unavailable"),
    ("dcf_gap_percent", "DCF gap percentage unavailable"),
    ("forward_revenue_estimates", "No forward revenue estimates (no analyst coverage)"),
    ("forward_eps_estimates", "No forward EPS estimates (no analyst coverage)"),
    ("daily_prices", "No daily price history available"),
    ("beta", "Beta unavailable"),
]


def compute_data_gaps(state: dict) -> list[dict]:
    """Scan a single run's JSONB state and return all detected data gaps.

    Returns list of:
        {"gap_type": "hard_error"|"soft_gap", "category": str,
         "field": str|None, "description": str}
    """
    gaps: list[dict] = []
    phase_outputs = state.get("phase_outputs", {})

    # ── Hard errors: CategoryError entries ────────────────────────────
    for key, val in phase_outputs.items():
        if isinstance(val, dict) and val.get("__type__") == "CategoryError":
            gaps.append({
                "gap_type": "hard_error",
                "category": key,
                "field": None,
                "description": val.get("reason", "Category analysis failed"),
            })

    # ── Soft gaps: CuratedFinancials null/empty fields ────────────────
    curated = state.get("curated_financials")
    if curated and isinstance(curated, dict):
        for field_name, description in _CURATED_FINANCIAL_GAPS:
            value = curated.get(field_name)
            if value is None or (isinstance(value, list) and len(value) == 0):
                gaps.append({
                    "gap_type": "soft_gap",
                    "category": "curated_financials",
                    "field": field_name,
                    "description": description,
                })

    # ── Soft gaps: LLM-reported data_gaps from deep-dive categories ───
    for cat_key in _DEEP_DIVE_CATEGORIES:
        output = phase_outputs.get(cat_key)
        if not isinstance(output, dict) or output.get("__type__") != "CategoryResult":
            continue
        structured = output.get("structured")
        if not isinstance(structured, dict):
            continue
        for gap_desc in structured.get("data_gaps", []):
            if gap_desc:  # skip empty strings
                gaps.append({
                    "gap_type": "soft_gap",
                    "category": cat_key,
                    "field": "data_gaps",
                    "description": gap_desc,
                })

    return gaps


def aggregate_data_gaps(
    runs: list[tuple[str, dict]],
) -> dict:
    """Aggregate gaps across multiple runs.

    Args:
        runs: list of (ticker, state_dict) tuples

    Returns:
        {"total_runs_scanned": int, "gaps": [AggregatedGap...]}
    """
    from collections import defaultdict

    # Key: (gap_type, category, field, description) → {count, tickers}
    counter: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "tickers": set()})

    for ticker, state in runs:
        for gap in compute_data_gaps(state):
            key = (gap["gap_type"], gap["category"], gap["field"], gap["description"])
            counter[key]["count"] += 1
            counter[key]["tickers"].add(ticker)

    total = len(runs)
    aggregated = []
    for (gap_type, category, field_name, description), info in counter.items():
        aggregated.append({
            "gap_type": gap_type,
            "category": category,
            "field": field_name,
            "description": description,
            "occurrences": info["count"],
            "frequency": round(info["count"] / total, 2) if total > 0 else 0,
            "example_tickers": sorted(info["tickers"])[:3],
        })

    aggregated.sort(key=lambda g: g["occurrences"], reverse=True)

    return {"total_runs_scanned": total, "gaps": aggregated}
```

- [ ] **Step 2: Verify the module imports cleanly**

Run from project root:
```bash
source backend/venv/bin/activate && python -c "from backend.app.services.data_gaps import compute_data_gaps, aggregate_data_gaps; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/data_gaps.py
git commit -m "feat: add compute_data_gaps and aggregate_data_gaps services"
```

---

### Task 2: Enhance `GET /api/runs` — ticker search, theme join, gap_count

**Files:**
- Modify: `backend/app/api/pipeline.py:17,22,56-69,118-134`

Add `ticker`/`search` query params, join `Theme` for `theme_name`, and compute `gap_count` per run.

- [ ] **Step 1: Add imports to `pipeline.py`**

At the top of the file, add the Theme model import and the `func` import for `ilike`:

```python
# Add to existing imports (line 17, after the sqlalchemy imports):
from sqlalchemy import select, desc, func

# Add new import after the ResearchState import (line 22):
from backend.app.models.theme import Theme
from backend.app.services.data_gaps import compute_data_gaps
```

Note: `func` is already importable from sqlalchemy — replace the existing `from sqlalchemy import select, desc` line with `from sqlalchemy import select, desc, func`.

- [ ] **Step 2: Update `_run_to_summary` to accept optional theme_name**

Replace the `_run_to_summary` function (lines 56–69) with:

```python
def _run_to_summary(run: ResearchRun, theme_name: str | None = None) -> dict:
    state = run.state or {}
    return {
        "id": run.id,
        "ticker": run.ticker,
        "theme_id": run.theme_id,
        "theme_name": theme_name,
        "phase": run.phase,
        "status": run.status,
        "loop_count": run.loop_count,
        "conviction_score": state.get("conviction_score"),
        "thesis_status": state.get("thesis_status"),
        "gap_count": len(compute_data_gaps(state)),
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
    }
```

- [ ] **Step 3: Update `list_runs` with ticker/search params and theme join**

Replace the `list_runs` function (lines 118–134) with:

```python
@router.get("/runs")
async def list_runs(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    theme_id: str | None = None,
    ticker: str | None = None,
    search: str | None = None,
    limit: int = 50,
):
    """List all research runs for the Research Library."""
    query = (
        select(ResearchRun, Theme.name.label("theme_name"))
        .outerjoin(Theme, ResearchRun.theme_id == Theme.id)
        .order_by(desc(ResearchRun.created_at))
        .limit(limit)
    )
    if status:
        query = query.where(ResearchRun.status == status)
    if theme_id:
        query = query.where(ResearchRun.theme_id == theme_id)
    if ticker:
        query = query.where(func.lower(ResearchRun.ticker) == ticker.lower())
    elif search:
        query = query.where(ResearchRun.ticker.ilike(f"%{search}%"))

    result = await db.execute(query)
    rows = result.all()
    return [_run_to_summary(run, theme_name=tn) for run, tn in rows]
```

- [ ] **Step 4: Verify with curl**

Start the dev server (`uvicorn backend.app.main:app --reload` from project root), then:

```bash
# Basic list (should include theme_name and gap_count)
curl -s http://localhost:8000/api/runs?limit=3 | python -m json.tool

# Search by partial ticker
curl -s "http://localhost:8000/api/runs?search=TS" | python -m json.tool

# Exact ticker match
curl -s "http://localhost:8000/api/runs?ticker=TSLA" | python -m json.tool
```

Expected: JSON responses with `theme_name` (string or null) and `gap_count` (int) on each summary.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/pipeline.py
git commit -m "feat: add ticker search, theme name, and gap count to run listing"
```

---

### Task 3: Add `GET /api/runs/data-gaps` endpoint

**Files:**
- Modify: `backend/app/api/pipeline.py` (append new route)

- [ ] **Step 1: Add the `/runs/data-gaps` route**

Add this route **before** the `/runs/{run_id}` route (important — FastAPI matches routes top-down, and `/runs/data-gaps` would match `{run_id}` if it comes after). Insert after the `list_runs` function:

```python
@router.get("/runs/data-gaps")
async def get_data_gaps(
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    theme_id: str | None = None,
    ticker: str | None = None,
):
    """Aggregate data gaps across all runs, ranked by frequency."""
    query = select(ResearchRun)
    if status:
        query = query.where(ResearchRun.status == status)
    if theme_id:
        query = query.where(ResearchRun.theme_id == theme_id)
    if ticker:
        query = query.where(func.lower(ResearchRun.ticker) == ticker.lower())

    result = await db.execute(query)
    runs_list = [
        (run.ticker, run.state or {}) for run in result.scalars().all()
    ]

    from backend.app.services.data_gaps import aggregate_data_gaps
    return aggregate_data_gaps(runs_list)
```

- [ ] **Step 2: Verify route ordering**

Confirm that in the file, the routes appear in this order:
1. `POST /runs` (start_run)
2. `GET /runs` (list_runs)
3. `GET /runs/data-gaps` (get_data_gaps) ← NEW, must be before `{run_id}` routes
4. `GET /runs/{run_id}` (get_run)
5. `POST /runs/{run_id}/advance`
6. `GET /runs/{run_id}/stream`
7. `GET /runs/{run_id}/report`

- [ ] **Step 3: Verify with curl**

```bash
# All gaps across all runs
curl -s http://localhost:8000/api/runs/data-gaps | python -m json.tool

# Gaps filtered to completed runs only
curl -s "http://localhost:8000/api/runs/data-gaps?status=completed" | python -m json.tool
```

Expected: `{"total_runs_scanned": N, "gaps": [...]}` with gaps sorted by occurrences descending.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/pipeline.py
git commit -m "feat: add /runs/data-gaps aggregate endpoint"
```

---

### Task 4: Update frontend API types and methods

**Files:**
- Modify: `frontend/lib/api.ts:120-131,368-374`

- [ ] **Step 1: Add `theme_name` and `gap_count` to `RunSummary`**

In `frontend/lib/api.ts`, update the `RunSummary` interface (lines 120–131). Add two fields after `thesis_status`:

```typescript
export interface RunSummary {
  id: string;
  ticker: string;
  theme_id: string;
  theme_name: string | null;
  phase: string;
  status: PhaseStatus;
  loop_count: number;
  conviction_score: number | null;
  thesis_status: ThesisStatus | null;
  gap_count: number;
  created_at: string | null;
  updated_at: string | null;
}
```

- [ ] **Step 2: Add `DataGap` and `DataGapsResponse` types**

Add these types after the `RunSummary` interface (before the phase-specific structured output types):

```typescript
export interface DataGap {
  gap_type: "hard_error" | "soft_gap";
  category: string;
  field: string | null;
  description: string;
  occurrences: number;
  frequency: number;
  example_tickers: string[];
}

export interface DataGapsResponse {
  total_runs_scanned: number;
  gaps: DataGap[];
}
```

- [ ] **Step 3: Update `pipeline.list()` to accept `search` param**

Update the `list` method in the `pipeline` object (around line 368) to add `search`:

```typescript
  list: (opts?: { status?: string; theme_id?: string; search?: string; limit?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
    if (opts?.search)   params.set("search",   opts.search);
    if (opts?.limit)    params.set("limit",    String(opts.limit));
    return apiFetch<RunSummary[]>(`/api/runs?${params}`);
  },
```

- [ ] **Step 4: Add `pipeline.dataGaps()` method**

Add after the `list` method in the `pipeline` object:

```typescript
  dataGaps: (opts?: { status?: string; theme_id?: string; ticker?: string }) => {
    const params = new URLSearchParams();
    if (opts?.status)   params.set("status",   opts.status);
    if (opts?.theme_id) params.set("theme_id", opts.theme_id);
    if (opts?.ticker)   params.set("ticker",   opts.ticker);
    return apiFetch<DataGapsResponse>(`/api/runs/data-gaps?${params}`);
  },
```

- [ ] **Step 5: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new type errors (existing errors, if any, should not increase).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add search, theme_name, gap_count, and dataGaps to API client"
```

---

### Task 5: Library page — search bar and theme dropdown

**Files:**
- Modify: `frontend/app/library/page.tsx`

- [ ] **Step 1: Add theme and search imports/state**

Update the imports (line 1–6) and add state for search, themes, and the active theme filter. Replace the existing imports and add new state to the component:

At the top of the file, update the import from `@/lib/api`:

```typescript
import { pipeline as api, themes as themesApi } from "@/lib/api";
import type { RunSummary, ThesisStatus, Theme } from "@/lib/api";
```

In the `LibraryPage` component (around line 162), add new state after the existing state declarations:

```typescript
  const [search, setSearch] = useState("");
  const [themeId, setThemeId] = useState<string>("");
  const [themeList, setThemeList] = useState<Theme[]>([]);
```

- [ ] **Step 2: Fetch themes on mount**

Add a `useEffect` to load themes once, after the existing `useEffect`:

```typescript
  useEffect(() => {
    themesApi.list().then(setThemeList).catch(() => {});
  }, []);
```

- [ ] **Step 3: Update the runs-fetching useEffect to include search and themeId**

Replace the existing `useEffect` that fetches runs (lines 167–172):

```typescript
  useEffect(() => {
    setLoading(true);
    const opts: Record<string, string | number> = {};
    if (filter !== "all") opts.status = filter;
    if (themeId) opts.theme_id = themeId;
    if (search.trim()) opts.search = search.trim();
    api.list(opts as Parameters<typeof api.list>[0])
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [filter, themeId, search]);
```

- [ ] **Step 4: Add search bar and theme dropdown to the JSX**

Insert a new row between the header and the filter bar (between the closing `</div>` of the header section and the `{/* Filter bar */}` comment, around line 205):

```tsx
        {/* Search & theme filter */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search by ticker..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                         text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]
                         focus:outline-none focus:border-[var(--color-accent)]/50 transition-colors"
            />
          </div>
          <select
            value={themeId}
            onChange={(e) => setThemeId(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                       text-sm text-[var(--color-text-primary)]
                       focus:outline-none focus:border-[var(--color-accent)]/50 transition-colors"
          >
            <option value="">All Themes</option>
            {themeList.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
```

- [ ] **Step 5: Add debounce to search input**

To avoid firing a request on every keystroke, add a debounced search value. Add this state and effect before the runs-fetching `useEffect`:

```typescript
  const [debouncedSearch, setDebouncedSearch] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);
```

Then update the runs-fetching `useEffect` to depend on `debouncedSearch` instead of `search`:

```typescript
  useEffect(() => {
    setLoading(true);
    const opts: Record<string, string | number> = {};
    if (filter !== "all") opts.status = filter;
    if (themeId) opts.theme_id = themeId;
    if (debouncedSearch.trim()) opts.search = debouncedSearch.trim();
    api.list(opts as Parameters<typeof api.list>[0])
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [filter, themeId, debouncedSearch]);
```

- [ ] **Step 6: Verify in browser**

Start both servers, open `http://localhost:3000/library`. Confirm:
- Search input appears and filters runs as you type (with ~300ms debounce)
- Theme dropdown populates with themes and filters the list
- Status tabs still work and compose with search + theme

- [ ] **Step 7: Commit**

```bash
git add frontend/app/library/page.tsx
git commit -m "feat: add ticker search and theme filter to library page"
```

---

### Task 6: RunCard — show theme_name and gap_count badge

**Files:**
- Modify: `frontend/app/library/page.tsx` (RunCard component, lines 86–156)

- [ ] **Step 1: Add theme_name label to RunCard**

Inside the RunCard component, add the theme name below the ticker line. After the `<div>` containing ticker + badges (after the closing `</div>` at line 117), and before the metadata row (line 119), insert:

```tsx
          {run.theme_name && (
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">{run.theme_name}</p>
          )}
```

- [ ] **Step 2: Add gap_count badge next to loop count**

Inside the badges row (after the loop count badge, around line 116), add:

```tsx
            {run.gap_count > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 text-xs font-medium">
                {run.gap_count} gap{run.gap_count !== 1 ? "s" : ""}
              </span>
            )}
```

- [ ] **Step 3: Verify in browser**

Open `http://localhost:3000/library`. Confirm:
- Theme name appears in muted text below each ticker
- Gap count badge shows in amber when > 0
- Cards without gaps don't show the badge

- [ ] **Step 4: Commit**

```bash
git add frontend/app/library/page.tsx
git commit -m "feat: show theme name and gap count on library run cards"
```

---

### Task 7: Data Gaps tab on Library page

**Files:**
- Modify: `frontend/app/library/page.tsx`

- [ ] **Step 1: Extend FilterStatus type and FilterBar**

Update the `FilterStatus` type (line 43) to include `"data_gaps"`:

```typescript
type FilterStatus = "all" | "completed" | "in_progress" | "awaiting_approval" | "watchlist" | "data_gaps";
```

Add the new tab to the `filters` array inside `FilterBar` (after the watchlist entry):

```typescript
    { key: "data_gaps",         label: "Data Gaps" },
```

- [ ] **Step 2: Add data gaps state and fetching**

In the `LibraryPage` component, add state for the data gaps response:

```typescript
  const [dataGaps, setDataGaps] = useState<import("@/lib/api").DataGapsResponse | null>(null);
  const [gapsLoading, setGapsLoading] = useState(false);
```

Add an effect that fetches data gaps when the "Data Gaps" tab is active:

```typescript
  useEffect(() => {
    if (filter !== "data_gaps") return;
    setGapsLoading(true);
    const opts: Record<string, string> = {};
    if (themeId) opts.theme_id = themeId;
    api.dataGaps(opts as Parameters<typeof api.dataGaps>[0])
      .then(setDataGaps)
      .finally(() => setGapsLoading(false));
  }, [filter, themeId]);
```

- [ ] **Step 3: Skip the normal runs fetch when Data Gaps tab is active**

Update the runs-fetching `useEffect` to skip when on the data_gaps tab:

```typescript
  useEffect(() => {
    if (filter === "data_gaps") return;
    setLoading(true);
    const opts: Record<string, string | number> = {};
    if (filter !== "all") opts.status = filter;
    if (themeId) opts.theme_id = themeId;
    if (debouncedSearch.trim()) opts.search = debouncedSearch.trim();
    api.list(opts as Parameters<typeof api.list>[0])
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [filter, themeId, debouncedSearch]);
```

- [ ] **Step 4: Create the DataGapsView component**

Add this component above the `LibraryPage` component (after `RunCard`):

```tsx
function DataGapsView({
  data,
  loading,
  onTickerClick,
}: {
  data: import("@/lib/api").DataGapsResponse | null;
  loading: boolean;
  onTickerClick: (ticker: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!data || data.gaps.length === 0) {
    return (
      <div className="text-center py-24">
        <p className="text-[var(--color-text-muted)] text-sm">No data gaps detected across runs.</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-4">
        {data.gaps.length} gap type{data.gaps.length !== 1 ? "s" : ""} found across {data.total_runs_scanned} run{data.total_runs_scanned !== 1 ? "s" : ""}
      </p>
      <div className="space-y-2">
        {data.gaps.map((gap, i) => (
          <div
            key={i}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                      gap.gap_type === "hard_error"
                        ? "bg-red-500/10 text-red-400"
                        : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {gap.gap_type === "hard_error" ? "Error" : "Gap"}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {gap.category.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-sm text-[var(--color-text-primary)]">{gap.description}</p>
                {gap.example_tickers.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <span className="text-xs text-[var(--color-text-muted)]">e.g.</span>
                    {gap.example_tickers.map((t) => (
                      <button
                        key={t}
                        onClick={() => onTickerClick(t)}
                        className="px-1.5 py-0.5 rounded bg-[var(--color-accent)]/10 text-[var(--color-accent)]
                                   text-xs font-mono font-medium hover:bg-[var(--color-accent)]/20 transition-colors"
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0 text-right">
                <p className="text-lg font-mono font-semibold text-[var(--color-text-primary)]">
                  {gap.occurrences}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {Math.round(gap.frequency * 100)}% of runs
                </p>
              </div>
            </div>
            {/* Frequency bar */}
            <div className="mt-3 h-1 rounded-full bg-[var(--color-border)] overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  gap.gap_type === "hard_error" ? "bg-red-400" : "bg-amber-400"
                }`}
                style={{ width: `${Math.round(gap.frequency * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire DataGapsView into the main page render**

In the main `LibraryPage` return, update the content section (the `{loading ? ... : runs.length === 0 ? ... : ...}` block) to handle the `data_gaps` filter. Replace the content section (around lines 211–238) with:

```tsx
        {/* Content */}
        {filter === "data_gaps" ? (
          <DataGapsView
            data={dataGaps}
            loading={gapsLoading}
            onTickerClick={(t) => {
              setSearch(t);
              setFilter("all");
            }}
          />
        ) : loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
          </div>
        ) : runs.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <p className="text-[var(--color-text-muted)] text-sm">
              {filter === "all"
                ? "No research runs yet. Start your first one."
                : `No ${STATUS_LABEL[filter]?.toLowerCase() ?? filter} runs.`}
            </p>
            {filter === "all" && (
              <button
                onClick={() => router.push("/pipeline/new")}
                className="mt-2 px-5 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-semibold
                           hover:bg-[var(--color-accent)]/90 transition-colors"
              >
                Begin Research →
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} onClick={() => navigate(run)} />
            ))}
          </div>
        )}
```

- [ ] **Step 6: Verify in browser**

Open `http://localhost:3000/library`. Confirm:
- "Data Gaps" tab appears in the filter bar
- Clicking it shows the aggregate gaps view with frequency bars
- Clicking an example ticker switches back to "All" tab with that ticker in the search field
- Theme dropdown filters the data gaps view too
- All existing tabs still work

- [ ] **Step 7: Commit**

```bash
git add frontend/app/library/page.tsx
git commit -m "feat: add Data Gaps tab to library page"
```
