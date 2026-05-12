# Tier 2.5 — Earnings Cycle Navigator

**Date:** 2026-05-05
**Status:** Spec — ready for implementation plan
**Roadmap context:** Tier 2.5 of `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md`. Compounds on Tier 1.3 (catalyst calendar), Tier 2.6 (status board), and Tier 1.4 (read-through engine). Doesn't gate on Tier 3 model — diff-vs-consensus is enough for v1.

---

## What this is

A pre/post-earnings layer over every active status-board thesis. For every ticker with an active thesis on the status board, the engine:

1. **Pre-print:** surfaces consensus expectations and "what to watch" against the thesis pillars when an earnings date is within window.
2. **Post-print:** ingests actuals (EPS / revenue / guidance direction) deterministically the moment FMP populates `epsActual`, then exposes a Haiku "thesis-check" verdict (confirms / threatens / neutral / insufficient) on demand.
3. **Propagates** the deterministic numbers — but not the narrative verdict — through the existing read-through engine so peer theses get richer summary inputs when the print drops.

The surface is a drawer expansion on `/status` rows, mirroring the read-through drawer pattern that just shipped. No new top-level page in v1.

This is a Tier-2 "fleet feature": when 12 theses report in a single week, the user can scan the status board and see green/red/amber print badges, click into the ones that matter, and read the LLM verdict for whether the thesis still holds.

## Decisions taken

| Topic | Decision | Why |
|---|---|---|
| UI surface | Drawer expansion on `/status` rows (Tier 2.6 pattern) | Reuses fresh muscle memory; a dedicated `/earnings` page only earns its keep at 20+ active theses. Cross-thesis "this week's earnings" comes free if `/status` adds an earnings filter chip. |
| Eligibility | Every active status-board thesis | Coverage > coupling. We don't gate on Sonnet flagging earnings as a catalyst. |
| Date source of truth | FMP earnings calendar at read-time | Already TTL-cached. Catalyst rows of `type='earnings'` are a *bonus signal* (their `signposts[]` enrich the pre-earnings brief), not the gate. |
| Pre-earnings synthesis | Deterministic always rendered + lazy LLM brief | Consensus / surprise trend / signposts auto-render. "Generate pre-earnings brief" Haiku button distills thesis pillars + signposts + consensus into 3-5 bullets of "what would confirm vs threaten." |
| Post-print trigger | Hybrid — auto-deterministic, lazy LLM verdict | Daily scheduler stores `earnings_prints` rows when `epsActual` first appears (cheap; no LLM). Narrative verdict is on-demand per `(run_id, print)` pair. Status board badge color flips on the deterministic numbers alone. |
| Verdict scope | Per-`run_id` (not per-ticker-theme) | Verdicts attach to the thesis-version they were computed against. Same pattern as `kill_criterion_states`. Re-running the thesis orphans old verdicts; user re-triggers if they want a fresh narrative. |
| Read-through propagation | Numbers propagate, narrative stays scoped | EPS surprise + revenue surprise + guidance direction enrich peer drawer payloads (and the existing read-through Haiku summary input); originator's narrative verdict does NOT bleed into peer theses. |
| Slack-window fix | Symmetric ±30d in `_try_fmp_earnings_override` | Drop-in fix while in the area; fixes the long-standing one-sided bug. Affects future thesis runs only — no backfill. |
| Persistence | Two new tables | `earnings_prints` (per-ticker, per-fiscal-period) + `thesis_print_verdicts` (per-run, per-print). Clean separation of objective numbers from per-thesis narrative. |
| Backfill | None — turns on at merge | History prior to merge stays in the read-through engine's existing earnings event indexer; we don't retroactively materialize prints. |
| Testing | Manual smoke (backend) + lint/Playwright (frontend) | Same conventions as Tier 1.3 / 2.6 / 1.4. No backend test framework. |

## Out of scope (v1)

- Reverse-DCF "what's priced in" comparison — that's Tier 3.8.
- Management credibility tracker (delivery vs promises across N quarters) — Tier 4.
- Automatic re-run of the thesis after a print — verdict only; user decides whether to re-run.
- Transcript sentiment scoring beyond what Haiku produces inline in the verdict.
- Historical backfill of past prints.
- Dedicated `/earnings` top-level page — earned later if `/status` proves cramped.
- Buy-side / sell-side estimate dispersion (just consensus mean for v1).

## Data model

Two new tables. No changes to existing schemas.

### New table — `earnings_prints`

One row per (ticker, fiscal_period). Per-ticker, shared across themes.

```python
class EarningsPrint(Base):
    __tablename__ = "earnings_prints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(nullable=False)  # 1-4
    earnings_date: Mapped[date] = mapped_column(nullable=False)

    eps_estimated: Mapped[float | None]
    eps_actual: Mapped[float | None]
    revenue_estimated: Mapped[float | None]
    revenue_actual: Mapped[float | None]

    # Computed at write-time, nullable when actual is missing
    eps_surprise_pct: Mapped[float | None]       # (actual - est) / |est|
    revenue_surprise_pct: Mapped[float | None]

    # Best-effort from transcript scrape; null when undetermined
    guidance_direction: Mapped[str | None] = mapped_column(String(20))
    # Enum literal: "raised" | "maintained" | "lowered" | "n/a" | None

    # Pointer to the transcript that informed guidance/verdict; nullable until fetched
    transcript_year: Mapped[int | None]
    transcript_quarter: Mapped[int | None]

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("ticker", "fiscal_year", "fiscal_quarter", name="uq_earnings_prints_period"),
        Index("ix_earnings_prints_ticker_date", "ticker", "earnings_date"),
    )
```

Idempotency: `INSERT ... ON CONFLICT (ticker, fiscal_year, fiscal_quarter) DO UPDATE` — when actuals first appear, the row updates from "estimates only" to "estimates + actuals." Re-runs of the scheduler are safe.

`fiscal_year` / `fiscal_quarter` come from the FMP calendar row's `date` plus the company's fiscal calendar where known; for tickers where FMP doesn't expose fiscal periods reliably (non-calendar-year reporters), fall back to calendar year/quarter from `earnings_date`. The unique constraint is on the inferred values, not on a pristine fiscal mapping.

### New table — `thesis_print_verdicts`

One row per (run_id, earnings_print_id). Per-thesis-run, written lazily when the user clicks "Run thesis-check."

```python
class ThesisPrintVerdict(Base):
    __tablename__ = "thesis_print_verdicts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    earnings_print_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("earnings_prints.id", ondelete="CASCADE"),
        nullable=False,
    )
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    # Enum: "confirms" | "threatens" | "neutral" | "insufficient"

    summary_md: Mapped[str] = mapped_column(nullable=False)
    pillars_addressed: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("run_id", "earnings_print_id", name="uq_thesis_print_verdicts_run_print"),
        Index("ix_thesis_print_verdicts_run_id", "run_id"),
    )
```

`verdict='insufficient'` is a real value, not an absence — Haiku is allowed to say "the print didn't speak to any of the thesis pillars one way or the other." This is different from "no verdict yet exists" (= no row).

Re-running the thesis: the cascade is on `run_id` (CASCADE), so when a run is replaced by a fresh one, old verdicts orphan. This is intentional. The `/status` board picks the latest run per (ticker, theme), so users naturally see "no verdict yet" on a fresh run with prior prints, prompting a re-trigger.

### Single Alembic migration

`alembic revision -m "add earnings_prints and thesis_print_verdicts"` (hand-written; the autogenerate diff is a starting point but UUID server defaults and JSONB defaults need touch-up). Hand-write the `downgrade()` to fully reverse, matching the discipline established in Tier 2.6's migration.

## Backend architecture

Two new services + extensions to two existing services + a new scheduler hook.

### New module — `services/earnings_prints.py`

```python
async def index_earnings_prints(
    ticker: str,
    fmp: FMPClient,
    db: AsyncSession,
) -> list[EarningsPrint]:
    """Pull FMP earnings calendar for a ticker, upsert prints. Returns
    affected rows. Idempotent on (ticker, fiscal_year, fiscal_quarter).

    Computes eps_surprise_pct and revenue_surprise_pct only when actuals
    are present. Does NOT fetch transcripts — guidance_direction stays
    null until a separate enrichment pass (or a verdict request) fills it in.
    """

async def fetch_active_board_tickers(db: AsyncSession) -> list[str]:
    """Distinct tickers from the latest non-archived run per (ticker, theme).
    Reuses the same DISTINCT ON query the status board uses. List driven by
    the board, not the universe."""
```

### New scheduler — `services/earnings_scheduler.py`

A single APScheduler cron job, registered in `app/main.py::lifespan` alongside the existing daily X-signal refresh. Runs once per weekday at 21:00 UTC (5 PM ET, after the market close + post-market press releases). For each active board ticker:

1. Call `index_earnings_prints(ticker, fmp, db)`.
2. For any newly-populated print (transition from `eps_actual IS NULL` → `eps_actual IS NOT NULL`), best-effort fetch the matching transcript via `FMPClient.get_earnings_transcript(ticker, year, quarter)` and parse guidance direction with a small Haiku call (or lightweight regex; design choice deferred to implementation, see "Open implementation choice" below).

Transcript fetch failures are non-fatal: the print row stays with `transcript_year/quarter` null and `guidance_direction` null. Re-running the scheduler retries.

Why daily, not realtime: a personal tool with ~12 active theses; earnings prints land at predictable hours; weekly cron is too sparse for a "today's prints" feel; sub-daily is overkill.

### New module — `services/earnings_verdict.py`

Single async `compute_verdict(run_id, earnings_print_id, db) -> ThesisPrintVerdict` function. Steps:

1. Load `ResearchRun.state` and pull `thesis_summary` + `thesis_pillars` (via the existing `_extract_thesis_summary` helper from `read_through.py`, plus a sibling pillar extractor).
2. Load `EarningsPrint` row (numbers + guidance) and any matched `Catalyst` of `type='earnings'` for this run (pulls `signposts[]` and the prompt-friendly `description`).
3. Optional: pull the transcript excerpt (mgmt commentary section, capped at ~6K chars) when present.
4. Single Haiku call with structured output (Pydantic `VerdictOutput { verdict, summary_md, pillars_addressed[] }`) using `assistant_prefill='{"verdict":'`. System prompt is long enough (>500 chars) to trigger ephemeral cache per `graph/llm.py` convention.
5. Persist via `INSERT ... ON CONFLICT (run_id, earnings_print_id) DO UPDATE` (idempotent — re-clicking "Run thesis-check" overwrites with a fresh call).

Cache hit rate: the system prompt is fully shared across all verdict calls in a run-day, so cache hits should be reliable across the ~12 board theses.

### New module — `services/earnings_brief.py`

Symmetric to `earnings_verdict.py` but pre-print. Single async `compute_brief(run_id, earnings_print_id, db)`. No persistence — pre-print briefs are ephemeral and re-rendered on demand. Re-running burns Haiku tokens but doesn't write a row. (Open question for impl plan: do we want a `thesis_print_briefs` mirror table for caching? Defer to the plan stage; YAGNI for v1 unless cost shows up as a real issue.)

### Extension — `services/read_through.py::compute_peer_events`

Today's earnings events come from `Catalyst` rows. Extend the indexer to also emit (or enrich existing items with) the deterministic numbers from `earnings_prints` when a matched row exists for the peer's `(ticker, earnings_date ± slack)`. Payload grows from `{description, expected_date, type, signposts}` to additionally include `{eps_surprise_pct, revenue_surprise_pct, guidance_direction}` when post-print numbers are known.

Key constraint per Q5-B: the originator's `thesis_print_verdicts.summary_md` is **never** read by `compute_peer_events`. Read-through items see numbers, not narrative.

The existing `summarize_read_through` Haiku prompt grows by one paragraph: "If post-print actuals are present, treat them as the most recent objective signal about the peer's print, and reason about implications for THIS thesis. Do not parrot or restate the peer thesis's verdict — it is not provided to you."

### Extension — `services/catalyst_promotion.py::_try_fmp_earnings_override`

Slack-window symmetry fix. Today:

```python
if parsed.window_start and parsed.window_end:
    lower = max(parsed.window_start, today)
    upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
```

After:

```python
if parsed.window_start and parsed.window_end:
    lower = max(parsed.window_start - timedelta(days=_FMP_EARNINGS_SLACK_DAYS), today)
    upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
```

No data migration. Affects only future thesis runs (the override only fires inside `promote_catalysts`, which is called per-run during `node_thesis_construction`).

## API

New router at `backend/app/api/earnings.py`. **No `from __future__ import annotations`** in this file — same FastAPI 0.115 / Python 3.12 footgun called out in `api/status.py` and `api/read_through.py`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/earnings/board?window_days=14` | Returns one entry per active status-board thesis with an upcoming or recent print. Each entry: `run_id`, `ticker`, `theme_id`, `print` (the `earnings_prints` row or null), `matched_catalyst` (ordinal + signposts from any `type='earnings'` Catalyst), `verdict` (the `thesis_print_verdicts` row or null), `phase` (`pre` / `post` / `none`). |
| `POST` | `/api/runs/{run_id}/earnings/{print_id}/brief` | Compute (or recompute) a pre-earnings brief. Returns `{summary_md, pillars_addressed, generated_at}`. Not persisted. |
| `POST` | `/api/runs/{run_id}/earnings/{print_id}/verdict` | Compute (or recompute) a post-print verdict. Returns the persisted `ThesisPrintVerdict`. Idempotent. |
| `GET` | `/api/earnings/prints/{ticker}` | List recent prints for a ticker (most recent 8). For potential future use; not consumed by v1 UI but cheap to expose. |
| `POST` | `/api/earnings/refresh/{ticker}` | Manually trigger `index_earnings_prints` for one ticker. Useful for "I just saw the print drop on a Twitter feed; pull it now" without waiting for the daily scheduler. |

Errors: 404 on missing run/print, 400 on `ValueError` from the verdict compute (e.g., thesis_summary missing), 502 + `logger.exception` on Haiku/FMP failures. Same error handling pattern as `api/read_through.py`.

`POST /verdict` returns 202 + persisted row when synchronous compute succeeds (typical case is 2-4s). If we ever need to make it non-blocking, the existing `pipeline.py` SSE pattern is the obvious upgrade path; not in v1.

## Frontend

### Status board changes (`/status`)

Per row, a third badge slot to the right of the existing health pill and `⟿ N` read-through badge:

- **Pre-print state** (print upcoming within `window_days`, no actuals): blue `📅 T-{N}d` badge. Clicking expands an inline drawer (sibling to read-through drawer) with consensus EPS/rev, last-4-quarter beat/miss trend, signposts (from matched Catalyst row, verbatim), and a "Generate pre-earnings brief" button.
- **Post-print state** (actuals present, no verdict yet): amber `📊 reported {N}d ago` badge. Drawer shows EPS/rev surprise %, guidance direction (or "—"), and a "Run thesis-check" button.
- **Verdict state** (verdict row exists): green / red / amber based on `verdict`. Drawer shows the LLM `summary_md` plus the deterministic numbers above it.
- **No print state**: no badge; row looks identical to today.

States are mutually exclusive — at most one earnings badge per row at a time. Color rules:

| Verdict | Badge color |
|---|---|
| `confirms` | emerald (matches healthy pill) |
| `threatens` | red (matches broken pill) |
| `neutral` | slate (matches stale pill) |
| `insufficient` | amber (matches triggered pill) |

### Drawer component

New `components/status/EarningsDrawer.tsx`. Same visual idiom as `ReadThroughDrawer.tsx` (sibling not parent — rendered below the row, full-width grid span). Three sub-views by phase:

- `<PreEarningsBlock />` — consensus + trend + signposts + brief button.
- `<PostEarningsBlock />` — surprise numbers + guidance + verdict button.
- `<VerdictBlock />` — verdict pill + `summary_md` (rendered as Markdown via the same util that renders thesis text on `/pipeline/[runId]`).

### `lib/api.ts` additions

Typed client extensions:

```ts
export type VerdictPhase = "pre" | "post" | "none";
export type Verdict = "confirms" | "threatens" | "neutral" | "insufficient";

export interface EarningsPrintRow { /* mirrors EarningsPrint fields */ }
export interface ThesisPrintVerdictRow { /* mirrors ThesisPrintVerdict fields */ }
export interface MatchedEarningsCatalyst { ordinal: number; signposts: string[]; description: string }

export interface EarningsBoardEntry {
  run_id: string;
  ticker: string;
  theme_id: string;
  phase: VerdictPhase;
  print: EarningsPrintRow | null;
  matched_catalyst: MatchedEarningsCatalyst | null;
  verdict: ThesisPrintVerdictRow | null;
}

export const earnings = {
  board: (windowDays?: number): Promise<{ entries: EarningsBoardEntry[] }> => /* ... */,
  brief: (runId: string, printId: string): Promise<{ summary_md: string; pillars_addressed: string[]; generated_at: string }> => /* ... */,
  verdict: (runId: string, printId: string): Promise<ThesisPrintVerdictRow> => /* ... */,
  refresh: (ticker: string): Promise<{ updated: number }> => /* ... */,
};
```

`/status` page polls `earnings.board()` on the same 60s cadence as the status board and read-throughs (and pauses on `document.visibilityState === "hidden"`, same pattern). Three independent polls is acceptable — they're tiny query-layer endpoints. Could be unified later if response time becomes an issue.

### Print view

The `EarningsDrawer` and any badge-only chrome carry `data-print-hide="true"` so they drop out of `@media print` for PDF exports of `/status`. Matches the discipline established in `app/globals.css`.

## Prompts

### `EARNINGS_BRIEF_SYSTEM` (Haiku, >500 chars for cache)

Role: equity analyst preparing a pre-earnings checklist for a specific thesis. Input: thesis_summary + thesis_pillars + signposts + consensus EPS/rev + last-4-quarter trend. Output: 3-5 markdown bullets, each starting with a metric or signpost name, identifying what would confirm vs threaten. Constraint: only reason about the print itself, not broader macro; no recommendations to buy/sell.

### `EARNINGS_VERDICT_SYSTEM` (Haiku, >500 chars for cache)

Role: equity analyst evaluating whether an earnings print confirms or threatens a thesis. Input: thesis_summary + thesis_pillars + signposts + actuals (eps surprise, rev surprise, guidance direction) + optional transcript management commentary (capped 6K chars). Output: structured Pydantic with `verdict: Literal["confirms","threatens","neutral","insufficient"]`, `summary_md` (3-5 sentences), `pillars_addressed: list[str]` (subset of input pillar names that the print actually spoke to). Constraint: lean toward `insufficient` when the print is silent on thesis pillars; do not infer from sentiment alone.

Both prompts use `assistant_prefill='{"verdict":'` (or `'{"summary_md":'` for the brief) per the established structured-output convention in `edgar_relationships.py` and `edgar_competition.py`.

## Smoke test

`backend/scripts/smoke_earnings_navigator.py` — symmetric to `smoke_read_through.py`. Run live against the dev database. Three assertions:

1. **Indexer** — call `index_earnings_prints(ticker)` for a known ticker, assert a row materializes with `eps_estimated` non-null. Use a ticker on the active board to keep paths warm.
2. **Verdict** — given a synthetic `EarningsPrint` row with mock actuals, call `compute_verdict(run_id, print_id)` against an existing completed run. Assert `verdict in {"confirms", "threatens", "neutral", "insufficient"}`, `pillars_addressed` is a non-null list, `summary_md` length > 50 chars.
3. **Read-through enrichment** — verify a peer-event drawer payload for a relationship-connected ticker now includes `eps_surprise_pct` when the originator's print exists. (Cleanup: delete synthetic `earnings_prints` row after the test; don't pollute production data.)

Run order: `python -m backend.scripts.smoke_earnings_navigator <run_id> <peer_ticker>`. Exit 0 on green, exit 1 with the failed assertion's name on red.

## Open implementation choice (deferred to plan stage)

**Guidance-direction extraction:** how do we get `raised` / `maintained` / `lowered` / `n/a` from the transcript?

- *Option A:* Lightweight regex over the management commentary section (works for many tickers' standardized phrasings, e.g., "we are raising our full-year guidance to..."). Cheap; misses companies with non-standard language.
- *Option B:* Tiny Haiku call with structured output (~200 tokens out). Robust; costs ~$0.0003 per print.

Defer to the writing-plans stage — both are low-stakes and trivially swappable. Initial gut: B for v1 (already paying Haiku for the verdict; one more small call for guidance is fine), revisit if cost shows up.

## Definition of done

- New tables exist in dev DB; alembic upgrade/downgrade both work clean.
- Daily scheduler is registered in `app/main.py::lifespan` and emits a single `index_earnings_prints` per active board ticker on each run.
- `GET /api/earnings/board` returns a non-empty array for a board with at least one ticker reporting in the next 14 days, and an empty array when no prints are within window.
- `POST /api/runs/{run_id}/earnings/{print_id}/verdict` returns a persisted row with one of the four allowed verdicts.
- `/status` page renders the third badge slot for at least one row in dev (verified via Playwright walkthrough).
- Read-through drawer for a peer ticker shows EPS surprise % when the originator's print is in the DB (verified via the smoke script).
- Slack-window symmetry change is in place (one-line edit; verified by inspection — no behavior test, since it only fires inside `promote_catalysts` and synthetic test setup is heavier than the change).
- Smoke script passes 3/3 against dev DB.

## File touch list (rough)

New files:

- `backend/app/models/earnings_print.py`
- `backend/app/models/thesis_print_verdict.py`
- `backend/app/services/earnings_prints.py`
- `backend/app/services/earnings_brief.py`
- `backend/app/services/earnings_verdict.py`
- `backend/app/services/earnings_scheduler.py`
- `backend/app/api/earnings.py`
- `backend/migrations/versions/<hash>_earnings_prints_and_verdicts.py`
- `backend/scripts/smoke_earnings_navigator.py`
- `frontend/components/status/EarningsDrawer.tsx`

Modified files:

- `backend/app/models/__init__.py` — register new models.
- `backend/app/main.py` — register router + scheduler job.
- `backend/app/services/catalyst_promotion.py` — symmetric slack window.
- `backend/app/services/read_through.py` — enrich peer-event payload with surprise numbers; update summary prompt with the "do not parrot" line.
- `frontend/lib/api.ts` — earnings client + types.
- `frontend/app/status/page.tsx` — third badge slot, third polling loop, drawer mount.
- `frontend/app/globals.css` — `data-print-hide` if any new sticky chrome.

Approximate diff size: ~1.4-1.8K LoC, comparable to Tier 1.4.
