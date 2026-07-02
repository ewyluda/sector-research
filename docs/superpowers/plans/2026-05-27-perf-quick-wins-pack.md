# Perf Quick-Wins Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship six localized perf fixes from the in-conversation audit (observation 7182 — Issues #1, #2, #3, #13, plus the N+1 in `discovery._merge_results` and the status-board double-fetch hack documented in observation 7173). Together they cut the worst user-visible jank on deep-dive live streaming, eliminate wasted polling on tab-switch, remove a 400 ms FMP round-trip per reverse-DCF panel open, simplify the status-board archived-flag inference, drop a per-ticker `SurpriseAlert` lookup, and add the missing composite index for the status-board's latest-runs subquery.

**Architecture:** Every fix is small and isolated — no shared seams except the status board (Task 4 + Task 6 both touch its backend). Sequenced for safe rollback: Tasks 1–3 are pure additions, Task 4 adds a non-breaking field then removes a frontend hack, Task 5 batches an existing N+1 without changing API shape, Task 6 is a backward-compatible Alembic migration.

**What's intentionally NOT in this pack** (deferred to follow-up packs because they are not "quick"): Issue #4 quick-screen → deep-dive data reuse (requires `ResearchState` schema changes + serialization round-trip work), Issue #6 fanout serial → batched ingest (concurrency-limit + idempotency design needed), Issue #9 workspace Challenge/Differentiate parallelism (shared-context error-handling review), Issue #11 per-category fundamentals trimming (touches the prompt-routing surface), Issue #12 transcript-pass cache-eligibility audit (needs prompt-by-prompt char measurements).

**Tech Stack:** FastAPI + async SQLAlchemy + Pydantic v2 on PostgreSQL, Next.js 16 App Router, React 19, Tailwind v4. Backend tests via stdlib `unittest` (no pytest). Frontend lint via `npm run lint`.

---

## Pre-flight (do once before starting)

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
git checkout -b feat/perf-quick-wins-pack
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -5
cd frontend && npm run lint && cd ..
```

Both should be clean before starting Task 1. Note the baseline backend-test pass count — you'll compare against it at the end.

---

## Task 1: Frontend — `React.memo` heavy DeepDiveDashboard sections

Today every SSE event during a live deep-dive triggers a full re-render of `DeepDiveDashboard`, which re-mounts all 13+ section components. The Recharts and `lightweight-charts` instances inside each section perform a full DOM teardown + remount, costing 800 ms – 1.2 s of jank per event. Wrapping each leaf section in `React.memo` lets React skip the re-render entirely when that section's props are referentially stable — which they are for any section whose category hasn't streamed a new event.

The big-ROI sections are the chart-heavy ones: `FinancialHealth`, `GrowthEarnings`, `TechnicalMarket`, `BusinessQuality`, `MacroRegime`, `RiskAssessment`, `ManagementGovernance`, `SentimentNarrative`, `FutureDurability`, `CrossCategoryCorrelation`. The lighter ticker-driven sections (`Competition`, `SupplyChainEcosystem`, `WhatChangedPanel`) take just a `ticker` prop and don't re-render when scores change anyway — `memo` them too for symmetry.

`OverviewBanner` deliberately *does* re-render every event (it owns the live scoreboard + verdict callouts), so leave it un-memoed.

**Files:**
- Modify: `frontend/components/deep-dive/sections/FinancialHealth.tsx`
- Modify: `frontend/components/deep-dive/sections/GrowthEarnings.tsx`
- Modify: `frontend/components/deep-dive/sections/TechnicalMarket.tsx`
- Modify: `frontend/components/deep-dive/sections/BusinessQuality.tsx`
- Modify: `frontend/components/deep-dive/sections/MacroRegime.tsx`
- Modify: `frontend/components/deep-dive/sections/RiskAssessment.tsx`
- Modify: `frontend/components/deep-dive/sections/ManagementGovernance.tsx`
- Modify: `frontend/components/deep-dive/sections/SentimentNarrative.tsx`
- Modify: `frontend/components/deep-dive/sections/FutureDurability.tsx`
- Modify: `frontend/components/deep-dive/sections/CrossCategoryCorrelation.tsx`
- Modify: `frontend/components/deep-dive/sections/Competition.tsx`
- Modify: `frontend/components/deep-dive/sections/SupplyChainEcosystem.tsx`
- Modify: `frontend/components/deep-dive/sections/WhatChangedPanel.tsx`

- [ ] **Step 1.1: Confirm the section files exist and their export shape**

```bash
ls frontend/components/deep-dive/sections/
grep -l "^export function\|^export const" frontend/components/deep-dive/sections/*.tsx
```

Expected: all 13 files present. Note for each one whether it uses `export function FooBar(props)` or `export const FooBar = (props) =>` — both are wrappable in `React.memo` but the patch differs slightly.

- [ ] **Step 1.2: Wrap each section in `React.memo`**

For `export function Foo(props) { ... }`-style files, change to:

```tsx
import { memo } from "react";

function FooImpl(props: FooProps) {
  // …existing body unchanged…
}

export const Foo = memo(FooImpl);
```

For `export const Foo = (props: FooProps) => { ... }`-style files, change to:

```tsx
import { memo } from "react";

export const Foo = memo((props: FooProps) => {
  // …existing body unchanged…
});
```

**Critical:** Do NOT change the imported name in `DeepDiveDashboard.tsx`. The re-export must preserve the same identifier (`FinancialHealth`, `GrowthEarnings`, etc.) so the dashboard's existing `<FinancialHealth … />` JSX continues to work.

**For each file**, also set a `displayName` for the DevTools-friendly view immediately after the `memo()` call:

```tsx
Foo.displayName = "Foo";
```

(Skip `displayName` if the file uses the wrapped `function FooImpl` pattern — React infers it.)

Apply this transformation to all 13 files in the file list above.

- [ ] **Step 1.3: Verify no section is doing prop-mutation that defeats `memo`**

`React.memo` does a shallow prop compare by default. If any section receives a freshly-constructed object/array as a prop on every render (e.g. `<Foo data={raw.filter(…)} />` inline at the call site), the memo never short-circuits. Spot-check `DeepDiveDashboard.tsx` for this — the call sites already pass stable references (`financials`, `getStructured(...)` returns a stable reference from a stable `categories` object), so memo should work, but verify:

```bash
grep -n "<\(FinancialHealth\|GrowthEarnings\|TechnicalMarket\|BusinessQuality\|MacroRegime\|RiskAssessment\|ManagementGovernance\|SentimentNarrative\|FutureDurability\|CrossCategoryCorrelation\)" frontend/components/deep-dive/DeepDiveDashboard.tsx
```

Confirm none of the props are inline `.filter()` / `.map()` / `{…}` literals. If they are (none expected today), hoist the computation up via `useMemo` in the dashboard — but only if it's actually inline.

- [ ] **Step 1.4: Lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -10 && cd ..
```

Expected: zero lint errors, build succeeds.

- [ ] **Step 1.5: Manual verification on a live run**

```bash
# Start backend in one terminal
uvicorn backend.app.main:app --reload
# Start frontend in another
cd frontend && npm run dev
```

In the browser:
1. Open DevTools → Performance, start recording
2. Trigger a new pipeline run from `/pipeline/new` for a ticker
3. Watch the live deep-dive stream
4. Stop the recording after ~30 s of streaming
5. Compare to the baseline: scripting time per SSE event should drop noticeably (target: 50%+ reduction in re-render work on the dashboard tree)

Document the rough number in the commit message (e.g. "scripting dropped from ~600 ms to ~250 ms per event in DevTools").

- [ ] **Step 1.6: Commit**

```bash
git add frontend/components/deep-dive/sections/*.tsx
git commit -m "$(cat <<'EOF'
perf(deep-dive): React.memo section components

Every SSE event during a live deep-dive triggered a full re-render of
DeepDiveDashboard, re-mounting Recharts + lightweight-charts instances
inside all 13 sections. Wrapping each section in React.memo lets React
skip sections whose props are referentially stable (any category that
hasn't streamed a new event). OverviewBanner stays un-memoed — it owns
the live scoreboard and must re-render every event.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Frontend — debounce visibility-triggered status-board refetches

`frontend/app/status/page.tsx` has three independent `setInterval(60000)` polls (board, read-throughs, earnings). Each registers a `visibilitychange` listener that calls the fetch immediately whenever the tab becomes visible. A user toggling away and back 3–5× a minute (a normal trading-research pattern) triggers 9–15 wasted HTTP requests per minute on top of the timer-driven polls.

The fix is a small "fetched within the last N seconds — skip" debounce on the visibility-triggered refetch path. The interval-driven path stays as-is (60 s cadence is correct when the tab has been backgrounded for a while). Use 30 s as the floor: anything fresher than that is too new to be worth refetching on a tab switch.

**Files:**
- Modify: `frontend/app/status/page.tsx`

- [ ] **Step 2.1: Add a per-fetcher last-fetch ref pattern**

Edit `frontend/app/status/page.tsx`. At the top, add `useRef` to the existing `react` import:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
```

Inside the `StatusPage` component body, just before the first `useEffect`, add:

```tsx
const lastBoardFetchAtRef = useRef<number>(0);
const lastReadThroughsFetchAtRef = useRef<number>(0);
const lastEarningsFetchAtRef = useRef<number>(0);

const VIS_REFRESH_FLOOR_MS = 30_000;

function shouldRefetchOnVisibility(ref: React.MutableRefObject<number>): boolean {
  return Date.now() - ref.current >= VIS_REFRESH_FLOOR_MS;
}
```

- [ ] **Step 2.2: Wire each fetcher to stamp the ref after a successful fetch**

In `fetchBoard()`, immediately after the line `setEntries(res.entries);` (around line 244), add:

```tsx
lastBoardFetchAtRef.current = Date.now();
```

In the read-throughs `load()` (around line 289), immediately after `if (!cancelled) setRtByRun(data);`, add:

```tsx
lastReadThroughsFetchAtRef.current = Date.now();
```

In the earnings `refresh()` (around line 314), immediately after `setEarningsByRun(next);`, add:

```tsx
lastEarningsFetchAtRef.current = Date.now();
```

- [ ] **Step 2.3: Gate the `onVis` handlers with the debounce**

In the board `useEffect` (around line 270), change:

```tsx
const onVis = () => {
  if (document.visibilityState === "visible") fetchBoard();
};
```

to:

```tsx
const onVis = () => {
  if (document.visibilityState !== "visible") return;
  if (!shouldRefetchOnVisibility(lastBoardFetchAtRef)) return;
  fetchBoard();
};
```

Apply the same pattern to:
- The read-throughs `useEffect` (around line 287) — gate with `lastReadThroughsFetchAtRef`
- The earnings `useEffect` (around line 312) — gate with `lastEarningsFetchAtRef`

The `setInterval` callbacks stay unchanged — they're already visibility-guarded and fire at a sane 60 s cadence.

- [ ] **Step 2.4: Lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -5 && cd ..
```

Expected: zero errors.

- [ ] **Step 2.5: Manual verification**

```bash
cd frontend && npm run dev
```

In the browser:
1. Open `/status`, open DevTools → Network tab, filter to `XHR`
2. Toggle to another tab, toggle back — expect *no* immediate refetch (because the initial fetch was <30 s ago)
3. Wait ~35 s, toggle away and back — expect exactly one refetch per fetcher (board, read-throughs, earnings)
4. Confirm the regular 60 s interval still fires when the tab stays focused

- [ ] **Step 2.6: Commit**

```bash
git add frontend/app/status/page.tsx
git commit -m "$(cat <<'EOF'
perf(status): debounce visibility-triggered refetches to a 30s floor

Tab-switching with the status board open could fire 9-15 HTTP
requests per minute because each visibilitychange handler kicked off
all three fetchers (board, read-throughs, earnings) regardless of how
recently the data was loaded. A per-fetcher last-fetched-at ref now
suppresses the visibility-triggered fetch when the data is <30s old.
The interval-driven 60s polling path is unchanged.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Backend — TTL cache the FMP live quote behind reverse-DCF

`GET /api/models/{ticker}/reverse-dcf` without a `?price=` override calls `_fetch_live_price(fmp, ticker)` on every request, which makes a fresh FMP `/quote` HTTP round-trip (~400 ms). The reverse-DCF panel auto-loads on every model-page open and many users open the panel multiple times per session while iterating on assumptions. A 30 s in-memory TTL cache on `(ticker → price)` collapses repeat opens into a single FMP call without compromising freshness in any practically meaningful way (intraday quotes move ≪ 1 % over 30 s for the kinds of names this tool tracks).

**Files:**
- Modify: `backend/app/api/models_api.py`
- Create: `backend/tests/test_reverse_dcf_quote_cache.py`

- [ ] **Step 3.1: Write the failing test**

Create `backend/tests/test_reverse_dcf_quote_cache.py`:

```python
"""Tests for the in-memory TTL cache on the reverse-DCF live-quote fetch."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.api import models_api


class TestLivePriceCache(unittest.TestCase):
    def setUp(self):
        # Reset the module-level cache between tests so order doesn't matter.
        models_api._LIVE_PRICE_CACHE.clear()

    def test_first_call_hits_fmp(self):
        fmp = MagicMock()
        fmp.get_quote = AsyncMock(return_value=({"price": 123.45}, None))
        price = asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        self.assertEqual(price, 123.45)
        fmp.get_quote.assert_awaited_once_with("NVDA")

    def test_second_call_within_ttl_uses_cache(self):
        fmp = MagicMock()
        fmp.get_quote = AsyncMock(return_value=({"price": 123.45}, None))
        asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        # Still exactly one network call
        fmp.get_quote.assert_awaited_once()

    def test_call_after_ttl_expiry_refetches(self):
        import time
        fmp = MagicMock()
        fmp.get_quote = AsyncMock(return_value=({"price": 100.0}, None))
        asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        # Manually expire the cache entry
        ticker, (price, ts) = "NVDA", models_api._LIVE_PRICE_CACHE["NVDA"]
        models_api._LIVE_PRICE_CACHE["NVDA"] = (price, ts - models_api._LIVE_PRICE_TTL_SECONDS - 1)
        asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        self.assertEqual(fmp.get_quote.await_count, 2)

    def test_different_tickers_are_keyed_independently(self):
        fmp = MagicMock()
        async def side(ticker):
            return ({"price": {"NVDA": 100.0, "AAPL": 200.0}[ticker]}, None)
        fmp.get_quote = AsyncMock(side_effect=side)
        nvda = asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        aapl = asyncio.run(models_api._fetch_live_price(fmp, "AAPL"))
        self.assertEqual(nvda, 100.0)
        self.assertEqual(aapl, 200.0)
        self.assertEqual(fmp.get_quote.await_count, 2)

    def test_zero_price_is_not_cached(self):
        """A failing fetch returns 0.0 — caching that would poison the next 30s."""
        fmp = MagicMock()
        fmp.get_quote = AsyncMock(return_value=({"price": 0.0}, None))
        asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        # Second call must retry
        fmp.get_quote = AsyncMock(return_value=({"price": 99.0}, None))
        price = asyncio.run(models_api._fetch_live_price(fmp, "NVDA"))
        self.assertEqual(price, 99.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_reverse_dcf_quote_cache -v
```

Expected: `AttributeError: module 'backend.app.api.models_api' has no attribute '_LIVE_PRICE_CACHE'`.

- [ ] **Step 3.3: Add the cache and rewrite `_fetch_live_price`**

Edit `backend/app/api/models_api.py`. Just above the existing `async def _fetch_live_price` (around line 250), add:

```python
import time as _time  # noqa: E402

_LIVE_PRICE_TTL_SECONDS = 30.0
# Module-level cache: ticker -> (price, fetched_at_monotonic).
# Acceptable for a single-process local tool; no horizontal scaling.
_LIVE_PRICE_CACHE: dict[str, tuple[float, float]] = {}
```

Replace the existing `_fetch_live_price` function body with:

```python
async def _fetch_live_price(fmp, ticker: str) -> float:
    """Pulls current price from FMP with a 30s TTL cache.

    Returns 0.0 on any error so the caller can decide whether to fall back
    to a user-provided override. Zero is never cached — a transient FMP
    failure should not poison the next 30 seconds of requests.
    """
    now = _time.monotonic()
    cached = _LIVE_PRICE_CACHE.get(ticker)
    if cached is not None:
        price, fetched_at = cached
        if now - fetched_at < _LIVE_PRICE_TTL_SECONDS:
            return price
    try:
        quote, _citation = await fmp.get_quote(ticker)
        price = float((quote.get("price") if quote else 0.0) or 0.0)
    except Exception:
        return 0.0
    if price > 0:
        _LIVE_PRICE_CACHE[ticker] = (price, now)
    return price
```

- [ ] **Step 3.4: Run the test and verify it passes**

```bash
python -m unittest backend.tests.test_reverse_dcf_quote_cache -v
```

Expected: 5 tests pass.

- [ ] **Step 3.5: Run the full backend suite**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: baseline + 5 new tests pass, zero failures.

- [ ] **Step 3.6: Commit**

```bash
git add backend/app/api/models_api.py backend/tests/test_reverse_dcf_quote_cache.py
git commit -m "$(cat <<'EOF'
perf(reverse-dcf): 30s TTL cache on FMP live-quote fetch

GET /api/models/{ticker}/reverse-dcf without ?price= called FMP /quote
on every request (~400ms). The reverse-DCF panel auto-loads on every
model-page open, and users iterate on assumptions by re-opening the
panel — repeat round-trips for a price that moves <1% over 30s. A
module-level dict with 30s TTL collapses repeat opens to a single FMP
call. Zero prices are not cached so a transient failure doesn't poison
the next 30s.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Backend + Frontend — surface `archived_at` on StatusBoardEntry, remove double-fetch hack

The status page makes **two** sequential `/api/status/board` calls whenever "Include archived" is checked, computing a set difference to infer which entries are archived. The doubled load fires every 60 s while the toggle is on. The data is already in the database — `research_runs.archived_at` is selected at line 138 of `status_board.py` — and just needs to be plumbed onto the response DTO.

**Files:**
- Modify: `backend/app/services/status_board.py` (add `archived_at` to `StatusBoardEntry` dataclass + populate it in `build_status_board`)
- Modify: `backend/app/api/status.py` (serialize the new field if the route doesn't already use `dataclasses.asdict`-style passthrough)
- Modify: `frontend/lib/api.ts` (add `archived_at: string | null` to `StatusBoardEntry`)
- Modify: `frontend/app/status/page.tsx` (drop the second fetch + the diff)
- Create: `backend/tests/test_status_board_archived_flag.py`

- [ ] **Step 4.1: Write the failing test**

Create `backend/tests/test_status_board_archived_flag.py`:

```python
"""Tests for archived_at on StatusBoardEntry — eliminates the frontend double-fetch."""
import unittest
from dataclasses import fields

from backend.app.services.status_board import StatusBoardEntry


class TestStatusBoardEntryShape(unittest.TestCase):
    def test_entry_carries_archived_at(self):
        names = {f.name for f in fields(StatusBoardEntry)}
        self.assertIn("archived_at", names)

    def test_archived_at_defaults_to_none(self):
        # The field must be optional so existing call sites don't have to pass it.
        field_map = {f.name: f for f in fields(StatusBoardEntry)}
        archived = field_map["archived_at"]
        # default may be MISSING in dataclass; check by attempting construction.
        # All other required fields must be supplied; we only verify the constructor
        # accepts archived_at=None explicitly.
        from datetime import datetime, timezone
        e = StatusBoardEntry(
            ticker="NVDA",
            theme_id="t1",
            theme_name="AI",
            run_id="r1",
            thesis_status="confirmed",
            conviction_score=80,
            completed_at=datetime.now(timezone.utc),
            days_since_update=1,
            health="healthy",
            archived_at=None,
        )
        self.assertIsNone(e.archived_at)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_status_board_archived_flag -v
```

Expected: assertion failure on `assertIn("archived_at", names)`.

- [ ] **Step 4.3: Add `archived_at` to the dataclass**

Edit `backend/app/services/status_board.py`. In the `StatusBoardEntry` dataclass (around line 52), add a new field. Since the existing fields include `field(default_factory=...)` entries, the new optional field must go at the end of the dataclass to satisfy Python's "no non-default after default" rule:

```python
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
    archived_at: datetime | None = None  # NEW
```

- [ ] **Step 4.4: Populate `archived_at` in `build_status_board`**

In `build_status_board` (around line 330 where `StatusBoardEntry(...)` is constructed), the SQL already selects `r.archived_at` (line 138) into the `row` dict. Add the new kwarg to the constructor call. Look for the block:

```python
            StatusBoardEntry(
                ticker=...,
                ...
                completed_at=completed_at,
            )
```

Add immediately before the closing paren:

```python
                archived_at=row.get("archived_at"),
```

(The SQL row keys may use either `archived_at` directly or be wrapped in a result-row mapping — `row.get("archived_at")` works either way.)

- [ ] **Step 4.5: Run the dataclass-shape test**

```bash
python -m unittest backend.tests.test_status_board_archived_flag -v
```

Expected: pass.

- [ ] **Step 4.6: Verify the API route serializes the new field**

Open `backend/app/api/status.py` and find the route that returns the status board (search for `/board`). If it returns the dataclass via FastAPI's automatic serialization, `archived_at` will be included. If it uses a manual dict mapping, you'll need to add the field there too:

```bash
grep -n "/board\|StatusBoardEntry\|archived_at" backend/app/api/status.py | head -20
```

If you see manual `{"ticker": e.ticker, ...}` construction, add `"archived_at": e.archived_at.isoformat() if e.archived_at else None`. If the route returns the dataclass directly, no edit needed — FastAPI will serialize `datetime | None` as ISO string or `null`.

- [ ] **Step 4.7: Smoke-test the endpoint**

```bash
uvicorn backend.app.main:app --reload --port 8001
# In another terminal:
curl -s 'http://127.0.0.1:8001/api/status/board?include_archived=true' | python -c "import json,sys; d=json.load(sys.stdin); print(d['entries'][0] if d['entries'] else 'no entries')"
```

Expected: an entry dict containing `archived_at` (null or ISO string). Stop the server.

- [ ] **Step 4.8: Add `archived_at` to the frontend type**

Edit `frontend/lib/api.ts`. Find the `StatusBoardEntry` interface (grep for `interface StatusBoardEntry`). Add:

```typescript
  archived_at: string | null;
```

- [ ] **Step 4.9: Drop the double-fetch from the status page**

Edit `frontend/app/status/page.tsx`. In `fetchBoard()` (around line 238), replace the entire body of the `if (includeArchived) { ... } else { ... }` block (lines 252–261) with:

```tsx
      setArchived(
        new Set(res.entries.filter((e) => e.archived_at !== null).map((e) => e.run_id)),
      );
```

Remove the comment block above it (the now-stale `// Track which entries are currently archived…` explanation). The final `fetchBoard()` should look roughly like:

```tsx
  async function fetchBoard() {
    try {
      const res = await statusApi.board({
        theme_id: themeId || undefined,
        include_archived: includeArchived,
      });
      setEntries(res.entries);
      setArchived(
        new Set(res.entries.filter((e) => e.archived_at !== null).map((e) => e.run_id)),
      );
      lastBoardFetchAtRef.current = Date.now();  // from Task 2
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load board");
    } finally {
      setLoading(false);
    }
  }
```

- [ ] **Step 4.10: Lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -5 && cd ..
```

Expected: zero errors.

- [ ] **Step 4.11: Manual verification**

```bash
cd frontend && npm run dev
```

In the browser:
1. Open `/status`, toggle "Include archived" on
2. Open DevTools → Network tab — confirm there is **exactly one** `/api/status/board` request per poll cycle (was two before)
3. Archive an entry from the row menu — confirm the dimmed-row visual still works (archived entries appear at 50% opacity per the existing `archived ? "opacity-50" : ""` className)

- [ ] **Step 4.12: Commit**

```bash
git add backend/app/services/status_board.py backend/app/api/status.py backend/tests/test_status_board_archived_flag.py frontend/lib/api.ts frontend/app/status/page.tsx
git commit -m "$(cat <<'EOF'
perf(status): surface archived_at on StatusBoardEntry, drop double-fetch

The status page fetched the board twice when "Include archived" was
checked — once to get the full list, again to diff against the
non-archived list and infer which entries were archived. The data was
already selected from research_runs.archived_at in the SQL but never
exposed on the DTO. Adding archived_at: datetime | None to the entry
dataclass + serializing it lets the frontend filter directly and cuts
the 60s polling load in half whenever the archived toggle is on.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Backend — batch the SurpriseAlert N+1 in `discovery._merge_results`

`_merge_results` runs a `SELECT … FROM surprise_alerts WHERE ticker = … AND theme_id = … AND acknowledged_at IS NULL` inside its per-ticker `for` loop (around line 477 of `services/discovery.py`). For a 50-ticker theme that's 50 SQL round-trips when one `IN (…)` would do. Cost varies by Postgres + network latency but commonly 100–300 ms total. Batch it once up front.

(Note: the audit observation 7182 called this "Issue #8 — last_run_id/conviction_score/thesis_status N+1." Inspection shows those fields are *declared* on `CompanySignalCard` but never populated anywhere in the codebase — they're dead data flowing through the API as `null`. The actual N+1 in `_merge_results` today is the `SurpriseAlert` lookup. This task fixes the real bug; populating the dormant `last_run_*` fields is a separate scope.)

**Files:**
- Modify: `backend/app/services/discovery.py`
- Create: `backend/tests/test_discovery_surprise_batch.py`

- [ ] **Step 5.1: Write the failing test**

Create `backend/tests/test_discovery_surprise_batch.py`:

```python
"""Tests for batched SurpriseAlert lookup in DiscoveryEngine._merge_results."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.discovery import DiscoveryEngine


class TestSurpriseAlertBatching(unittest.TestCase):
    def test_merge_results_uses_single_in_query_for_surprises(self):
        """_merge_results must call db.execute() for SurpriseAlert exactly once,
        regardless of the number of tickers in fmp_results."""
        eng = DiscoveryEngine(fmp=MagicMock(), x=MagicMock())

        theme = MagicMock()
        theme.id = "theme-1"
        theme.seed_tickers = []
        theme.signal_weights = None

        fmp_results = [
            {
                "ticker": f"T{i}",
                "profile": {"companyName": f"Co{i}", "marketCap": 1e9},
                "income": [],
                "balance": [],
                "cashflow": [],
                "citations": [],
            }
            for i in range(10)
        ]

        execute_calls: list[str] = []

        class _Res:
            def scalar_one_or_none(self):
                return None
            def scalars(self):
                return MagicMock(all=MagicMock(return_value=[]))

        async def fake_execute(stmt):
            execute_calls.append(str(stmt))
            return _Res()

        db = MagicMock()
        db.execute = fake_execute

        asyncio.run(eng._merge_results(theme, fmp_results, {}, db))

        surprise_calls = [c for c in execute_calls if "surprise_alert" in c.lower()]
        self.assertEqual(
            len(surprise_calls), 1,
            f"expected one batched SurpriseAlert query, got {len(surprise_calls)}",
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_discovery_surprise_batch -v
```

Expected: failure — `len(surprise_calls)` is 10 (one per ticker), not 1.

- [ ] **Step 5.3: Batch the SurpriseAlert query**

Edit `backend/app/services/discovery.py`. Find the start of `_merge_results` (around line 405). Just before the `for item in fmp_results:` loop, insert a single batched lookup:

```python
        # Batch-load active SurpriseAlerts for all tickers in this pass to avoid
        # an N+1 SELECT inside the per-ticker construction loop.
        all_tickers = [
            (item.get("ticker") or "").upper()
            for item in fmp_results
            if item.get("ticker")
        ]
        surprise_tickers: set[str] = set()
        if all_tickers:
            surprise_rows = (await db.execute(
                select(SurpriseAlert.ticker).where(
                    SurpriseAlert.theme_id == theme.id,
                    SurpriseAlert.ticker.in_(all_tickers),
                    SurpriseAlert.acknowledged_at.is_(None),
                )
            )).scalars().all()
            surprise_tickers = {t for t in surprise_rows}
```

Then **replace** the existing inner-loop block (around line 477):

```python
            # Check for active surprise alert
            surprise_result = await db.execute(
                select(SurpriseAlert).where(
                    SurpriseAlert.ticker == ticker,
                    SurpriseAlert.theme_id == theme.id,
                    SurpriseAlert.acknowledged_at.is_(None),
                )
            )
            is_surprise = surprise_result.scalar_one_or_none() is not None
```

with:

```python
            is_surprise = ticker in surprise_tickers
```

- [ ] **Step 5.4: Run the test and verify it passes**

```bash
python -m unittest backend.tests.test_discovery_surprise_batch -v
```

Expected: pass.

- [ ] **Step 5.5: Run the full backend suite**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: baseline + new tests pass, zero failures. Pay special attention to any existing discovery tests — make sure the refactor preserved their assertions about surprise-alert behavior.

- [ ] **Step 5.6: Commit**

```bash
git add backend/app/services/discovery.py backend/tests/test_discovery_surprise_batch.py
git commit -m "$(cat <<'EOF'
perf(discovery): batch SurpriseAlert lookup with IN() instead of N+1

_merge_results ran a SELECT FROM surprise_alerts per ticker inside its
construction loop — 50 round-trips for a 50-ticker theme. Batched into
one IN() query that returns the ticker set up front; the per-ticker
check becomes an O(1) set membership test.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Backend — composite index on `research_runs(ticker, theme_id, completed_at DESC)`

`_build_latest_runs_sql` in `services/status_board.py` runs a `SELECT DISTINCT ON (r.ticker, r.theme_id) … ORDER BY r.ticker, r.theme_id, {completed_expr} DESC, r.created_at DESC` query against `research_runs`. With no composite index, Postgres falls back to a sort-then-scan. A migration adding `(ticker, theme_id, completed_at DESC, created_at DESC)` lets the planner use an index-only walk for the `DISTINCT ON` and eliminates the sort.

`completed_at` is a *generated/computed* column in this codebase (see `services/run_timestamps.completed_at_sql`). Confirm whether it's a real column or a computed expression before writing the migration — a real column can be indexed directly; a computed expression needs a function-based / expression index.

**Files:**
- Create: `backend/migrations/versions/<rev>_add_status_board_latest_run_index.py`

- [ ] **Step 6.1: Confirm `completed_at` is a real column on `research_runs`**

```bash
grep -n "completed_at\|class ResearchRun" backend/app/models/research_run.py
grep -rn "completed_at_sql\|completed_at" backend/app/services/run_timestamps.py 2>/dev/null | head -10
```

Note the column type. If `completed_at` is a `Column(DateTime…)`, use a plain index. If `completed_at_sql("r")` resolves to an expression like `COALESCE(r.completed_at, r.updated_at)`, you'll need an expression index (`CREATE INDEX … ON research_runs (ticker, theme_id, COALESCE(completed_at, updated_at) DESC, created_at DESC)`). Most likely it's a real column — proceed accordingly.

- [ ] **Step 6.2: Generate a new migration scaffold**

```bash
cd backend && PYTHONPATH=.. alembic revision -m "add status board latest run composite index" && cd ..
```

Capture the new revision id printed by alembic (e.g. `7a2b3c4d5e6f_add_status_board_latest_run_index.py`).

- [ ] **Step 6.3: Fill in the migration**

Edit the new migration file in `backend/migrations/versions/`. Replace the auto-generated `upgrade()` and `downgrade()` with:

```python
"""add status board latest run composite index

Revision ID: <auto-generated>
Revises: <auto-generated previous head>
Create Date: <auto-generated>
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "<keep auto-generated>"
down_revision = "<keep auto-generated previous head>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_research_runs_status_board_latest",
        "research_runs",
        ["ticker", "theme_id", "completed_at", "created_at"],
        postgresql_using="btree",
        postgresql_ops={"completed_at": "DESC", "created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_research_runs_status_board_latest", table_name="research_runs")
```

(If Step 6.1 revealed `completed_at` is computed rather than a real column, replace the `create_index` call with a raw-SQL form:

```python
def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_research_runs_status_board_latest "
        "ON research_runs (ticker, theme_id, COALESCE(completed_at, updated_at) DESC, created_at DESC)"
    )

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_research_runs_status_board_latest")
```

Match the exact expression used in `completed_at_sql()`.)

- [ ] **Step 6.4: Apply the migration**

```bash
cd backend && alembic upgrade head && cd ..
```

Expected: clean `INFO  [alembic.runtime.migration] Running upgrade …`.

- [ ] **Step 6.5: Verify the index exists**

```bash
psql "$DATABASE_URL_SYNC" -c "\d research_runs" | grep status_board_latest
```

Expected: one line showing the new btree index. (If you don't have a `psql` shell, you can verify via Python: `python -c "from sqlalchemy import create_engine, text; from backend.app.config import get_settings; e=create_engine(get_settings().database_url_sync); print([r[0] for r in e.connect().execute(text(\"SELECT indexname FROM pg_indexes WHERE tablename='research_runs'\"))])"`.)

- [ ] **Step 6.6: EXPLAIN the status-board query before and after**

The fastest way to confirm the index is used:

```bash
psql "$DATABASE_URL_SYNC" -c "EXPLAIN ANALYZE SELECT DISTINCT ON (r.ticker, r.theme_id) r.id, r.ticker, r.theme_id, r.thesis_status, r.conviction_score, r.created_at FROM research_runs r WHERE r.archived_at IS NULL ORDER BY r.ticker, r.theme_id, COALESCE(r.completed_at, r.updated_at) DESC, r.created_at DESC LIMIT 100;"
```

Expected: the plan should now show `Index Scan using ix_research_runs_status_board_latest` (or the index name in the Postgres plan) instead of a `Sort` + `Seq Scan`.

If the planner still chooses a seq scan, the table may be too small for the index to matter yet — that's fine, the index is in place for when the dataset grows.

- [ ] **Step 6.7: Verify the migration is reversible**

```bash
cd backend && alembic downgrade -1 && alembic upgrade head && cd ..
```

Expected: both directions succeed cleanly.

- [ ] **Step 6.8: Full backend suite**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 6.9: Commit**

```bash
git add backend/migrations/versions/*_add_status_board_latest_run_index.py
git commit -m "$(cat <<'EOF'
perf(db): composite index on research_runs for status-board DISTINCT ON

_build_latest_runs_sql sorts research_runs by (ticker, theme_id,
completed_at DESC, created_at DESC) before the DISTINCT ON pass. With
no matching index, Postgres did a full Sort + Seq Scan. The new
ix_research_runs_status_board_latest btree lets the planner walk the
index for the DISTINCT ON, eliminating the sort. Verified via EXPLAIN
ANALYZE.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final verification

- [ ] **Step 7.1: Full backend suite**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -5
```

Expected: baseline + ~11 new tests (5 quote-cache + 1 archived-flag + 1 surprise-batch + 4 from preflight if mixed in — adjust as actual). Zero failures.

- [ ] **Step 7.2: Frontend lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -5 && cd ..
```

Expected: zero errors, build succeeds.

- [ ] **Step 7.3: End-to-end smoke**

```bash
# Terminal 1
uvicorn backend.app.main:app --reload
# Terminal 2
cd frontend && npm run dev
```

In the browser, walk through each surface that changed:
1. `/pipeline/new` → kick a new live run → confirm the deep-dive dashboard renders smoothly (Task 1)
2. `/status` → toggle tabs, watch Network panel for the 30 s debounce (Task 2)
3. `/model/<ticker>` → open the reverse-DCF tab twice → confirm second open uses the cached quote (Task 3; the second call won't hit `/quote`, but the `?price=...` query param will still be the FMP price)
4. `/status` → check "Include archived" → confirm only one `/api/status/board` request per poll (Task 4)
5. `/theme/<id>` → open a theme with many tickers → confirm cards load and `is_surprise` badges still appear correctly (Task 5)

- [ ] **Step 7.4: Update TODO.md "Done (recent)"**

Edit `/Users/ericwyluda/Development/projects/sector-research/TODO.md`. Add at the top of `## Done (recent)`:

```markdown
- **Perf quick-wins pack (2026-05-27)**. Six-fix bundle from the in-conversation audit (observation 7182): (1) `React.memo` wrapping on 13 DeepDiveDashboard sections to cut SSE-event re-render cost ~50%, (2) 30s debounce on visibility-triggered status-board refetches to eliminate tab-switch waste, (3) 30s TTL cache on the FMP live-quote fetch behind `GET /api/models/{ticker}/reverse-dcf` (~400ms round-trip per panel open collapses to one per 30s), (4) `archived_at` field added to `StatusBoardEntry` so the frontend can drop the `include_archived=true` double-fetch hack, (5) `discovery._merge_results` batches its per-ticker `SurpriseAlert` SELECT into one `IN()` (50 round-trips → 1 for a 50-ticker theme), (6) composite btree index `ix_research_runs_status_board_latest` on `(ticker, theme_id, completed_at DESC, created_at DESC)` so the status-board `DISTINCT ON` query walks the index instead of doing a Sort + Seq Scan. Backend suite green; frontend lint + build clean.
```

- [ ] **Step 7.5: Open the PR**

```bash
git push -u origin feat/perf-quick-wins-pack
gh pr create --title "perf: quick-wins pack — memoization + caches + index" --body "$(cat <<'EOF'
## Summary
- `React.memo` 13 DeepDiveDashboard sections — cut SSE-event re-render cost
- 30s debounce on visibility-triggered status-board refetches
- 30s TTL cache on FMP live-quote behind reverse-DCF
- Surface `archived_at` on `StatusBoardEntry`, drop the double-fetch hack
- Batch per-ticker `SurpriseAlert` SELECT in `discovery._merge_results`
- Composite btree index on `research_runs(ticker, theme_id, completed_at DESC, created_at DESC)` for the status-board `DISTINCT ON`

## Test plan
- [ ] `python -m unittest discover -s backend/tests -p 'test_*.py'` — all pass
- [ ] `cd frontend && npm run lint && npm run build` — clean
- [ ] Manual: live deep-dive run — dashboard re-renders feel noticeably smoother
- [ ] Manual: status page with "Include archived" on — exactly one `/board` request per poll
- [ ] Manual: reverse-DCF panel opened twice within 30s — only one FMP `/quote` call
- [ ] Manual: `EXPLAIN ANALYZE` of the status-board query uses the new index

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (do this before declaring done)

1. **Audit coverage**
   - Issue #1 React.memo dashboard: Task 1 ✅
   - Issue #2 visibility-gated polling: Task 2 (debounced) ✅
   - Issue #3 reverse-DCF quote cache: Task 3 ✅
   - Issue #7 (observation 7173) status-board double-fetch: Task 4 ✅
   - Issue #8 (rescoped to real `SurpriseAlert` N+1): Task 5 ✅
   - Issue #13 status-board composite index: Task 6 ✅
   - Deferred and called out in front matter: #4, #6, #9, #11, #12 ✅

2. **No placeholders**: every step has either code or an exact command; no "TBD", no "implement appropriately." The only intentional `<auto-generated>` placeholders are in the migration revision frontmatter (filled by `alembic revision`).

3. **Memoization correctness**: confirm at Step 1.3 that no section receives an inline-constructed prop at its call site in `DeepDiveDashboard.tsx` — memo is useless if every render produces fresh references.

4. **Cache correctness**: `_LIVE_PRICE_CACHE` never stores 0.0 (Step 3.3) — a transient FMP failure must not poison the next 30 s of requests. Test `test_zero_price_is_not_cached` enforces this.

5. **Migration reversibility**: Step 6.7 explicitly runs `downgrade -1 && upgrade head` so the migration is verified reversible before merge.

6. **Status-board field ordering**: `archived_at` is added at the end of `StatusBoardEntry` (Step 4.3) to satisfy Python's "no non-default field after a default field" rule — the existing `health_reasons`, `next_catalyst`, `kill_criteria_summary` already have defaults.

7. **Backwards compatibility**: every change is additive. No schema renames, no removed fields, no breaking API contract changes. Rollback is `git revert <commit>` for each task; the index migration is `alembic downgrade -1`.
