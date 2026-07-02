# Post-Campaign Fix Pack + Fill-In Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three known daily-use dead ends (issue #52 earnings deep link, seed-only 8-K dead end, snoozed-question invisibility) and burn down the six parked fill-in items (kick-off hook extraction, ValidationCard `any`s, DifferentiationCard badge, lib/api placement, FMP citation persistence, correlated metric-guard extension).

**Architecture:** Two independent PRs. **Part A** (`fix/post-campaign-fix-pack`, Tasks 1–7) is user-facing fixes: a new `post_pending` earnings-board phase, an orphan-events section on `/status`, and a snoozed-questions view + unsnooze endpoint. **Part B** (`chore/fill-in-polish-pack`, Tasks 8–14) is refactors + two small backend behavior changes (citations, guards). Part A merges before Part B starts (both touch `EarningsDrawer.tsx`).

**Tech Stack:** FastAPI + async SQLAlchemy (stdlib `unittest`), Next.js 16 + React 19 (node --test for lib code; no component tests exist — UI verified via tsc/lint/build + live smoke).

**Conventions that apply to every task** (from CLAUDE.md):
- Backend tests from project root with venv active: `source backend/venv/bin/activate` then `python -m unittest backend.tests.<module>`. Full suite: `python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')`. Lint: `ruff check backend`.
- Frontend from `frontend/`: `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`.
- Frontend colors: token classes only (`bg-[var(--surface)]` etc.); semantic accent palettes (amber/rose/emerald/blue) are allowed and used by existing badges. No `slate-*`/`gray-*`/`zinc-*`.
- `frontend/AGENTS.md`: Next.js 16 — check `node_modules/next/dist/docs/` before assuming any App Router API.
- Do NOT add `from __future__ import annotations` to `backend/app/api/questions.py` (FastAPI 0.115 + py3.12 footgun, documented in the file header).

## File structure

**Part A:**
- Modify: `backend/app/api/earnings.py` (extract `_choose_print`, new `post_pending` phase)
- Create: `backend/tests/test_earnings_board_selection.py`
- Modify: `backend/app/services/questions.py` (`_snoozed` predicate, `snoozed` virtual status)
- Modify: `backend/app/api/questions.py` (unsnooze endpoint)
- Modify: `backend/tests/test_questions_api.py` (snoozed filter + unsnooze tests)
- Modify: `frontend/lib/api/status.ts` (`VerdictPhase` union, `questions.unsnooze`)
- Modify: `frontend/components/status/EarningsDrawer.tsx` (`PendingActualsBlock`)
- Modify: `frontend/app/status/page.tsx` (post_pending badge; orphan section wiring)
- Create: `frontend/lib/orphanEvents.ts` + `frontend/lib/orphanEvents.test.mts`
- Create: `frontend/components/status/OrphanEventsSection.tsx`
- Modify: `frontend/lib/questions-ui.ts` + `frontend/lib/questions-ui.test.mts` (snoozed filter value)
- Modify: `frontend/app/questions/page.tsx`, `frontend/components/questions/QuestionRow.tsx`

**Part B:**
- Create: `frontend/lib/hooks/useWorkspaceKickoff.ts`
- Modify: `frontend/components/status/WorkspaceButton.tsx`, `frontend/components/deep-dive/ReportHeader.tsx`, `frontend/components/workspace/RetryRunButton.tsx`
- Modify: `frontend/components/workspace/StepCards/ValidationCard.tsx`, `frontend/components/workspace/StepCards/DifferentiationCard.tsx`
- Create: `frontend/lib/api/peers.ts`; Modify: `frontend/lib/api/workspace.ts`, `frontend/lib/api/index.ts`, `frontend/lib/api/catalysts.ts`, `frontend/lib/api/themes.ts`, `frontend/lib/api/pipeline.ts`, `frontend/lib/format.ts` + fmt-helper importers
- Modify: `backend/app/graph/deep_dive_helpers.py`, `backend/app/graph/nodes.py`, `backend/tests/test_deep_dive_helpers.py`
- Modify: `backend/app/services/metric_guards.py`, `backend/app/services/company_snapshot.py`, `backend/app/services/peer_comp.py`, `backend/tests/test_metric_scaling.py`

---

# PART A — fix pack (branch `fix/post-campaign-fix-pack`)

- [ ] **Setup:** `git checkout main && git pull && git checkout -b fix/post-campaign-fix-pack`

### Task 1: Earnings board — `post_pending` phase (issue #52, backend)

The bug: `backend/app/api/earnings.py:161-169` picks `post` (eps_actual NOT NULL) or `upcoming` (null actuals, date ≥ today). Yesterday's print with null actuals (the 21:00 cron hasn't refreshed) is neither → the board row is dropped → `/status?expand_earnings=<run_id>` silently no-ops.

**Files:**
- Modify: `backend/app/api/earnings.py` (selection logic ~lines 150–171, sort_key ~line 211)
- Create: `backend/tests/test_earnings_board_selection.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_earnings_board_selection.py`:

```python
"""Unit tests for the earnings-board print-selection helper (issue #52)."""
import os
import unittest
from datetime import date

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.api.earnings import _choose_print
from backend.app.models.earnings_print import EarningsPrint


def _print(**over) -> EarningsPrint:
    base = dict(
        ticker="ORCL",
        fiscal_year=2026,
        fiscal_quarter=4,
        earnings_date=date(2026, 6, 10),
        eps_estimated=1.5,
        eps_actual=None,
    )
    base.update(over)
    return EarningsPrint(**base)


TODAY = date(2026, 6, 11)


class ChoosePrintTests(unittest.TestCase):
    def test_reported_print_is_post(self):
        chosen, phase = _choose_print([_print(eps_actual=1.62)], TODAY)
        self.assertEqual(phase, "post")

    def test_past_print_awaiting_actuals_is_post_pending(self):
        # Issue #52 repro: yesterday's print, nightly refresh hasn't landed.
        p = _print(earnings_date=date(2026, 6, 10), eps_actual=None)
        chosen, phase = _choose_print([p], TODAY)
        self.assertIs(chosen, p)
        self.assertEqual(phase, "post_pending")

    def test_future_print_is_pre(self):
        _, phase = _choose_print([_print(earnings_date=date(2026, 6, 20))], TODAY)
        self.assertEqual(phase, "pre")

    def test_today_print_without_actuals_is_pre(self):
        # Dated today (e.g. reports after close tonight) → still upcoming.
        _, phase = _choose_print([_print(earnings_date=TODAY)], TODAY)
        self.assertEqual(phase, "pre")

    def test_reported_beats_pending(self):
        reported = _print(earnings_date=date(2026, 6, 1), eps_actual=1.62)
        pending = _print(earnings_date=date(2026, 6, 10))
        chosen, phase = _choose_print([pending, reported], TODAY)
        self.assertIs(chosen, reported)
        self.assertEqual(phase, "post")

    def test_pending_beats_upcoming(self):
        pending = _print(earnings_date=date(2026, 6, 10))
        upcoming = _print(earnings_date=date(2026, 6, 24))
        chosen, phase = _choose_print([upcoming, pending], TODAY)
        self.assertIs(chosen, pending)
        self.assertEqual(phase, "post_pending")

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(_choose_print([], TODAY))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it — expect ImportError**

Run: `python -m unittest backend.tests.test_earnings_board_selection -v`
Expected: FAIL — `ImportError: cannot import name '_choose_print'`

- [ ] **Step 3: Implement `_choose_print` and wire it into the endpoint**

In `backend/app/api/earnings.py`, add `from collections.abc import Sequence` to the imports, then add this module-level helper above `get_earnings_board`:

```python
def _choose_print(
    candidates: Sequence[EarningsPrint], today: date
) -> tuple[EarningsPrint, str] | None:
    """Pick the board print + phase for one thesis row.

    Precedence: most recent reported print ("post") > most recent past
    print awaiting actuals ("post_pending") > upcoming print ("pre").
    `candidates` must be ordered earnings_date DESC (the board query does
    this). A past print with null actuals is the issue-#52 morning-after
    case: FMP's nightly earnings refresh (21:00) hasn't filled actuals yet.
    """
    post = next((p for p in candidates if p.eps_actual is not None), None)
    if post is not None:
        return post, "post"
    pending = next(
        (p for p in candidates if p.eps_actual is None and p.earnings_date < today),
        None,
    )
    if pending is not None:
        return pending, "post_pending"
    upcoming = next(
        (p for p in candidates if p.eps_actual is None and p.earnings_date >= today),
        None,
    )
    if upcoming is not None:
        return upcoming, "pre"
    return None
```

In `get_earnings_board`, replace this block (currently ~lines 160–171):

```python
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
```

with:

```python
        chosen_phase = _choose_print(candidates, today)
        if chosen_phase is None:
            continue
        chosen, phase = chosen_phase
```

And update `sort_key` (currently ~line 211) so `post_pending` sorts with the post group:

```python
    def sort_key(e: EarningsBoardEntry) -> tuple[int, int]:
        if e.print is None:
            return (2, 0)
        ord_ = e.print.earnings_date.toordinal()
        if e.phase in ("post", "post_pending"):
            return (0, -ord_)
        return (1, ord_)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m unittest backend.tests.test_earnings_board_selection -v`
Expected: 7 tests PASS. Also run `ruff check backend` — clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/earnings.py backend/tests/test_earnings_board_selection.py
git commit -m "fix(earnings): include past prints awaiting actuals as post_pending (issue #52)"
```

### Task 2: Earnings board — `post_pending` frontend

**Files:**
- Modify: `frontend/lib/api/status.ts` (~line 178)
- Modify: `frontend/components/status/EarningsDrawer.tsx` (dispatcher ~lines 55–60, new block)
- Modify: `frontend/app/status/page.tsx` (badge chain ~lines 654–678)

- [ ] **Step 1: Extend the phase union**

In `frontend/lib/api/status.ts`:

```typescript
export type VerdictPhase = "pre" | "post" | "post_pending" | "none";
```

- [ ] **Step 2: Add the drawer block**

In `frontend/components/status/EarningsDrawer.tsx`, extend the dispatcher — insert before the final `return <PreEarningsBlock entry={entry} />;`:

```typescript
  if (entry.phase === "post_pending") return <PendingActualsBlock entry={entry} />;
```

Add the block (place it between the Pre-print and Post-print sections; `fmtUSD` is the file's existing local helper used by `PreEarningsBlock`):

```tsx
// ── Post-print, actuals pending (issue #52) ─────────────────────────────────

function PendingActualsBlock({ entry }: { entry: EarningsBoardEntry }) {
  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-[var(--bg)]/40 border-t border-[var(--surface)]">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-[var(--text-muted)]">
        <span><span className="text-[var(--text-faint)]">Reported:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-[var(--text-faint)]">EPS est:</span> {p.eps_estimated?.toFixed(2) ?? "—"}</span>
        <span><span className="text-[var(--text-faint)]">Rev est:</span> {fmtUSD(p.revenue_estimated)}</span>
      </div>
      <p className="mt-2 text-xs text-amber-400">
        Awaiting actuals — the nightly earnings refresh (21:00) hasn&apos;t landed yet. Estimates shown.
      </p>
    </div>
  );
}
```

- [ ] **Step 3: Add the board badge**

In `frontend/app/status/page.tsx`, in the badge IIFE, insert between the `if (eb.phase === "post")` block and the `if (eb.phase === "pre")` block:

```tsx
                        if (eb.phase === "post_pending") {
                          const days = daysSince(eb.print.earnings_date);
                          return (
                            <button
                              onClick={onClick}
                              data-print-hide="true"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-semibold"
                            >
                              📊 {days}d ago · pending
                            </button>
                          );
                        }
```

No change to the `expand_earnings` effect — the board row now exists, so `earningsByRun[runId]` resolves and the existing one-shot logic opens the drawer.

- [ ] **Step 4: Gates**

Run from `frontend/`: `npm run typecheck && npm run lint`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/status.ts frontend/components/status/EarningsDrawer.tsx frontend/app/status/page.tsx
git commit -m "fix(earnings): post_pending board badge + awaiting-actuals drawer block (issue #52)"
```

### Task 3: Orphan-events derive helper

**Files:**
- Create: `frontend/lib/orphanEvents.ts`
- Create: `frontend/lib/orphanEvents.test.mts`

- [ ] **Step 1: Write the failing test**

Create `frontend/lib/orphanEvents.test.mts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { deriveOrphanEvents } from "./orphanEvents.ts";
import type { MaterialEvent } from "./api/status.ts";

function mkEvent(ticker: string, over: Partial<MaterialEvent> = {}): MaterialEvent {
  return {
    id: `${ticker}-1`,
    ticker,
    event_type: "guidance",
    materiality: "high",
    headline: "h",
    summary: "s",
    item_codes: null,
    filing_date: "2026-06-10",
    document_url: null,
    dismissed_at: null,
    group_count: 1,
    group_member_ids: [],
    group_headlines: [],
    ...over,
  };
}

test("board tickers are excluded", () => {
  const out = deriveOrphanEvents(
    { NVDA: [mkEvent("NVDA")], ERIC: [mkEvent("ERIC")] },
    new Set(["NVDA"]),
  );
  assert.deepEqual(out.map((g) => g.ticker), ["ERIC"]);
});

test("empty event lists are dropped", () => {
  assert.deepEqual(deriveOrphanEvents({ ERIC: [] }, new Set()), []);
});

test("groups sort by ticker", () => {
  const out = deriveOrphanEvents(
    { ZS: [mkEvent("ZS")], ANET: [mkEvent("ANET")] },
    new Set(),
  );
  assert.deepEqual(out.map((g) => g.ticker), ["ANET", "ZS"]);
});
```

- [ ] **Step 2: Run — expect module-not-found**

Run from `frontend/`: `node --test lib/orphanEvents.test.mts`
Expected: FAIL — cannot find `./orphanEvents.ts`.

- [ ] **Step 3: Implement**

Create `frontend/lib/orphanEvents.ts`:

```typescript
import type { MaterialEvent } from "./api/status";

export interface OrphanEventGroup {
  ticker: string;
  events: MaterialEvent[];
}

/**
 * Events on tickers with no status-board entry (theme seeds without an
 * active thesis). Board tickers render their events inside board rows;
 * everything else needs OrphanEventsSection or the ?expand_events= deep
 * link dead-ends (TODO.md backlog item).
 */
export function deriveOrphanEvents(
  eventsByTicker: Record<string, MaterialEvent[]>,
  boardTickers: ReadonlySet<string>,
): OrphanEventGroup[] {
  return Object.entries(eventsByTicker)
    .filter(([ticker, events]) => !boardTickers.has(ticker) && events.length > 0)
    .map(([ticker, events]) => ({ ticker, events }))
    .sort((a, b) => a.ticker.localeCompare(b.ticker));
}
```

- [ ] **Step 4: Run — expect pass**

Run: `node --test lib/orphanEvents.test.mts` → 3 PASS. Then `npm run typecheck` → clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/orphanEvents.ts frontend/lib/orphanEvents.test.mts
git commit -m "feat(status): orphan-events derive helper"
```

### Task 4: Orphan-events section on /status

**Files:**
- Create: `frontend/components/status/OrphanEventsSection.tsx`
- Modify: `frontend/app/status/page.tsx` (expand_events effect ~lines 443–455; render before `</main>` ~line 747)

- [ ] **Step 1: Create the section component**

Create `frontend/components/status/OrphanEventsSection.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { OrphanEventGroup } from "@/lib/orphanEvents";
import { MaterialEventsDrawer } from "./MaterialEventsDrawer";

interface Props {
  groups: OrphanEventGroup[];
  /** One-shot deep-link target: ?expand_events= ticker with no board row. */
  autoExpandTicker?: string | null;
  onDismissed: (ticker: string, eventId: string) => void;
}

/**
 * Material events on tickers with no status-board entry. Without this
 * section a /status?expand_events= deep link from Today silently no-ops
 * for seed-only tickers.
 */
export function OrphanEventsSection({ groups, autoExpandTicker, onDismissed }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (autoExpandTicker) {
      setExpanded((prev) => (prev[autoExpandTicker] ? prev : { ...prev, [autoExpandTicker]: true }));
    }
  }, [autoExpandTicker]);

  if (groups.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Material events — untracked tickers
      </h2>
      {groups.map((g) => (
        <div key={g.ticker} className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center gap-3 px-3 py-2">
            <Link
              href={`/company/${g.ticker}`}
              className="font-mono font-bold text-sm text-[var(--text)] hover:text-[var(--primary)]"
            >
              {g.ticker}
            </Link>
            <span className="text-xs text-[var(--text-muted)] truncate flex-1">
              {g.events[0].headline}
            </span>
            <button
              type="button"
              data-print-hide="true"
              onClick={() => setExpanded((prev) => ({ ...prev, [g.ticker]: !prev[g.ticker] }))}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-semibold"
            >
              8-K ×{g.events.length}
            </button>
          </div>
          {expanded[g.ticker] && (
            <div className="border-t border-[var(--border)]">
              <MaterialEventsDrawer
                items={g.events}
                onDismissed={(id) => onDismissed(g.ticker, id)}
              />
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
```

- [ ] **Step 2: Wire it into the status page**

In `frontend/app/status/page.tsx`:

a) Imports (top of file, with the other imports):

```typescript
import { deriveOrphanEvents } from "@/lib/orphanEvents";
import { OrphanEventsSection } from "@/components/status/OrphanEventsSection";
```

(If the page imports sibling components with relative paths, match that style instead.)

b) State + derivation (near the other `useState`/`useMemo` declarations; add `useMemo` to the React import if absent):

```typescript
  const [orphanAutoExpand, setOrphanAutoExpand] = useState<string | null>(null);
  const orphanGroups = useMemo(
    () => deriveOrphanEvents(eventsByTicker, new Set(entries.map((e) => e.ticker))),
    [eventsByTicker, entries],
  );
```

c) Replace the `expand_events` one-shot effect (~lines 443–455) with:

```typescript
  const expandEventsConsumed = useRef(false);
  useEffect(() => {
    if (expandEventsConsumed.current) return;
    const ticker = new URLSearchParams(window.location.search)
      .get("expand_events")
      ?.toUpperCase();
    if (!ticker || entries.length === 0) return;
    const entry = entries.find((en) => en.ticker === ticker);
    const hasEvents = (eventsByTicker[ticker] ?? []).length > 0;
    if (entry && hasEvents) {
      expandEventsConsumed.current = true;
      setEventsExpanded((prev) => ({ ...prev, [entry.run_id]: true }));
    } else if (!entry && hasEvents) {
      // Seed-only ticker: no board row — open its orphan-section drawer.
      expandEventsConsumed.current = true;
      setOrphanAutoExpand(ticker);
    }
  }, [entries, eventsByTicker]);
```

d) Render the section just before the closing `</main>` (~line 747):

```tsx
      <OrphanEventsSection
        groups={orphanGroups}
        autoExpandTicker={orphanAutoExpand}
        onDismissed={handleEventDismissed}
      />
```

(`handleEventDismissed(ticker, eventId)` already exists at ~line 495 and updates `eventsByTicker` — its signature matches the prop exactly.)

- [ ] **Step 3: Gates + live smoke**

`npm run typecheck && npm run lint` → clean.
Live smoke (optional but recommended): backend on test DB (`DATABASE_URL="postgresql+asyncpg://ericwyluda@localhost:5432/sector_research_test" uvicorn backend.app.main:app --reload`), `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev`; open `/status` and confirm the section appears only when a non-board ticker has events; visit `/status?expand_events=<such ticker>` and confirm the drawer auto-opens.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/status/OrphanEventsSection.tsx frontend/app/status/page.tsx
git commit -m "feat(status): render seed-only ticker events outside the board loop"
```

### Task 5: Snoozed questions — backend filter + unsnooze endpoint

**Files:**
- Modify: `backend/app/services/questions.py` (~lines 28–57)
- Modify: `backend/app/api/questions.py` (new endpoint after `dismiss_endpoint`/`resolve_endpoint`)
- Modify: `backend/tests/test_questions_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_questions_api.py` (reuse the file's existing `_question` factory, `_build_async_test_session` helper, and imports; extend the import block with `from backend.app.api.questions import unsnooze_endpoint` and `from fastapi import HTTPException` — plus `uuid`/`datetime` symbols if not already imported):

```python
class SnoozedFilterTests(unittest.TestCase):
    def test_snoozed_filter_returns_only_active_snoozes(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(_question(question_text="open-now"))
                db.add(_question(
                    question_text="active-snooze",
                    snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                ))
                db.add(_question(
                    question_text="expired-snooze",
                    snoozed_until=datetime.now(timezone.utc) - timedelta(days=1),
                ))
                db.add(_question(question_text="dismissed", status="dismissed"))
                await db.commit()

                rows = await list_questions(db, status="snoozed")
                self.assertEqual([q.question_text for q in rows], ["active-snooze"])

        asyncio.run(_run())


class UnsnoozeEndpointTests(unittest.TestCase):
    def test_unsnooze_clears_and_rejoins_open_list(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                q = _question(
                    question_text="snoozed",
                    snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                )
                db.add(q)
                await db.commit()

                out = await unsnooze_endpoint(q.id, db)
                self.assertIsNone(out.snoozed_until)
                rows = await list_questions(db, status="open")
                self.assertEqual([r.question_text for r in rows], ["snoozed"])

        asyncio.run(_run())

    def test_unsnooze_is_idempotent_on_never_snoozed(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                q = _question(question_text="plain-open")
                db.add(q)
                await db.commit()
                out = await unsnooze_endpoint(q.id, db)
                self.assertIsNone(out.snoozed_until)

        asyncio.run(_run())

    def test_unsnooze_unknown_id_404s(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                with self.assertRaises(HTTPException) as ctx:
                    await unsnooze_endpoint(str(uuid.uuid4()), db)
                self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(_run())
```

- [ ] **Step 2: Run — expect failures**

Run: `python -m unittest backend.tests.test_questions_api -v`
Expected: ImportError on `unsnooze_endpoint`; snoozed-filter test would return `[]`.

- [ ] **Step 3: Implement**

In `backend/app/services/questions.py`, next to `_not_snoozed()` (ensure `and_` is in the `sqlalchemy` import line):

```python
def _snoozed():
    """Predicate: snooze set and unexpired (inverse of _not_snoozed)."""
    return and_(Question.snoozed_until.is_not(None), Question.snoozed_until > func.now())
```

In `list_questions`, replace:

```python
    if status:
        stmt = stmt.where(Question.status == status)
    if status == "open":
        # Snoozed questions drop out of the default open view until expiry.
        stmt = stmt.where(_not_snoozed())
```

with:

```python
    if status == "snoozed":
        # Virtual filter: snoozed rows are status="open" with an unexpired
        # snoozed_until — hidden from the default open view, surfaced here.
        stmt = stmt.where(Question.status == "open").where(_snoozed())
    elif status:
        stmt = stmt.where(Question.status == status)
    if status == "open":
        # Snoozed questions drop out of the default open view until expiry.
        stmt = stmt.where(_not_snoozed())
```

In `backend/app/api/questions.py`, add after `resolve_endpoint` (no body model needed):

```python
@router.post("/{question_id}/unsnooze", response_model=QuestionResponse)
async def unsnooze_endpoint(
    question_id: str,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    """Clear an active snooze so the question rejoins the open list.

    Idempotent: unsnoozing a never-/no-longer-snoozed open question is a
    no-op success.
    """
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    if q.status != "open":
        raise HTTPException(409, f"question is {q.status}, cannot unsnooze")
    if q.snoozed_until is not None:
        q.snoozed_until = None
        await db.commit()
        await db.refresh(q)
    return _serialize(q)
```

(`_normalize_status_filter` passes `"snoozed"` through unchanged — no API-layer change needed for the filter.)

- [ ] **Step 4: Run — expect pass**

`python -m unittest backend.tests.test_questions_api -v` → all PASS (existing + 4 new). `ruff check backend` → clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/questions.py backend/app/api/questions.py backend/tests/test_questions_api.py
git commit -m "feat(questions): snoozed status filter + unsnooze endpoint"
```

### Task 6: Snoozed questions — frontend view + unsnooze UI

**Files:**
- Modify: `frontend/lib/questions-ui.ts` (~line 2), `frontend/lib/questions-ui.test.mts`
- Modify: `frontend/lib/api/status.ts` (`questions` object, ~line 319)
- Modify: `frontend/app/questions/page.tsx` (statusFilter state ~line 33, select ~lines 183–194)
- Modify: `frontend/components/questions/QuestionRow.tsx`

- [ ] **Step 1: Failing test for the filter value**

Append to `frontend/lib/questions-ui.test.mts` (match the file's existing import style):

```typescript
test("snoozed status builds list path", () => {
  assert.equal(
    buildQuestionListPath({ status: "snoozed" }),
    "/api/questions?status=snoozed",
  );
});
```

Run: `node --test lib/questions-ui.test.mts` → FAIL (type error at typecheck; assert may pass at runtime — the gate is `npm run typecheck` rejecting `"snoozed"` until the union is extended).

- [ ] **Step 2: Extend the filter union**

In `frontend/lib/questions-ui.ts`:

```typescript
export type QuestionStatusFilter =
  | "open"
  | "snoozed"
  | "resolved_auto"
  | "resolved_inline"
  | "resolved_manual"
  | "dismissed"
  | "all";
```

- [ ] **Step 3: API client**

In `frontend/lib/api/status.ts`, add to the `questions` object (after `dismiss`):

```typescript
  unsnooze: async (id: string): Promise<Question> =>
    apiFetch<Question>(`/api/questions/${encodeURIComponent(id)}/unsnooze`, {
      method: "POST",
    }),
```

(`Question.snoozed_until: string | null` already exists in the interface — no type change needed.)

- [ ] **Step 4: Page filter option**

In `frontend/app/questions/page.tsx`:
- Change the state to use the shared filter type (import `QuestionStatusFilter` from `@/lib/questions-ui`, which the file already imports from):

```typescript
  const [statusFilter, setStatusFilter] = useState<QuestionStatusFilter>("open");
```

- Update the select's cast to `as QuestionStatusFilter` and add the option right after Open:

```tsx
            <option value="snoozed">Snoozed</option>
```

- If the existing `questionsApi.list` call's `status` param type complains, it already accepts `QuestionStatusFilter` (verified) — no change.

- [ ] **Step 5: QuestionRow snoozed chip + Unsnooze button**

In `frontend/components/questions/QuestionRow.tsx`, inside the component add:

```typescript
  const isSnoozed =
    question.snoozed_until != null && new Date(question.snoozed_until) > new Date();

  const handleUnsnooze = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const updated = await questionsApi.unsnooze(question.id);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };
```

Next to the status chip (after the `STATUS_LABEL` span):

```tsx
        {isSnoozed && (
          <span className="px-1.5 py-0.5 rounded text-xs font-medium border bg-amber-900/40 text-amber-200 border-amber-700/60">
            Snoozed until {question.snoozed_until!.slice(0, 10)}
          </span>
        )}
```

Inside the existing `{isOpen && (...)}` action row, add as the first button:

```tsx
          {isSnoozed && (
            <button
              type="button"
              onClick={handleUnsnooze}
              disabled={busy}
              className="px-2 py-1 text-xs rounded border border-amber-700 text-amber-200 hover:bg-amber-900/30 disabled:opacity-50"
            >
              Unsnooze
            </button>
          )}
```

- [ ] **Step 6: Gates**

`npm run typecheck && npm run lint && npm test` → clean/green (29 node tests incl. the new ones).

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/questions-ui.ts frontend/lib/questions-ui.test.mts frontend/lib/api/status.ts frontend/app/questions/page.tsx frontend/components/questions/QuestionRow.tsx
git commit -m "feat(questions): snoozed view + unsnooze UI"
```

### Task 7: Part A close-out — gates, docs, PR

- [ ] **Step 1: Full gates**

```bash
source backend/venv/bin/activate
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
ruff check backend
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```
Expected: backend suite green (836 + 11 new), frontend all green.

- [ ] **Step 2: Doc updates**

- `CLAUDE.md` — Material events section: update the sentence "deep link `/status?expand_events=<ticker>` — only resolves for tickers with a board entry; seed-only gap tracked in TODO" → "deep link `/status?expand_events=<ticker>`; seed-only tickers render in an Orphan-events section below the board". Questions blurb: append "+ `POST /api/questions/{id}/unsnooze` and a Snoozed filter view". Status section: note the `post_pending` earnings phase (past print awaiting actuals).
- `TODO.md` — remove the material-events-deep-link bullet from Backlog / v3; remove "snoozed-question visibility/unsnooze UI" from the loose-ends line; add a Done (recent) entry for the fix pack.

```bash
git add CLAUDE.md TODO.md && git commit -m "docs: fix-pack reconciliation (post_pending phase, orphan events, unsnooze)"
```

- [ ] **Step 3: PR + merge**

```bash
git push -u origin fix/post-campaign-fix-pack
gh pr create --title "Post-campaign fix pack: earnings pending-actuals, orphan 8-K events, question unsnooze" --body "Closes #52.

- Earnings board: past prints with null actuals now surface as \`post_pending\` — the /status?expand_earnings deep link works the morning after a print.
- /status renders material events for seed-only tickers (no board row) in a new orphan-events section; ?expand_events deep links auto-open it.
- Questions: \`snoozed\` filter view + per-row Unsnooze (\`POST /api/questions/{id}/unsnooze\`).

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Wait for CI green, merge (note: gh API 401s have occurred on PR merges — fall back to `git checkout main && git merge --no-ff fix/post-campaign-fix-pack && git push` if `gh pr merge` fails), confirm issue #52 auto-closed.

---

# PART B — fill-in polish pack (branch `chore/fill-in-polish-pack`)

- [ ] **Setup:** Part A merged. `git checkout main && git pull && git checkout -b chore/fill-in-polish-pack`

### Task 8: Extract `useWorkspaceKickoff` (3 copies)

**Files:**
- Create: `frontend/lib/hooks/useWorkspaceKickoff.ts`
- Modify: `frontend/components/status/WorkspaceButton.tsx` (~lines 24–36), `frontend/components/deep-dive/ReportHeader.tsx` (~lines 100–114), `frontend/components/workspace/RetryRunButton.tsx` (~lines 26–38)

- [ ] **Step 1: Create the hook**

Create `frontend/lib/hooks/useWorkspaceKickoff.ts` (sibling of `useWorkspacePreflight.ts`):

```typescript
"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";

/**
 * Shared workspace kick-off: route to the in-flight run if one exists,
 * otherwise POST a new run and route to it. Extracted from the three
 * identical closures in WorkspaceButton / ReportHeader / RetryRunButton.
 */
export function useWorkspaceKickoff(opts: {
  ticker: string;
  researchRunId?: string | null;
  inFlightRunId?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const kickOff = useCallback(async () => {
    if (opts.inFlightRunId) {
      router.push(`/workspace/${opts.inFlightRunId}`);
      return;
    }
    setBusy(true);
    try {
      const { run_id } = await workspaceApi.kickOff(
        opts.ticker,
        opts.researchRunId ?? undefined,
      );
      router.push(`/workspace/${run_id}`);
    } catch (err) {
      alert(`Workspace kick-off failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(false);
    }
  }, [opts.ticker, opts.researchRunId, opts.inFlightRunId, router]);

  return { kickOff, busy };
}
```

- [ ] **Step 2: Migrate the three call sites**

a) `WorkspaceButton.tsx` — add `const { kickOff } = useWorkspaceKickoff({ ticker, researchRunId, inFlightRunId });` and replace the onClick closure body:

```tsx
onClick={(ev) => {
  ev.stopPropagation();
  void kickOff();
}}
```

b) `ReportHeader.tsx` — delete `handleWorkspaceRefresh` and its local `loading` state; add `const { kickOff, busy } = useWorkspaceKickoff({ ticker, researchRunId: runId, inFlightRunId });` and point the button's `onClick` at `kickOff`, replacing former `loading` reads with `busy`.

c) `RetryRunButton.tsx` — add `const { kickOff } = useWorkspaceKickoff({ ticker, inFlightRunId });` and replace the onClick closure body the same way as (a).

In all three: remove now-orphaned `workspaceApi` / `useRouter` imports and `router` variables your change made unused (lint will flag them). Behavior note: (a) and (c) had no loading state before — don't add disabled wiring there; only ReportHeader keeps its loading affordance via `busy`.

- [ ] **Step 3: Gates + commit**

`npm run typecheck && npm run lint` → clean.

```bash
git add frontend/lib/hooks/useWorkspaceKickoff.ts frontend/components/status/WorkspaceButton.tsx frontend/components/deep-dive/ReportHeader.tsx frontend/components/workspace/RetryRunButton.tsx
git commit -m "refactor(workspace): extract useWorkspaceKickoff hook (3 copies)"
```

### Task 9: Type ValidationCard's two `any` adapters

**Files:**
- Modify: `frontend/components/workspace/StepCards/ValidationCard.tsx` (~lines 14–33)

- [ ] **Step 1: Replace the adapters**

Add `ReverseDcfResponse` and `SensitivityGrid` to the existing `@/lib/api` type import (both exported from `lib/api/model.ts` via the barrel; no name clash — the workspace shape is `WorkspaceSensitivityGrid`). Replace both adapters and delete the two `eslint-disable-next-line @typescript-eslint/no-explicit-any` comments:

```typescript
function toModelGrid(g: WorkspaceSensitivityGrid): SensitivityGrid {
  return {
    x_dim: g.dim_x,
    y_dim: g.dim_y,
    x_values: g.x_axis,
    y_values: g.y_axis,
    values: g.values,
  };
}

function toModelThesisRows(
  rows: ValidationOutput["thesis_vs_priced_in"],
): ReverseDcfResponse["thesis_vs_priced_in"] {
  return rows.map((r) => ({
    dimension: r.metric,
    thesis: r.thesis_value,
    priced_in: r.priced_in_value,
    delta: r.delta_pct,
  }));
}
```

(`SensitivityHeatmap` takes `grid: SensitivityGrid`; `ThesisVsPricedTable` takes `rows: ReverseDcfResponse["thesis_vs_priced_in"]` — both verified.)

- [ ] **Step 2: Gates + commit**

`npm run typecheck && npm run lint` → clean.

```bash
git add frontend/components/workspace/StepCards/ValidationCard.tsx
git commit -m "refactor(workspace): type ValidationCard adapters, drop the last two anys"
```

### Task 10: DifferentiationCard — human-readable read-through badge

**Files:**
- Modify: `frontend/components/workspace/StepCards/DifferentiationCard.tsx` (badge ~line 33)

- [ ] **Step 1: Replace the raw `event_key` badge**

Add at module level:

```typescript
const READ_THROUGH_LABEL: Record<string, string> = {
  earnings: "Earnings",
  run_complete: "Run completed",
};
```

Replace the read-through `<li>` body (currently a raw `{rt.event_key}` badge + `{rt.peer_ticker} · {rt.event_type}` span) with:

```tsx
              <li key={i} className="text-sm text-[var(--text)]">
                <span
                  title={rt.event_key}
                  className="text-xs px-1 rounded mr-2 bg-[var(--surface-alt)] text-[var(--text-muted)]"
                >
                  {READ_THROUGH_LABEL[rt.event_type] ?? rt.event_type} · {rt.event_date}
                </span>
                <span className="text-[var(--text-muted)]">
                  {rt.peer_ticker}
                  {typeof rt.payload.description === "string" && ` — ${rt.payload.description}`}
                </span>
              </li>
```

(Raw keys look like `earnings:ORCL:2026-06-15` / `run_complete:<uuid>` — kept in the `title` tooltip. `payload.description` is the human catalyst description on earnings read-throughs; `payload` is `Record<string, unknown>`, hence the typeof guard.)

- [ ] **Step 2: Gates + commit**

`npm run typecheck && npm run lint` → clean.

```bash
git add frontend/components/workspace/StepCards/DifferentiationCard.tsx
git commit -m "fix(workspace): human-readable read-through badge in DifferentiationCard"
```

### Task 11: lib/api placement — peers module, getSignalHistory, fmt helpers

**Files:**
- Create: `frontend/lib/api/peers.ts`
- Modify: `frontend/lib/api/workspace.ts`, `frontend/lib/api/index.ts`, `frontend/lib/api/catalysts.ts`, `frontend/lib/api/themes.ts`, `frontend/lib/api/pipeline.ts`, `frontend/lib/format.ts`, plus fmt-helper importers

- [ ] **Step 1: Move the peers domain out of workspace.ts**

Create `frontend/lib/api/peers.ts` and move these five symbols verbatim from `workspace.ts` (~lines 85–133): `PeerCompRow`, `PeerCompTable`, `PeerSetResponse`, `PeerCompResponse`, `peersApi`. Header:

```typescript
import { apiFetch } from "./core";
```

In `workspace.ts`: delete the moved block; add `import type { PeerCompTable } from "./peers";` (used by `DifferentiationOutput`); do NOT re-export the moved names from workspace.ts (an `export *` collision in the barrel would be ambient). Remove the `apiFetch` import from workspace.ts if it's now unused.

In `frontend/lib/api/index.ts`, add:

```typescript
export * from "./peers";
```

- [ ] **Step 2: Move getSignalHistory to themes.ts**

Move the `getSignalHistory` function verbatim from `catalysts.ts` (~lines 56–67) to `themes.ts`, carrying its `import type { SignalHistoryResponse } from "./pipeline";` along (the type stays in pipeline.ts — it's referenced there). Remove the now-unused import from catalysts.ts if nothing else uses it.

- [ ] **Step 3: Move the fmt helpers to lib/format.ts**

Move `fmtMarketCap`, `fmtPct`, `fmtScore` verbatim from `frontend/lib/api/pipeline.ts` (~lines 521–536) to `frontend/lib/format.ts`. Add one doc line above `fmtPct`: `/** Fraction input (0.69 → "69.0%") — unlike formatPercent, which takes 0–100. */`

Then fix importers: `grep -rn "fmtMarketCap\|fmtPct\|fmtScore" frontend --include="*.ts" --include="*.tsx" | grep -v node_modules | grep "from"` — for each file importing these names from `@/lib/api` (candidates: `app/theme/[id]/ThemeDetailClient.tsx`, `components/deep-dive/sections/QuantFingerprint.tsx`, `components/deep-dive/ReportHeader.tsx`, `components/peers/PeerCompTable.tsx`, `components/company/StatementTable.tsx`, `components/company/fmtFinancial.ts`), change the import source to `@/lib/format`. Files with their own *local* helpers of the same name (`components/status/EarningsDrawer.tsx` defines local `fmtUSD`/`fmtPct`) are untouched. `npm run typecheck` is the completeness gate — it fails on any missed importer.

- [ ] **Step 4: Gates + commit**

`npm run typecheck && npm run lint && npm test && npm run build` → clean/green.

```bash
git add frontend/lib/api/ frontend/lib/format.ts $(git diff --name-only)
git commit -m "refactor(api): peers domain module; getSignalHistory → themes; fmt helpers → lib/format"
```

### Task 12: Persist FMP citations on research state

Citations are the app's core convention, but the 10 non-transcript primary FMP fetches and all 6 tier-2 fetches in `node_deep_dive` discard their `Citation` halves — only transcript + FRED citations land in `state.citations` today.

**Files:**
- Modify: `backend/app/graph/deep_dive_helpers.py`
- Modify: `backend/app/graph/nodes.py` (unpack ~line 297; tier-2 block ~line 317)
- Modify: `backend/tests/test_deep_dive_helpers.py`

- [ ] **Step 1: Failing helper tests**

Append to `backend/tests/test_deep_dive_helpers.py` (match the file's existing import style):

```python
class UnwrapGatherCitationTests(unittest.TestCase):
    def test_exception_slot_returns_none(self):
        self.assertIsNone(unwrap_gather_citation(RuntimeError("boom")))

    def test_tuple_slot_returns_citation_half(self):
        sentinel = object()
        self.assertIs(unwrap_gather_citation(("data", sentinel)), sentinel)

    def test_none_citation_passes_through(self):
        self.assertIsNone(unwrap_gather_citation(("data", None)))
```

Add `unwrap_gather_citation` to the file's import from `backend.app.graph.deep_dive_helpers`.

Run: `python -m unittest backend.tests.test_deep_dive_helpers -v` → ImportError.

- [ ] **Step 2: Implement the helper**

In `backend/app/graph/deep_dive_helpers.py`, below `unwrap_gather_result`:

```python
def unwrap_gather_citation(result: object):
    """Citation counterpart of unwrap_gather_result: pull the Citation half
    of a `(data, citation)` gather slot, or None for a failed slot."""
    if isinstance(result, BaseException):
        return None
    return result[1]  # type: ignore[index]
```

Run the helper tests → PASS.

- [ ] **Step 3: Wire into node_deep_dive**

In `backend/app/graph/nodes.py`:

a) Extend the line-37 import:

```python
from backend.app.graph.deep_dive_helpers import (
    unwrap_gather_citation,
    unwrap_gather_result as _unwrap,
)
```

b) Change the primary unpack (~line 297) from `(income, _), (balance, _), ...` to named citations:

```python
        (income, income_cit), (balance, balance_cit), (cashflow, cashflow_cit), (profile, profile_cit), (dcf, dcf_cit), (estimates, estimates_cit), (hist_prices, hist_cit), (transcripts, transcript_cit), (key_metrics, km_cit), (ratios_ttm, ratios_cit), (fin_growth, growth_cit) = (
```

(the `asyncio.gather(...)` call itself is unchanged), then add immediately after the closing paren:

```python
        # Persist the FMP citations alongside the data (previously discarded).
        # transcript_cit is handled separately below, gated on transcript
        # analysis succeeding. Note: a risk-loop re-run of this node appends
        # again — same convention as the FRED/transcript citations.
        for _cit in (income_cit, balance_cit, cashflow_cit, profile_cit, dcf_cit,
                     estimates_cit, hist_cit, km_cit, ratios_cit, growth_cit):
            if _cit is not None:
                state.add_citation(StateCitation.from_citation(_cit))
```

c) After the tier-2 `secondary = await asyncio.gather(...)` block's `_unwrap` lines (~line 325), add:

```python
        for _slot in secondary:
            _t2_cit = unwrap_gather_citation(_slot)
            if _t2_cit is not None:
                state.add_citation(StateCitation.from_citation(_t2_cit))
```

(`StateCitation` is already imported in nodes.py — used for the transcript citation at ~line 377.)

- [ ] **Step 4: Gates**

`python -m unittest backend.tests.test_deep_dive_helpers backend.tests.test_output_parsing -v` → green. `ruff check backend` → clean.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/deep_dive_helpers.py backend/app/graph/nodes.py backend/tests/test_deep_dive_helpers.py
git commit -m "feat(pipeline): persist FMP citations on research state"
```

### Task 13: Metric guards — null EBITDA-derived metrics on correlated corruption

Known case (PR #44 follow-up): ORCL's corrupt FY2026-Q4 statement (negative costOfRevenue) trips the tier-1 gross-margin guard, but the same corruption poisons EBITDA → `ebitdaMarginTTM` 9.2% (plausible-looking, wrong) and EV/EBITDA 113× pass through unguarded. Neither can be range-guarded without false positives — but the tier-1 gross trigger is a high-confidence corruption detector for that ticker's TTM aggregates, so null the EBITDA-derived siblings when it fires.

**Files:**
- Modify: `backend/app/services/metric_guards.py`
- Modify: `backend/app/services/company_snapshot.py` (Margins group ~line 163; Valuation group ~line 186)
- Modify: `backend/app/services/peer_comp.py` (`_fetch_one` ~lines 152–188)
- Modify: `backend/tests/test_metric_scaling.py`

- [ ] **Step 1: Write the failing tests (and fix the now-stale pin)**

In `backend/tests/test_metric_scaling.py`:

a) The existing `test_peer_row_nulls_corrupt_gross` asserts `self.assertAlmostEqual(row.ebitda_margin, 0.09206033433296713)` ("sibling margins untouched") — that pin is the old behavior. Change that line to `self.assertIsNone(row.ebitda_margin)`.

b) Add new tests (same class style as the existing ORCL tests; the recorded ORCL payloads already carry `ebitdaMarginTTM: 0.09206…` and `evToEBITDATTM: 113.487…`, and MSFT carries clean values `0.6314…` / `14.812…`):

```python
    async def test_overview_nulls_correlated_ebitda_metrics(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING"):
            ov = await build_company_overview(_StubFMP(), "ORCL")
        self.assertIsNone(_stat(ov, "Margins", "EBITDA"))
        self.assertIsNone(_stat(ov, "Valuation (TTM)", "EV/EBITDA"))
        # Operating is not EBITDA-derived — still passes through.
        self.assertAlmostEqual(_stat(ov, "Margins", "Operating"), 0.3059176341340301)

    async def test_clean_ticker_keeps_ebitda_metrics(self):
        ov = await build_company_overview(_StubFMP(), "MSFT")
        self.assertAlmostEqual(_stat(ov, "Margins", "EBITDA"), 0.6314044860858445)
        self.assertAlmostEqual(_stat(ov, "Valuation (TTM)", "EV/EBITDA"), 14.812080796580396)

    async def test_peer_row_nulls_correlated_ebitda_metrics(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING"):
            row = await _fetch_one("ORCL", _StubFMP())
        self.assertIsNone(row.ebitda_margin)
        self.assertIsNone(row.ev_ebitda)
```

(Wrap in the file's existing async-test runner pattern — the current tests run via `asyncio.run(...)` inside sync `test_` methods; mirror exactly. Note: peer_comp's `ev_ebitda` reads `enterpriseValueMultipleTTM` from the ratios payload first — the recorded ORCL ratios payload carries it.)

Run: `python -m unittest backend.tests.test_metric_scaling -v` → new tests FAIL (values pass through).

- [ ] **Step 2: Implement**

In `backend/app/services/metric_guards.py`, append:

```python
def gross_corruption(gross_margin: Optional[float]) -> bool:
    """True when grossProfitMarginTTM carries the impossible >1.0 corruption
    (the tier-1 trigger). Used to null sibling EBITDA-derived metrics from
    the same TTM aggregates — the corruption source (negative costOfRevenue)
    poisons EBITDA too, producing values that look individually plausible
    (live example 2026-06-10: ORCL EBITDA margin 9.2%, EV/EBITDA 113×)."""
    return gross_margin is not None and gross_margin > 1.0


def guard_correlated(
    value: Optional[float], *, corrupt: bool, metric: str, ticker: str
) -> Optional[float]:
    """Null an EBITDA-derived metric when the ticker's statement aggregates
    are known-corrupt (see gross_corruption). No-op otherwise."""
    if value is None or not corrupt:
        return value
    logger.warning(
        "nulling %s=%s for %s — correlated with impossible grossProfitMarginTTM",
        metric,
        value,
        ticker,
    )
    return None
```

In `backend/app/services/company_snapshot.py` (extend the `metric_guards` import with `gross_corruption, guard_correlated`): before the stat groups are built, compute

```python
    raw_gross = _f(ra, "grossProfitMarginTTM")
    corrupt = gross_corruption(raw_gross)
```

use `raw_gross` in the existing Gross `StatItem` (semantics unchanged: `guard_margin(raw_gross, metric="grossProfitMarginTTM", ticker=ticker)`), and wrap the two EBITDA-derived stats:

```python
    StatItem(label="EBITDA", value=guard_correlated(
        guard_margin(_f(ra, "ebitdaMarginTTM"), metric="ebitdaMarginTTM", ticker=ticker),
        corrupt=corrupt, metric="ebitdaMarginTTM", ticker=ticker,
    ), unit="pct"),
```

```python
    StatItem(label="EV/EBITDA", value=guard_correlated(
        _f(km, "evToEBITDATTM"), corrupt=corrupt, metric="evToEBITDATTM", ticker=ticker,
    ), unit="x"),
```

In `backend/app/services/peer_comp.py` `_fetch_one` (same import extension): hoist

```python
    raw_gross = _first((ratios, "grossProfitMarginTTM"))
    corrupt = gross_corruption(raw_gross)
```

use `raw_gross` in the `gross_margin=guard_margin(...)` kwarg, and wrap:

```python
    ev_ebitda=guard_correlated(
        _first(
            (ratios, "enterpriseValueMultipleTTM"),
            (km, "enterpriseValueOverEBITDATTM"),
        ),
        corrupt=corrupt, metric="ev_ebitda", ticker=ticker,
    ),
```

```python
    ebitda_margin=guard_correlated(
        guard_margin(
            _first((ratios, "ebitdaMarginTTM")),
            metric="ebitdaMarginTTM", ticker=ticker,
        ),
        corrupt=corrupt, metric="ebitdaMarginTTM", ticker=ticker,
    ),
```

- [ ] **Step 3: Run — expect pass**

`python -m unittest backend.tests.test_metric_scaling -v` → all green (updated pin + 3 new). `ruff check backend` → clean.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/metric_guards.py backend/app/services/company_snapshot.py backend/app/services/peer_comp.py backend/tests/test_metric_scaling.py
git commit -m "fix(metrics): null EBITDA-derived stats when gross-margin corruption detected"
```

### Task 14: Part B close-out — gates, docs, PR

- [ ] **Step 1: Full gates**

Same commands as Task 7 Step 1. Optional live smoke on the test DB: start a pipeline run on a cheap ticker and confirm the completed report's citation list now shows FMP entries (income statement, profile, DCF, etc.) grouped under the FMP source family; open `/company/ORCL` and confirm EBITDA + EV/EBITDA render "—".

- [ ] **Step 2: Doc updates**

- `CLAUDE.md`: lib/api blurb "12 domain modules" → "13 domain modules (… + `peers`)"; "Citations as a first-class primitive" section — note primary + tier-2 FMP citations now persist to `state.citations`; Peer comparison section — append the correlated-nulling rule (gross>1.0 tier-1 trigger also nulls `ebitdaMarginTTM` + EV/EBITDA in both builders).
- `TODO.md`: remove "Persist FMP citations on state" from Backlog / v3; clear the remaining loose-ends fragments (`useWorkspaceKickoff`, ValidationCard `any`s, `peersApi`/`getSignalHistory`/fmt placement, DifferentiationCard badge) from the In-progress line; add a Done (recent) entry.

```bash
git add CLAUDE.md TODO.md && git commit -m "docs: polish-pack reconciliation (peers module, citations, correlated guards)"
```

- [ ] **Step 3: PR + merge**

```bash
git push -u origin chore/fill-in-polish-pack
gh pr create --title "Fill-in polish pack: kickoff hook, typed adapters, api placement, FMP citations, correlated metric guards" --body "Burns down the parked TODO loose ends:

- \`useWorkspaceKickoff\` hook replaces 3 copied closures
- ValidationCard adapters typed (last 2 \`any\`s gone)
- DifferentiationCard read-through badge human-readable (raw event_key → tooltip)
- lib/api placement: new \`peers\` domain module, \`getSignalHistory\` → themes, fmt helpers → \`lib/format\`
- node_deep_dive persists FMP citations on state (primary + tier-2)
- Correlated metric guard: tier-1 gross corruption also nulls EBITDA margin + EV/EBITDA (ORCL follow-up from PR #44)

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```
Wait for CI green, merge (same gh-401 fallback as Task 7).

---

## Self-review notes (already applied)

- Precedence decision in `_choose_print`: reported > pending > upcoming. Pending-vs-upcoming coexistence within one ±14d window is near-impossible at quarterly cadence; pending-first matches the morning-after intent.
- The orphan-events `expand_events` fallback keeps the pre-existing `entries.length === 0` guard, so a deep link to an orphan ticker on a *completely empty* board still no-ops — acceptable (the board is never empty in practice) and noted in the code comment.
- `unwrap_gather_citation` returns untyped on purpose (mirrors the module's pragmatic typing; ruff default rules don't require annotations).
- Citation duplication on risk-loop re-runs of deep_dive matches the existing FRED/transcript convention — called out in the code comment, not "fixed" here.
- Operating/pretax/net margins deliberately stay un-nulled under corruption: ORCL's operating 0.3059 is real (pinned by an existing test) — only EBITDA-derived metrics are correlated casualties.
