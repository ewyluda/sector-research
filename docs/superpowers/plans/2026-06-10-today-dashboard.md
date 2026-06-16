# Today Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/` a Today dashboard (summary banner → 4-day calendar lanes → needs-attention list) and move the Themes grid to `/themes`. Frontend-only; composes three existing endpoints.

**Architecture:** Client page at `app/page.tsx` polls `/api/status/board`, `/api/catalysts/calendar`, `/api/questions/by-ticker` in parallel every 60s (visibility-gated). Bucketing/sorting lives in a pure, unit-tested `lib/todayDerive.ts`. Presentational components in `components/today/`. The existing `WorkspaceButton` is extracted from `app/status/page.tsx` for reuse.

**Tech Stack:** Next.js 16 App Router, React 19, Tailwind v4 (CSS-variable tokens), `node --test` for `.mts` unit tests.

**Spec:** `docs/superpowers/specs/2026-06-10-today-dashboard-design.md` (read it first).

**Conventions that bind every task:**
- Run all frontend commands from `frontend/`.
- Dark-theme CSS variable tokens (`var(--surface)` etc.) — no hardcoded slate classes in new code (existing tailwind color utilities like `border-red-500/40` for severity tints are fine; that's how `app/status/page.tsx` does pills).
- Date math via `components/catalysts/calendarDates.ts` helpers — never `Date.toISOString()`.
- Next.js 16 caveat: `frontend/AGENTS.md` says check `node_modules/next/dist/docs/` before assuming App Router behavior. The tasks below only use patterns already present in this codebase (client components, `Link`, plain pages), so no new API surface should be needed.

---

### Task 1: Move the Themes grid to `/themes` and update Nav + inbound links

`/` keeps serving the old grid until Task 7 swaps it — build stays green at every commit.

**Files:**
- Create: `frontend/app/themes/page.tsx`
- Modify: `frontend/components/Nav.tsx:8-19`
- Modify: `frontend/app/theme/[id]/ThemeDetailClient.tsx:465`
- Modify: `frontend/app/theme/new/page.tsx:94,251`

- [ ] **Step 1: Create `frontend/app/themes/page.tsx`**

Copy the entire current contents of `frontend/app/page.tsx` (the `ThemeDashboard` server component, 166 lines) into `frontend/app/themes/page.tsx` unchanged, except replace the header comment block (lines 1-6) with:

```tsx
/**
 * Themes (/themes)
 * Grid of curated themes. Each card shows seed tickers and last refreshed
 * timestamp. Data fetched server-side. (Moved from / when the Today
 * dashboard took over the home page.)
 */
```

Keep everything else identical: `export const dynamic = "force-dynamic";`, `ThemeCard`, `DeleteThemeButton` wiring, error/empty states, parent/sub-theme sections.

- [ ] **Step 2: Update the Nav links array**

In `frontend/components/Nav.tsx`, replace the first entry of `links` and insert Themes second:

```tsx
const links = [
  { href: "/",              label: "Today"    },
  { href: "/themes",        label: "Themes"   },
  { href: "/filings",       label: "Filings"  },
  { href: "/catalysts",     label: "Catalysts" },
  { href: "/status",        label: "Status"   },
  { href: "/prospectus",    label: "Prospectus" },
  { href: "/workspace",     label: "Workspace" },
  { href: "/questions",     label: "Questions" },
  { href: "/library",       label: "Library"  },
  { href: "/performance",   label: "Performance" },
  { href: "/pipeline/new",  label: "+ New Run" },
];
```

No change to the active-state logic: `"/theme/abc".startsWith("/themes")` is false, so the Themes pill won't false-activate on theme detail pages, and `Today` only activates on exact `/`.

- [ ] **Step 3: Retarget the three links that assume `/` is the themes grid**

All three are back/cancel links from theme pages. Change `href="/"` → `href="/themes"` at:
- `frontend/app/theme/[id]/ThemeDetailClient.tsx:465`
- `frontend/app/theme/new/page.tsx:94`
- `frontend/app/theme/new/page.tsx:251`

Leave `components/Nav.tsx:41` (the wordmark) pointing at `/` — going "home" now means Today, which is correct.

- [ ] **Step 4: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: both clean. `/themes` and `/` both render the grid for now (intentional, temporary).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/themes/page.tsx frontend/components/Nav.tsx "frontend/app/theme/[id]/ThemeDetailClient.tsx" frontend/app/theme/new/page.tsx
git commit -m "feat(today): move themes grid to /themes, add Today nav entry"
```

---

### Task 2: `lib/todayDerive.ts` — pure derivation functions (TDD)

**Files:**
- Create: `frontend/lib/todayDerive.ts`
- Test: `frontend/lib/todayDerive.test.mts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/lib/todayDerive.test.mts`. Mirrors `lib/cellPath.test.mts` style (node:test + node:assert, imports the `.ts` file directly — Node 25 strips types natively).

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { deriveAttention, deriveSummary } from "./todayDerive.ts";
import type { QuestionTickerRollup, StatusBoardEntry } from "./api.ts";

function entry(over: Partial<StatusBoardEntry>): StatusBoardEntry {
  return {
    ticker: "TEST",
    theme_id: "th-1",
    theme_name: "Test Theme",
    run_id: "run-1",
    thesis_status: "BUY",
    conviction_score: 70,
    completed_at: "2026-05-01T00:00:00Z",
    days_since_update: 10,
    health: "healthy",
    health_reasons: [],
    next_catalyst: null,
    kill_criteria_summary: { total: 0, triggered: 0 },
    ...over,
  };
}

function rollup(over: Partial<QuestionTickerRollup>): QuestionTickerRollup {
  return { ticker: "TEST", p1_count: 0, p2_count: 0, p3_count: 0, open_count: 0, ...over };
}

test("buckets sort broken → triggered → stale → questions", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "STALE1", health: "stale", days_since_update: 95 }),
      entry({ ticker: "TRIG", health: "triggered", kill_criteria_summary: { total: 3, triggered: 1 } }),
      entry({ ticker: "BROKE", health: "broken", health_reasons: ["kill criterion triggered"] }),
      entry({ ticker: "FINE", health: "healthy" }),
      entry({ ticker: "SOON", health: "imminent" }),
    ],
    [rollup({ ticker: "QQQ", p1_count: 2, open_count: 4 })],
  );
  assert.deepEqual(
    rows.map((r) => r.ticker),
    ["BROKE", "TRIG", "STALE1", "QQQ"],
  );
});

test("within a health bucket, oldest update first; questions by p1 desc", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "S-NEW", health: "stale", days_since_update: 91 }),
      entry({ ticker: "S-OLD", health: "stale", days_since_update: 200 }),
    ],
    [
      rollup({ ticker: "Q-LOW", p1_count: 1, open_count: 1 }),
      rollup({ ticker: "Q-HIGH", p1_count: 3, open_count: 5 }),
    ],
  );
  assert.deepEqual(
    rows.map((r) => r.ticker),
    ["S-OLD", "S-NEW", "Q-HIGH", "Q-LOW"],
  );
});

test("healthy/imminent entries and zero-P1 rollups produce no rows", () => {
  assert.deepEqual(
    deriveAttention(
      [entry({ health: "healthy" }), entry({ health: "imminent" })],
      [rollup({ p1_count: 0, p2_count: 4, open_count: 4 })],
    ),
    [],
  );
});

test("a ticker can appear as both a health row and a questions row", () => {
  const rows = deriveAttention(
    [entry({ ticker: "BOTH", health: "triggered" })],
    [rollup({ ticker: "BOTH", p1_count: 1, open_count: 2 })],
  );
  assert.equal(rows.length, 2);
  assert.equal(rows[0].kind, "health");
  assert.equal(rows[1].kind, "questions");
});

test("health row fields map through", () => {
  const [row] = deriveAttention(
    [entry({
      ticker: "NVDA", theme_name: "Semis", run_id: "run-9", health: "triggered",
      health_reasons: ["1 kill criterion triggered"],
      kill_criteria_summary: { total: 5, triggered: 2 }, days_since_update: 12,
    })],
    [],
  );
  assert.equal(row.kind, "health");
  if (row.kind === "health") {
    assert.equal(row.severity, "red");
    assert.equal(row.runId, "run-9");
    assert.equal(row.themeName, "Semis");
    assert.equal(row.triggeredCriteria, 2);
    assert.equal(row.totalCriteria, 5);
    assert.equal(row.daysSinceUpdate, 12);
    assert.deepEqual(row.reasons, ["1 kill criterion triggered"]);
  }
});

test("stale rows are amber, broken/triggered red", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "B", health: "broken" }),
      entry({ ticker: "S", health: "stale" }),
    ],
    [],
  );
  assert.deepEqual(rows.map((r) => r.severity), ["red", "amber"]);
});

test("deriveSummary counts buckets; all-clear is all zeros", () => {
  assert.deepEqual(
    deriveSummary(
      [
        entry({ health: "broken" }),
        entry({ health: "triggered" }),
        entry({ health: "stale" }),
        entry({ health: "healthy" }),
      ],
      [rollup({ ticker: "A", p1_count: 2 }), rollup({ ticker: "B", p1_count: 0, open_count: 1 })],
    ),
    { alerts: 2, stale: 1, p1Tickers: 1 },
  );
  assert.deepEqual(deriveSummary([], []), { alerts: 0, stale: 0, p1Tickers: 0 });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd frontend && node --test lib/todayDerive.test.mts
```
Expected: FAIL — cannot find module `./todayDerive.ts`.

- [ ] **Step 3: Implement `frontend/lib/todayDerive.ts`**

```ts
/**
 * Pure derivation for the Today dashboard: buckets status-board entries and
 * the open-question rollup into attention rows + banner summary counts.
 * Kept free of React/fetch so it's unit-testable via node --test.
 */

import type { Health, QuestionTickerRollup, StatusBoardEntry } from "./api";

export interface HealthAttentionRow {
  kind: "health";
  severity: "red" | "amber";
  ticker: string;
  themeName: string;
  runId: string;
  health: Health;
  reasons: string[];
  triggeredCriteria: number;
  totalCriteria: number;
  daysSinceUpdate: number;
}

export interface QuestionsAttentionRow {
  kind: "questions";
  severity: "blue";
  ticker: string;
  p1Count: number;
  openCount: number;
}

export type AttentionRow = HealthAttentionRow | QuestionsAttentionRow;

export interface TodaySummary {
  alerts: number;     // broken + triggered theses
  stale: number;      // stale theses
  p1Tickers: number;  // tickers with ≥1 open P1 question
}

const HEALTH_BUCKET: Partial<Record<Health, number>> = {
  broken: 0,
  triggered: 1,
  stale: 2,
};

export function deriveAttention(
  entries: StatusBoardEntry[],
  rollup: QuestionTickerRollup[],
): AttentionRow[] {
  const healthRows = entries
    .filter((e) => e.health in HEALTH_BUCKET)
    .sort((a, b) => {
      const byBucket = HEALTH_BUCKET[a.health]! - HEALTH_BUCKET[b.health]!;
      return byBucket !== 0 ? byBucket : b.days_since_update - a.days_since_update;
    })
    .map(
      (e): HealthAttentionRow => ({
        kind: "health",
        severity: e.health === "stale" ? "amber" : "red",
        ticker: e.ticker,
        themeName: e.theme_name,
        runId: e.run_id,
        health: e.health,
        reasons: e.health_reasons,
        triggeredCriteria: e.kill_criteria_summary.triggered,
        totalCriteria: e.kill_criteria_summary.total,
        daysSinceUpdate: e.days_since_update,
      }),
    );

  const questionRows = rollup
    .filter((r) => r.p1_count > 0)
    .sort((a, b) => b.p1_count - a.p1_count)
    .map(
      (r): QuestionsAttentionRow => ({
        kind: "questions",
        severity: "blue",
        ticker: r.ticker,
        p1Count: r.p1_count,
        openCount: r.open_count,
      }),
    );

  return [...healthRows, ...questionRows];
}

export function deriveSummary(
  entries: StatusBoardEntry[],
  rollup: QuestionTickerRollup[],
): TodaySummary {
  return {
    alerts: entries.filter((e) => e.health === "broken" || e.health === "triggered").length,
    stale: entries.filter((e) => e.health === "stale").length,
    p1Tickers: rollup.filter((r) => r.p1_count > 0).length,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd frontend && node --test lib/todayDerive.test.mts
```
Expected: all 7 tests pass. Also confirm the existing suite still passes: `node --test lib/cellPath.test.mts`.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/todayDerive.ts frontend/lib/todayDerive.test.mts
git commit -m "feat(today): pure attention/summary derivation with unit tests"
```

---

### Task 3: Extract `WorkspaceButton` out of the status page

Verbatim move — no behavior change. AttentionList (Task 5) reuses it.

**Files:**
- Create: `frontend/components/status/WorkspaceButton.tsx`
- Modify: `frontend/app/status/page.tsx` (delete local `WorkspaceButton` at lines 144-173; add import)

- [ ] **Step 1: Create `frontend/components/status/WorkspaceButton.tsx`**

The body of the function is copied verbatim from `app/status/page.tsx:144-173`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";

export function WorkspaceButton({ ticker, researchRunId }: { ticker: string; researchRunId: string }) {
  const router = useRouter();
  const { status: preflight, reasons } = useWorkspacePreflight(ticker, researchRunId);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const tooltip = reasons.length > 0 ? reasons.join(" • ") : "Run workspace refresh";
  return (
    <button
      type="button"
      disabled={!canKickOff}
      title={tooltip}
      onClick={async (ev) => {
        ev.stopPropagation();
        if (inFlightRunId) {
          router.push(`/workspace/${inFlightRunId}`);
          return;
        }
        try {
          const { run_id } = await workspaceApi.kickOff(ticker, researchRunId);
          router.push(`/workspace/${run_id}`);
        } catch (err) {
          alert(`Workspace kick-off failed: ${err instanceof Error ? err.message : err}`);
        }
      }}
      className="rounded bg-slate-700/40 px-2 py-0.5 text-[11px] text-slate-300 ring-1 ring-slate-600 hover:bg-slate-700/60 hover:ring-slate-500 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-slate-700/40 disabled:hover:ring-slate-600"
    >
      ↻ Workspace
    </button>
  );
}
```

- [ ] **Step 2: Update `app/status/page.tsx`**

Delete the local `function WorkspaceButton(...) {...}` definition (lines 144-173) and add to the imports:

```tsx
import { WorkspaceButton } from "@/components/status/WorkspaceButton";
```

If `useRouter` / `workspaceApi` / `useWorkspacePreflight` are now unused in `app/status/page.tsx`, remove those imports too — but check first: `useRouter` is also used by the page itself for row navigation, so likely only `useWorkspacePreflight` (and possibly `workspaceApi`) become unused. Let `npm run lint` be the judge; remove exactly what it flags.

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: clean. The `/status` page renders identically (kick-off button still preflight-gated).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/status/WorkspaceButton.tsx frontend/app/status/page.tsx
git commit -m "refactor(status): extract WorkspaceButton for reuse on Today dashboard"
```

---

### Task 4: `SummaryBanner` and `TodayLanes` components

Presentational only — verified by lint/build here, exercised live in Task 7.

**Files:**
- Create: `frontend/components/today/SummaryBanner.tsx`
- Create: `frontend/components/today/TodayLanes.tsx`

- [ ] **Step 1: Create `frontend/components/today/SummaryBanner.tsx`**

```tsx
import type { TodaySummary } from "@/lib/todayDerive";

const TINT = {
  red: "border-red-500/40 bg-red-500/10 text-red-300",
  amber: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  blue: "border-blue-500/40 bg-blue-500/10 text-blue-300",
} as const;

/** One-line severity summary. Renders nothing when all clear. */
export function SummaryBanner({ summary }: { summary: TodaySummary }) {
  const { alerts, stale, p1Tickers } = summary;
  if (alerts === 0 && stale === 0 && p1Tickers === 0) return null;

  const tone = alerts > 0 ? "red" : stale > 0 ? "amber" : "blue";
  const parts: string[] = [];
  if (alerts > 0) parts.push(`${alerts} triggered/broken ${alerts === 1 ? "thesis" : "theses"}`);
  if (stale > 0) parts.push(`${stale} stale ${stale === 1 ? "thesis" : "theses"}`);
  if (p1Tickers > 0) parts.push(`${p1Tickers} ticker${p1Tickers === 1 ? "" : "s"} with open P1 questions`);

  return (
    <div className={`rounded-lg border px-4 py-2.5 text-sm font-medium ${TINT[tone]}`}>
      ⚠ {parts.join(" · ")}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/components/today/TodayLanes.tsx`**

Reuses `EventCard` (econ/earnings/catalyst row rendering, `expand_earnings` deep link, `/pipeline/<runId>` link) and the local-date helpers. Four lanes; today is wider and outlined like the `/catalysts` today-lane.

```tsx
import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";
import { EventCard } from "@/components/catalysts/EventCard";
import { addDays, dayLabel, isoLocal } from "@/components/catalysts/calendarDates";

export function TodayLanes({
  events,
  warnings,
  error,
}: {
  events: CalendarEvent[];
  warnings: string[];
  error: string | null;
}) {
  const today = new Date();
  const days = Array.from({ length: 4 }, (_, i) => addDays(today, i));
  const byDate = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const list = byDate.get(ev.date) ?? [];
    list.push(ev);
    byDate.set(ev.date, list);
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wide">
          Today + next 3 days
        </h2>
        <Link href="/catalysts" className="text-xs text-[var(--primary)] hover:underline">
          Full calendar →
        </Link>
      </div>

      {error ? (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      ) : (
        <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-1.5">
          {days.map((d, i) => {
            const iso = isoLocal(d);
            const dayEvents = byDate.get(iso) ?? [];
            return (
              <div
                key={iso}
                className={`rounded-md bg-[rgba(127,127,127,0.07)] p-1.5 min-h-[120px] ${
                  i === 0 ? "outline outline-1 outline-blue-400/40" : ""
                }`}
              >
                <div className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
                  {i === 0 ? `Today · ${dayLabel(d)}` : dayLabel(d)}
                </div>
                {dayEvents.length === 0 ? (
                  <div className="text-[11px] text-[var(--text-faint)]">—</div>
                ) : (
                  dayEvents.map((ev, j) => (
                    <EventCard key={`${ev.kind}-${ev.ticker ?? "us"}-${j}`} event={ev} />
                  ))
                )}
              </div>
            );
          })}
        </div>
      )}

      {warnings.length > 0 && (
        <p className="mt-1.5 text-[11px] text-[var(--text-faint)]">{warnings.join(" · ")}</p>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: clean (components compile even though nothing imports them yet — Next builds the module graph from pages, so this mostly checks lint/types; full exercise comes in Task 7).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/today/SummaryBanner.tsx frontend/components/today/TodayLanes.tsx
git commit -m "feat(today): SummaryBanner and TodayLanes components"
```

---

### Task 5: `AttentionList` component

**Files:**
- Create: `frontend/components/today/AttentionList.tsx`

- [ ] **Step 1: Create `frontend/components/today/AttentionList.tsx`**

```tsx
"use client";

import Link from "next/link";
import type { AttentionRow } from "@/lib/todayDerive";
import { WorkspaceButton } from "@/components/status/WorkspaceButton";

const ROW_BORDER: Record<AttentionRow["severity"], string> = {
  red: "border-l-red-500",
  amber: "border-l-amber-500",
  blue: "border-l-blue-500",
};

const HEALTH_LABEL: Record<string, string> = {
  broken: "Broken",
  triggered: "Triggered",
  stale: "Stale",
};

export function AttentionList({ rows, error }: { rows: AttentionRow[]; error: string | null }) {
  return (
    <section>
      <h2 className="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wide mb-2">
        Needs attention
      </h2>

      {error ? (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-muted)]">
          All clear ✓{" "}
          <Link href="/status" className="text-[var(--primary)] hover:underline">
            View status board →
          </Link>
        </div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((row) =>
            row.kind === "health" ? (
              <div
                key={`health-${row.ticker}-${row.runId}`}
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2`}
              >
                <Link
                  href={`/pipeline/${row.runId}`}
                  className="font-mono font-bold text-sm text-[var(--text)] tracking-wide hover:underline shrink-0"
                >
                  {row.ticker}
                </Link>
                <span className="text-[11px] text-[var(--text-muted)] truncate shrink-0 max-w-[140px]">
                  {row.themeName}
                </span>
                <span className="text-xs text-[var(--text-muted)] truncate flex-1">
                  <span className="font-semibold text-[var(--text)]">{HEALTH_LABEL[row.health]}</span>
                  {row.health === "stale" && ` · ${row.daysSinceUpdate}d since update`}
                  {row.triggeredCriteria > 0 &&
                    ` · ${row.triggeredCriteria}/${row.totalCriteria} kill criteria triggered`}
                  {row.reasons.length > 0 && ` — ${row.reasons.join("; ")}`}
                </span>
                <span className="shrink-0" data-print-hide="true">
                  <WorkspaceButton ticker={row.ticker} researchRunId={row.runId} />
                </span>
              </div>
            ) : (
              <Link
                key={`questions-${row.ticker}`}
                href="/questions"
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2 hover:bg-[var(--surface-alt)] transition-colors`}
              >
                <span className="font-mono font-bold text-sm text-[var(--text)] tracking-wide shrink-0">
                  {row.ticker}
                </span>
                <span className="text-xs text-[var(--text-muted)] flex-1">
                  {row.p1Count} open P1 question{row.p1Count === 1 ? "" : "s"}
                  {row.openCount > row.p1Count && ` (${row.openCount} open total)`}
                </span>
                <span className="text-[11px] text-[var(--primary)] shrink-0">View →</span>
              </Link>
            ),
          )}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Verify**

```bash
cd frontend && npm run lint && npm run build
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/today/AttentionList.tsx
git commit -m "feat(today): AttentionList with workspace kick-off on health rows"
```

---

### Task 6: Today page at `/` (replaces the themes grid)

**Files:**
- Modify: `frontend/app/page.tsx` (full replacement — the grid now lives at `/themes` from Task 1)

- [ ] **Step 1: Replace `frontend/app/page.tsx` entirely**

```tsx
"use client";

/**
 * Today dashboard (/) — morning briefing.
 * SummaryBanner → 4-day calendar lanes → needs-attention list.
 * Composes /api/status/board + /api/catalysts/calendar + /api/questions/by-ticker
 * client-side; polls every 60s while the tab is visible. Each section degrades
 * independently — a failed source shows an inline note, never blanks the page.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  getCalendarEvents,
  questions as questionsApi,
  status as statusApi,
  type CalendarEvent,
  type QuestionTickerRollup,
  type StatusBoardEntry,
} from "@/lib/api";
import { addDays, isoLocal } from "@/components/catalysts/calendarDates";
import { deriveAttention, deriveSummary } from "@/lib/todayDerive";
import { SummaryBanner } from "@/components/today/SummaryBanner";
import { TodayLanes } from "@/components/today/TodayLanes";
import { AttentionList } from "@/components/today/AttentionList";

const HEADER_FMT = new Intl.DateTimeFormat("en-US", {
  weekday: "long",
  month: "long",
  day: "numeric",
});

export default function TodayDashboard() {
  const [board, setBoard] = useState<StatusBoardEntry[] | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [calendarError, setCalendarError] = useState<string | null>(null);
  const [rollup, setRollup] = useState<QuestionTickerRollup[] | null>(null);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  // Tracks which sources have loaded at least once, so polling failures
  // after a successful first load keep last-good data without an error note.
  const loadedRef = useRef({ board: false, calendar: false, questions: false });

  useEffect(() => {
    let cancelled = false;

    async function fetchAll() {
      // Recompute the window each poll so an overnight tab rolls forward.
      const start = isoLocal(new Date());
      const end = isoLocal(addDays(new Date(), 3));

      const [boardRes, calRes, qRes] = await Promise.allSettled([
        statusApi.board(),
        getCalendarEvents(start, end),
        questionsApi.byTicker(),
      ]);
      if (cancelled) return;

      if (boardRes.status === "fulfilled") {
        loadedRef.current.board = true;
        setBoard(boardRes.value.entries);
        setBoardError(null);
      } else if (!loadedRef.current.board) {
        setBoardError("Could not load the status board.");
      } // else: keep last-good data, no error note

      if (calRes.status === "fulfilled") {
        loadedRef.current.calendar = true;
        setEvents(calRes.value.events);
        setWarnings(calRes.value.warnings);
        setCalendarError(null);
      } else if (!loadedRef.current.calendar) {
        setCalendarError("Could not load the calendar.");
      }

      if (qRes.status === "fulfilled") {
        loadedRef.current.questions = true;
        setRollup(qRes.value.tickers);
        setQuestionsError(null);
      } else if (!loadedRef.current.questions) {
        setQuestionsError("Could not load open questions.");
      }
    }

    fetchAll();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchAll();
    };
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") fetchAll();
    }, 60_000);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const summary = useMemo(() => deriveSummary(board ?? [], rollup ?? []), [board, rollup]);
  const attentionRows = useMemo(() => deriveAttention(board ?? [], rollup ?? []), [board, rollup]);

  // Attention section: board failure dominates (rows would be misleadingly
  // empty); a questions-only failure still shows health rows with a note.
  const attentionError =
    boardError ?? (questionsError ? `${questionsError} Health rows may be incomplete.` : null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text)]">Today</h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">{HEADER_FMT.format(new Date())}</p>
      </div>

      {!boardError && !questionsError && <SummaryBanner summary={summary} />}

      <TodayLanes events={events ?? []} warnings={warnings} error={calendarError} />

      <AttentionList rows={attentionRows} error={attentionError} />
    </div>
  );
}
```

Note the loading state is intentionally minimal: before the first fetch resolves, sections render their natural empty shells ("—" lanes / no banner). If that looks janky live, a follow-up may add skeletons — do not add them preemptively.

- [ ] **Step 2: Verify build + tests**

```bash
cd frontend && npm run lint && npm run build && node --test lib/todayDerive.test.mts lib/cellPath.test.mts
```
Expected: all clean, 10 tests pass (7 new + 3 cellPath).

- [ ] **Step 3: Manual smoke (requires backend running)**

Backend: `source backend/venv/bin/activate && uvicorn backend.app.main:app --reload` from repo root. Frontend: `cd frontend && npm run dev`. API base must be `http://127.0.0.1:8000` (Docker steals IPv6 localhost:8000 on this machine).

Visit `http://localhost:3000/` and check:
- Header shows "Today" + the current date.
- Banner counts match the `/status` board (triggered/broken + stale) and `/questions` P1 rollup; banner absent if all clear.
- Lanes show the same events `/catalysts` shows for the next 4 days; earnings rows link to `/status?expand_earnings=...` and open the EarningsDrawer; catalyst rows link to `/pipeline/<runId>`.
- Attention rows: ticker links open the run report; ↻ Workspace button preflight-gates and kicks off (routes to `/workspace/<runId>`).
- `/themes` renders the grid; theme detail "back" links land on `/themes`.
- `/status` unaffected (WorkspaceButton extraction).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(today): Today dashboard takes over the home page"
```

---

### Task 7: Docs

**Files:**
- Modify: `CLAUDE.md` (two surgical edits)
- Modify: `TODO.md` ("Done (recent)" entry)

- [ ] **Step 1: Update CLAUDE.md**

1. In the "Seven top-level workspaces" intro list, change the first bullet:

```markdown
- **Today** (`/`) — morning briefing: summary banner, 4-day calendar slice, needs-attention list (status-board health + open P1 questions). Pure frontend composition of the board/calendar/questions endpoints.
- **Themes / Discovery** (`/themes`, `/theme/[id]`) — ranked companies per theme.
```

2. In the "Frontend layout" section, update the `app/` bullet's route list: `/` is now the Today dashboard and the themes grid is `/themes`; add `components/today/` to the components list:

```markdown
- `components/today/` — `SummaryBanner`, `TodayLanes` (reuses catalysts `EventCard`), `AttentionList` (reuses `components/status/WorkspaceButton`, extracted from the status page); derivation logic in `lib/todayDerive.ts` (unit-tested)
```

- [ ] **Step 2: Add TODO.md "Done (recent)" entry**

Prepend under `## Done (recent)`:

```markdown
- **Today dashboard (investor-portal sub-project 3)** — `/` is now a morning briefing (severity banner → today+3d calendar lanes → needs-attention list with workspace kick-off); themes grid moved to `/themes`. Frontend-only composition of board/calendar/questions endpoints, 60s visibility-gated polling, per-section degradation. `WorkspaceButton` extracted to `components/status/`. Spec: `docs/superpowers/specs/2026-06-10-today-dashboard-design.md`.
```

- [ ] **Step 3: Verify + commit**

```bash
cd frontend && npm run lint && npm run build
git add CLAUDE.md TODO.md
git commit -m "docs: Today dashboard — CLAUDE.md workspaces/layout + TODO done log"
```

---

## Final verification (after all tasks)

```bash
cd frontend && npm run lint && npm run build && node --test lib/todayDerive.test.mts lib/cellPath.test.mts
```

Then the Playwright smoke from Task 6 Step 3 end-to-end against the live backend. Backend test suite is untouched by this work (no backend changes) — no need to run it.
