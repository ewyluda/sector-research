# Tier 2.6 — Live Thesis Status Board

**Date:** 2026-05-04
**Status:** Spec — ready for implementation plan
**Roadmap context:** Tier 2.6 of `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md`. Depends on Tier 1.1 (kill criteria, pre-mortem, enriched catalysts — shipped) and Tier 1.3 (catalyst calendar — shipped, PR #20 open).

---

## What this is

A new `/status` top-level page that renders a fleet view of every active thesis (10–20 names) as a compact row table with health pills, conviction score, nearest catalyst, kill-criteria summary, and last-refresh recency. The board is the daily home view for monitoring active positions — a B-bucket "fleet view" complement to the A-bucket per-ticker pipeline page.

Health is computed from a mix of manual flags (kill criteria flipped to `triggered`, manual `BROKEN` thesis status) and automatic time-based heuristics (`Imminent` if a catalyst is within 30d, `Stale` if no re-run in 90d). Kill criteria are flipped from the existing report page; the board itself is read-only with an archive escape hatch.

## Decisions taken

| Topic | Decision | Why |
|---|---|---|
| Fleet membership | Latest completed run per `(ticker, theme)`, with explicit per-run archive gesture | Zero-friction onboarding (every completed run shows up automatically) plus a clean way to retire exited names |
| Health model | Manual kill-criteria flags + auto Stale (90d) / Imminent (30d) | Uses signals already in the system; no new LLM evaluator needed for v1 |
| Page placement | New `/status` top-level, sibling to Themes / Filings / Catalysts / Library | Matches established IA from Tier 1.3; doesn't disrupt the existing landing page |
| Thresholds | `Imminent` = catalyst within 30d, `Stale` = no run in 90d | Aligns with existing `<30d` and `>90d` calendar bucket boundaries |
| Kill-criterion toggle UX | Inline on `/pipeline/[runId]` only — board is read-only | Toggling next to the criterion's full context is lower cognitive cost; board stays scannable |
| Aggregation strategy | Read-time aggregation, no caching, no materialized table | YAGNI for ≤100 active runs; nothing can drift because everything is derived |
| Layout | Compact row table (Bloomberg-watchlist style) | Best fit for 10–20 rows of homogenous data; sortable; matches PM mental model |
| Refresh | Frontend polls every 60s while tab visible; backend computes live every request | Matches existing live-page conventions; no scheduler complexity |
| Testing | Manual smoke (backend) + lint/build/Playwright walkthrough (frontend) | No test framework configured per CLAUDE.md |

## Data model

Two new artifacts plus one column.

### New table — `kill_criterion_states`

One row per kill-criterion-per-run that has ever been flipped from default. Default state (`armed`) is implicit absence; only deviations are persisted.

```python
class KillCriterionState(Base):
    __tablename__ = "kill_criterion_states"

    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(
        UUID, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(nullable=False)   # index into ThesisOutput.kill_criteria[]
    status: Mapped[str] = mapped_column(String(16), nullable=False)   # "armed" | "triggered"
    flipped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_kill_criterion_state_run_ordinal"),
    )
```

**Why ordinal-keyed:** Kill criteria emitted by Sonnet have no stable ID — ordinal in `ThesisOutput.kill_criteria` is the only handle. Stable for the lifetime of a run; re-runs produce a new run with new state, mirroring the `Catalyst` per-run scoping convention.

### New column — `research_runs.archived_at`

```python
archived_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True, index=True
)
```

`null` = on the board, non-null = archived. Archive does not delete the run — it just hides it from the default board view. Index supports the default `WHERE archived_at IS NULL` filter.

### Alembic migration

One revision adds the `kill_criterion_states` table (with FK + unique index) and the `archived_at` column with index. Both have correct downgrades (drop table, drop column).

## Backend services & API

### `services/status_board.py`

Pure aggregation. No caching.

```python
@dataclass
class KillCriteriaSummary:
    total: int
    triggered: int

@dataclass
class NextCatalyst:
    description: str
    type: str | None
    expected_date: date | None
    expected_window_end: date | None
    days_until: int | None    # negative if window started but not ended

@dataclass
class StatusBoardEntry:
    ticker: str
    theme_id: str
    theme_name: str
    run_id: str
    thesis_status: str         # STRONG_BUY | BUY | WATCHLIST | PASS | BROKEN
    conviction_score: int | None
    completed_at: datetime
    days_since_update: int

    health: str                # "healthy" | "imminent" | "stale" | "triggered" | "broken"
    health_reasons: list[str]  # e.g. ["Catalyst in 12d", "1 of 3 kill criteria triggered"]

    next_catalyst: NextCatalyst | None
    kill_criteria_summary: KillCriteriaSummary

@dataclass
class StatusBoardResponse:
    entries: list[StatusBoardEntry]
    total: int
    generated_at: datetime
```

**Aggregation query.** For each `(ticker, theme_id)` with at least one `completed`/`watchlist` run that is not archived:

1. Pick the most recent such run by `updated_at`.
2. Pull `ThesisOutput` from `state.phases.thesis_construction` to derive `thesis_status`, `conviction_score`, and `kill_criteria` array length (`total`).
3. Left-join `kill_criterion_states` on `(run_id, ordinal)` for `triggered` count.
4. Left-join `catalysts` for the next catalyst (see tie-break below).
5. Compute `health` and `health_reasons`.

**Catalyst tie-break — `nearest_catalyst(catalysts) -> Catalyst | None`:**

1. Catalysts with `expected_date >= today`, ascending by `expected_date`. First wins.
2. Else: catalysts whose `expected_window_end >= today`, ascending by `expected_window_end`.
3. Else: first catalyst by `ordinal` (the unbound case — row still has *something* to show).

The existing `_bucket` logic in `services/catalysts.py` already encodes proximity; refactor a `nearest_catalyst()` helper out of it rather than duplicating.

**Health resolution — first match wins for the `health` value, but `health_reasons` accumulates every condition that fires:**

1. `broken` — `thesis_status == BROKEN`
2. `triggered` — any kill criterion in `kill_criterion_states` for this run has `status="triggered"`
3. `stale` — `(now - completed_at).days > 90`
4. `imminent` — `next_catalyst.days_until is not None and next_catalyst.days_until <= 30 and (expected_window_end is None or expected_window_end >= today)`
5. `healthy` — none of the above

This order matches the sort severity ranking below — a broken thesis is always more severe than one with a single triggered kill criterion.

**Sort order on the response:** by health severity descending (`broken` > `triggered` > `stale` > `imminent` > `healthy`), then `next_catalyst.days_until` ascending, then `completed_at` descending.

### Endpoints — `api/status.py`

| Method + path | Purpose | Notes |
|---|---|---|
| `GET /api/status/board?theme_id=&include_archived=false` | The fleet view | Returns `StatusBoardResponse`. Default excludes archived. |
| `POST /api/runs/{run_id}/archive` | Archive a run | Sets `archived_at = now()`. 204. |
| `POST /api/runs/{run_id}/unarchive` | Restore | Sets `archived_at = null`. 204. |
| `GET /api/runs/{run_id}/kill-criteria` | Hydrate report page toggles | Returns `list[KillCriterionStateOut]`. Only rows that exist (i.e., have been flipped at least once); the report page treats absent ordinals as `armed`. |
| `PUT /api/runs/{run_id}/kill-criteria/{ordinal}` | Flip one criterion | Body: `{status: "armed"\|"triggered", note?: string}`. Idempotent upsert on `(run_id, ordinal)`. Returns the persisted `KillCriterionStateOut`. |

`PUT` is intentionally single-criterion, not batch — flipping happens one-at-a-time when news arrives.

**Frontend report payload extension.** `GET /api/runs/{run_id}/report` (in `backend/app/api/pipeline.py::get_report`, the endpoint feeding `/pipeline/[runId]`) gets a `kill_criterion_states: KillCriterionStateOut[]` field appended so the report page can hydrate without a parallel fetch. The standalone `GET /api/runs/{run_id}/kill-criteria` endpoint stays for completeness and is the canonical mutation-friendly read path.

### Error handling

Three real failure modes:

1. **Run has no catalysts** (legacy pre-Tier-1.3 runs) — `next_catalyst = None`, row shows em-dash. Not an error.
2. **Run has no `ThesisOutput` in state** (very old / failed runs) — exclude entirely; `logger.warning("status_board.skip_run", run_id=..., reason="no thesis_output")`.
3. **Orphan kill-criterion state** (state row's `ordinal` exceeds current `kill_criteria` array length) — treat as `armed` for counting; do not 500.

Archive / kill-criterion endpoints: 404 if run doesn't exist; otherwise 200/204.

## Frontend

### Page — `frontend/app/status/page.tsx`

Compact row table layout (decision: card grid rejected for vertical-space reasons; expand-to-card rejected as YAGNI).

**Header:** "Status Board" + subtitle "Active theses with health, catalyst proximity, and kill-criteria flags."

**Filter bar (top, sticky):**
- Theme select (reuses pattern from `library/page.tsx`)
- Health filter chips: `All`, `Broken`, `Triggered`, `Stale`, `Imminent`, `Healthy` (each with count badge)
- "Include archived" toggle on the right
- "+ New Run" button on the far right (matches Library)

**Table columns:**
1. **Ticker** — mono badge, click to navigate to `/pipeline/[runId]`
2. **Health** — pill (colors: healthy=emerald, imminent=blue, stale=slate, triggered=amber, broken=red)
3. **Conviction** — large mono number (existing `--color-accent` pattern)
4. **Next catalyst** — description (truncated) + days-until in accent color (`12d`, `47d`, or `undated` in muted slate)
5. **Theme** — small muted text
6. **Refreshed** — relative ("6d ago"), goes slate at >90d
7. **⋯ overflow menu** — `Archive`, `Open report`

**Sort:** the backend sort order is the default; columns are not click-sortable in v1 (deferred — easy to add later).

**Row click:** navigate to `/pipeline/[runId]` (same destination as the ticker badge for consistency).

**Archived rows:** rendered with 50% opacity + slate text + `Unarchive` action in the overflow menu.

**Polling:** 60s `setInterval` while `document.visibilityState === "visible"`. `useEffect` cleanup on unmount.

**Empty/loading:** 4 skeleton rows on first load; "No active theses yet — start a new run" empty state with CTA to `/pipeline/new`.

### Nav — `components/Nav.tsx`

One new entry: `Status`, between `Filings` and `Catalysts` (or wherever feels right when looking at the live nav). Order isn't load-bearing.

### Report page — `frontend/app/pipeline/[runId]/page.tsx`

Locate the existing kill-criteria render (in `RiskCard` or wherever the Tier 1.1 ship landed). Add per-criterion:

- Pill: `Armed` (slate) / `Triggered` (amber dot)
- Click → opens an inline editor with status select + optional `note` textarea + `Save` button
- `Save` → `PUT /api/runs/{run_id}/kill-criteria/{ordinal}` → on 200, update local state and close the editor
- Saving state: button shows `Saving...` and is disabled
- Save error: small inline error with retry; toggle does not optimistically update

`KillCriterionStateOut[]` hydrates from the extended report payload. Lookup by `ordinal`; absence → `armed`.

### TypeScript types — `frontend/lib/api.ts`

New types mirroring backend shapes:

```ts
export type Health = "healthy" | "imminent" | "stale" | "triggered" | "broken";

export interface NextCatalyst { /* mirrors backend */ }
export interface KillCriteriaSummary { total: number; triggered: number }
export interface StatusBoardEntry { /* full mirror */ }
export interface StatusBoardResponse {
  entries: StatusBoardEntry[];
  total: number;
  generated_at: string;
}

export interface KillCriterionStateOut {
  ordinal: number;
  status: "armed" | "triggered";
  flipped_at: string;
  note: string | null;
}

export const status = {
  board: (opts?: { theme_id?: string; include_archived?: boolean }) => /* GET */,
  archive: (run_id: string) => /* POST */,
  unarchive: (run_id: string) => /* POST */,
};

export const killCriteria = {
  list: (run_id: string) => /* GET */,
  set: (run_id: string, ordinal: number, body: { status: ...; note?: string }) => /* PUT */,
};
```

## Refresh & polling

- **Backend:** every `GET /api/status/board` is a fresh aggregation. No cache, no scheduler.
- **Frontend:** `setInterval(fetchBoard, 60_000)` while tab visible; pauses when `visibilitychange` fires `hidden`. First fetch is on mount.
- **Mutations:** `archive` / `unarchive` / kill-criterion `PUT` trigger an immediate board refetch on the status page.

## Testing

- **Backend:** smoke via curl. Walkthrough:
  1. Run two pipelines to completion (NVDA, MSFT).
  2. `curl GET /api/status/board` — verify both rows present, healthy.
  3. `curl PUT /api/runs/{run_id}/kill-criteria/0 -d '{"status":"triggered"}'` on NVDA.
  4. Re-fetch board — NVDA health goes `triggered`, summary `1 triggered`.
  5. `curl POST /api/runs/{run_id}/archive` on MSFT — drops from default view; reappears with `?include_archived=true`.
  6. Verify a run dated >90d ago shows as `Stale` (manual `UPDATE research_runs SET updated_at = now() - interval '100 days' WHERE id = ...`).
- **Frontend:** `npm run lint` clean; `npm run build` clean. Manual Playwright walkthrough covering load, filter, archive, and kill-criterion flip → board update.

## Non-goals (explicit)

- No badge transition history / audit trail.
- No notifications (email, Slack, in-app push) on health changes.
- No auto-evaluation of kill criteria via LLM (deferred — natural fit for a later tier once the read-through engine and earnings cycle navigator land).
- No multi-flip / batch-edit UI for kill criteria.
- No theme-grouped roll-ups on the board (e.g., "AI Infra: 4 healthy, 1 triggered").
- No CSV/PDF export.
- No click-sort columns on the table (deferred — backend sort suffices for v1).

## Definition of done

- New `/status` page is live, paged into the nav, and renders a row per active thesis with the columns described above.
- Health badges compute correctly across all five states; `health_reasons` exposes every contributing condition.
- Kill-criterion toggle on the report page persists to `kill_criterion_states` and propagates to the board badge within one polling tick.
- Archive / unarchive round-trips work; archived runs are hidden by default and visible via the include-archived toggle.
- Alembic migration applies cleanly forward and backward on a fresh dev DB.
- Backend smoke walkthrough passes; frontend lint + build clean.

## Open questions for implementation

None blocking. Implementation can begin immediately.
