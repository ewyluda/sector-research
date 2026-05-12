# Tier 3.9 — Workspace 5-Step Loop

**Date:** 2026-05-09
**Status:** Spec drafted; awaiting user review before writing-plans
**Source:** `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md` (Tier 3 item 9), `docs/2026-05-03-model-workspace-plan.md` (superseded)

---

## Context

Tier 3.9 is the last unshipped Tier 3 item. Tier 3.7 (editable model) and Tier 3.8 (reverse DCF) shipped in PR #24 on 2026-05-06. The May 3 model-workspace plan predates both — its Phase 0 (schema) and Phase 3 (reverse DCF) tasks are now done in `ticker_models` / `ticker_model_drafts` and `services/reverse_dcf.py`. This spec supersedes that plan.

The workspace is the **recurring post-earnings refresh ritual** — slide 46's 5-step loop, Steps 9-13 of the exoskeleton in concentrated form. It is *not* a fresh deep-dive; the existing 6-phase pipeline keeps that role. The workspace operates on a ticker that already has a completed `research_run` and an existing `ticker_model`, and produces a delta-summary plus a verdict.

## Strategic decisions

- **Separate, complementary flow.** Workspace is its own surface at `/workspace/[runId]`. It reads `research_runs` + `ticker_models` outputs but does not rerun pipeline phases. Pipeline = first-time deep dive (slow, expensive, infrequent). Workspace = recurring refresh (fast, cheap, ~2-3 min, once per ticker per quarter).
- **Manual per-ticker trigger only for v1.** No scheduler, no bulk fleet button, no auto-fire on earnings. v1 is a button on `/status` rows + `/pipeline/[runId]` header. Bulk and scheduled triggers are deferred to v1.5 once the manual flow is validated.
- **No Investor Council.** Step 4 reuses the existing `risk_stress_test` Sonnet prompt with refreshed context. Multi-persona critique is deferred — `risk_stress_test` already provides adversarial framing, and the differentiation isn't worth the LLM cost or new prompt design until v1 is in real use.
- **Auto-advance, SSE-streamed.** All 5 steps run continuously after the click; SSE pushes per-step events to the frontend exactly as pipeline does. Single report page with collapsible step cards. No human interrupts between steps (matches the pipeline's pattern after its own interrupt removal).
- **Tight status-board integration.** Step 4 writes back `kill_criterion_states` flips. The `services/status_board.py` staleness check is extended to read `workspace_runs.created_at` so a workspace refresh resets staleness without rerunning the pipeline. Workspace verdict mirrors the status-board badge palette.
- **Skip LangGraph.** Workspace has 5 sequential steps, no branching, no loops, no checkpoints beyond the persisted `workspace_runs.step_outputs`. Plain async sequence inside `WorkspaceService._run_workspace()` is simpler and adequate.

## How the workspace maps to the exoskeleton

| Workspace step          | Exoskeleton steps              | Existing infra reused                                      | New work for v1                     |
| ----------------------- | ------------------------------ | ---------------------------------------------------------- | ----------------------------------- |
| 1. Update / Refresh     | 04 (model build), 10 (earnings)| `model_diff`, `ticker_models` versioning, FMP/EDGAR clients| Cell-level historical-actuals patch |
| 2. Research             | 02 (triage), 03 (DD)           | Open-questions list (Tier 1.2), Haiku                      | One Haiku prompt                    |
| 3. Validation           | 04 (model), 07 (valuation)     | `services/reverse_dcf.py`, model components                | Inline render in workspace page     |
| 4. Challenge / Sharpen  | 06 (insight), 08 (thesis), 11  | `risk_stress_test` Sonnet prompt, `kill_criterion_states`  | Refreshed context + writeback path  |
| 5. Differentiation      | 03 (DD comps), 09 (read-thru)  | `competitor_landscape`, FMP, Tier 1.4 read-through engine  | Peer-comp table + median compute    |

## Step semantics

### Step 1 — Update / Refresh

**Purpose:** Pull the latest external data, update the historical cells of the model, and produce a diff against the prior version.

**Sources:**
- Latest 10-Q via `EdgarClient.get_filing_index` (already exists)
- Latest earnings transcript via `fetch_recent_transcripts` (post-2026-05-08 fix; correct ticker routing)
- FMP `income-statement` / `balance-sheet-statement` / `cash-flow-statement` / `key-metrics-ttm` for the latest reported quarter
- FMP `analyst-estimates` for refreshed consensus

**Action:**
1. Load the latest `ticker_models` row (version N).
2. Patch historical cells in `ModelState.income_statement` / `balance_sheet` / `cash_flow` with the latest period's actuals. Forecast drivers and overrides are preserved untouched.
3. Run `recompute()` (existing `model_balancing.py`) so derived cells (free_cash_flow, balance plug) reflect the new actuals.
4. Diff via `model_diff.diff_states(prior, new)`.
5. Persist new `ticker_models` row at version N+1, `parent_research_run_id` unchanged.
6. Emit citations (with `cell_path` populated) for every changed cell — FMP citation for actuals, EDGAR/transcript for narrative-driven changes.

**Output (Pydantic):**
```
UpdateRefreshOutput {
  version_before: int
  version_after: int
  changed_cells: list[ChangedCell]   # cell_path, prior_value, new_value, source, citation_id
  new_filings: list[FilingRef]       # form, accession, fetched_at
  consensus_delta: list[EstimateDelta] | None
  summary: str                       # one-line "loaded latest 10-Q (filed 2026-05-01), 2 income-statement actuals updated"
}
```

### Step 2 — Research

**Purpose:** Surface what jumped out in the new sources that warrants follow-up.

**Sources:** new 10-Q text + new transcript + prior `research_runs` thesis + prior open-questions list (Tier 1.2)

**Action:** Single Haiku call. Prompt: *"Given the new 10-Q + transcript, what 3-5 specific items jumped out vs. the prior thesis? For each, classify as `confirms_thesis` / `threatens_thesis` / `new_unknown`."* Optional append to open-questions list with `surfaced_by: "workspace_run:<id>"` provenance.

**Output:**
```
ResearchOutput {
  highlights: list[Highlight]        # text, classification, citation_id
  new_open_questions: list[Question] # appended to existing log
  summary: str                       # short markdown
}
```

### Step 3 — Validation / Sensitivity

**Purpose:** Re-derive the reverse-DCF outputs against the updated model and current price.

**Sources:** updated `ticker_model` from Step 1 + live FMP quote (via `app.state.fmp` singleton — same pattern as `models_api.py::_fetch_live_price`)

**Action:** Call existing `services/reverse_dcf.py` functions:
- `solve_implied_driver(state, dim)` for each of revenue_growth / operating_margin / terminal_multiple
- `solve_implied_irr(state, price)`
- `sensitivity_grid(state, dim_x, dim_y)` for the same 3 axes the model page uses
- `thesis_vs_priced_in(state, price)`

No new computation. Workspace renders these inline using the existing `<ImpliedDriversTable />`, `<SensitivityHeatmap />`, `<ThesisVsPricedTable />` components from `components/model/`. Footer link to `/model/{ticker}#reverse-dcf` for full deep-dive.

**Output:**
```
ValidationOutput {
  implied_drivers: ImpliedDriversBundle
  implied_irr: float
  sensitivity_grids: list[SensitivityGrid]
  thesis_vs_priced_in: ThesisVsPricedIn
  current_price: float
  citation_ids: list[str]            # FMP quote + reverse-DCF inputs
}
```

### Step 4 — Challenge / Sharpen

**Purpose:** Stress-test the existing thesis against the updated model and new filings; flip kill criteria and catalyst statuses where the LLM concludes a state change.

**Sources:** prior `research_runs.thesis` output + updated `ticker_model` + new filings/transcript text + prior `kill_criterion_states` + open `catalysts`

**Action:** One Sonnet call using a refreshed-context variant of the existing `risk_stress_test` prompt. Framing addition: *"You are evaluating whether anything in this update changes the existing thesis or kill criteria. For each kill criterion, output `armed | triggered | resolved`. For each open catalyst, output `still_pending | resolved | missed`."*

Structured Pydantic output. Service applies writebacks:
- `kill_criterion_states` upserts (existing PUT path, idempotent on `(run_id, ordinal)`).
- `catalysts` row updates for resolution / miss.
- All writes carry `surfaced_by_workspace_run_id` provenance via `step_outputs.challenge_sharpen.kill_criterion_writes` (no schema change — provenance is in JSONB).

**Output:**
```
ChallengeOutput {
  stress_test_summary: str           # markdown
  kill_criterion_writes: list[KillCriterionWrite]  # ordinal, status, note
  catalyst_updates: list[CatalystUpdate]
  proposed_verdict: Literal["healthy","imminent","triggered","broken"]
}
```

### Step 5 — Differentiation

**Purpose:** Show where the ticker stands vs. its named competitors and what peers are signaling.

**Sources:** `competitor_landscape.competitors[]` rows where `resolved_to_ticker IS NOT NULL` (cap at 8 to bound FMP load); `services/read_through.py` resolver filtered to this ticker.

**Action:**
1. For each resolved peer, `asyncio.gather` FMP `key-metrics-ttm` + `financial-growth` (with `return_exceptions=True` so a single peer failure doesn't abort the step).
2. Build the metric matrix: PE, EV/EBITDA, P/B, P/FCF, P/S, ROE, revenue YoY, EPS YoY, gross margin, EBITDA margin.
3. Compute peer median per metric; ticker's delta vs median.
4. Resolve current read-throughs for this ticker via `services/read_through.py::resolve_read_throughs`.

**Output:**
```
DifferentiationOutput {
  peer_comp: PeerCompTable           # rows: peers + ticker + median + delta
  read_throughs: list[ReadThroughItem]  # filtered to this ticker
  per_peer_errors: list[PeerError]   # peer_ticker, error_message
}
```

### Verdict

After all 5 steps complete, resolve verdict using the same first-match-wins logic as `services/status_board.py::_resolve_health` (broken > triggered > stale > imminent > healthy), driven by the post-Step-4 `kill_criterion_states` and updated catalysts. Persisted on `workspace_runs.verdict`. Rendered as a top-of-page badge using the existing status-board palette.

## Schema

**New table `workspace_runs`:**

| Column                          | Type                  | Notes                                          |
| ------------------------------- | --------------------- | ---------------------------------------------- |
| `id`                            | uuid PK               |                                                |
| `ticker`                        | str, indexed          | normalized via `Ticker = NewType("Ticker",str)`|
| `parent_research_run_id`        | uuid FK→research_runs | nullable (run could be archived)               |
| `ticker_model_version_before`   | int                   |                                                |
| `ticker_model_version_after`    | int, nullable         | populated when Step 1 succeeds                 |
| `status`                        | str                   | `running` \| `complete` \| `failed`            |
| `verdict`                       | str, nullable         | populated when run completes                   |
| `step_outputs`                  | jsonb                 | keyed by step name; Pydantic-serialized        |
| `citations`                     | jsonb                 | accumulated cell-tagged citations              |
| `error`                         | str, nullable         | orchestrator-level failure message             |
| `created_at`                    | timestamptz           |                                                |
| `updated_at`                    | timestamptz           |                                                |

Index on `(ticker, created_at desc)` for the per-ticker history list.

**No schema changes to other tables.** `kill_criterion_states` writes go through the existing PUT shape; `ticker_models` already has versioning; `catalysts` already has resolution columns; `StateCitation.cell_path` was added in migration `2db2e8812418` for Tier 3.7.

**Staleness reset for `/status`:** extend `services/status_board.py::_resolve_staleness` to take the latest `workspace_runs.created_at` for the ticker into account. Currently staleness is `now - research_runs.completed_at > 90d`; new logic is `now - max(research_runs.completed_at, latest_workspace_run.created_at) > 90d`. One join, no caching.

## Code organization

**Backend:**

```
backend/app/models/workspace_run.py        # ORM
backend/app/models/workspace_schemas.py    # Pydantic step output schemas
backend/app/services/workspace.py          # WorkspaceService orchestrator + SSE queue
backend/app/services/workspace_steps.py    # 5 step functions, all async, all module-level
backend/app/api/workspace.py               # endpoints
backend/migrations/versions/<rev>_workspace_runs.py
```

`WorkspaceService` mirrors `PipelineService`'s pattern:
- `dict[run_id, asyncio.Queue]` for SSE subscribers
- `_emit(run_id, event)` pushes events
- `event_stream(run_id)` consumed via `GET /api/workspace/runs/{id}/stream`
- `_run_workspace(run_id, ticker)` background task fired by `POST /api/workspace/{ticker}/runs`

Each step function in `workspace_steps.py`:
```python
async def step_update_refresh(ctx: WorkspaceContext) -> UpdateRefreshOutput: ...
async def step_research(ctx: WorkspaceContext) -> ResearchOutput: ...
async def step_validation(ctx: WorkspaceContext) -> ValidationOutput: ...
async def step_challenge(ctx: WorkspaceContext) -> ChallengeOutput: ...
async def step_differentiation(ctx: WorkspaceContext) -> DifferentiationOutput: ...
```

`WorkspaceContext` carries the db session, FMP/EDGAR/Anthropic clients, the prior research_run, the prior ticker_model, and the SSE emitter. All 5 functions are pure relative to the context — easy to unit-test by stubbing the context.

**Frontend:**

```
frontend/app/workspace/page.tsx                     # fleet-wide recent workspace runs (cheap freebie)
frontend/app/workspace/[runId]/page.tsx             # single SSE-subscribed report page
frontend/components/workspace/
  WorkspaceReport.tsx                               # orchestrator
  VerdictBadge.tsx                                  # reuses status-board palette
  StepCards/
    UpdateRefreshCard.tsx                           # diff panel + citation chips
    ResearchCard.tsx                                # markdown summary + open-questions delta
    ValidationCard.tsx                              # reuses ImpliedDriversTable / SensitivityHeatmap / ThesisVsPricedTable
    ChallengeCard.tsx                               # stress-test markdown + kill-criterion flip table + catalyst updates
    DifferentiationCard.tsx                         # peer-comp table + embedded ReadThroughDrawer
frontend/lib/api.ts                                 # extended with workspace endpoints + SSE event types
```

## API surface

```
POST   /api/workspace/{ticker}/runs           → 202 + {run_id}; kicks off background task
GET    /api/workspace/runs/{run_id}           → full WorkspaceRun
GET    /api/workspace/runs/{run_id}/stream    → SSE; mirrors /api/runs/{id}/stream
GET    /api/workspace/{ticker}/history        → recent 30 workspace_runs for this ticker
GET    /api/workspace/recent                  → recent 30 across all tickers (for /workspace index)
```

`{ticker}` paths use the existing `TickerPath` dependency for boundary normalization.

**SSE event union** (mirrors pipeline's `SSEEvent` typed in `frontend/lib/api.ts`):

```ts
| { type: "workspace_run_start"; run_id: string; ticker: string }
| { type: "step_start"; step: WorkspaceStep }
| { type: "step_complete"; step: WorkspaceStep; output: StepOutput }
| { type: "step_failed"; step: WorkspaceStep; error: string }
| { type: "workspace_run_complete"; verdict: Verdict; version_after: number }
| { type: "workspace_run_failed"; error: string }
```

## UI surface + entry points

`/workspace/[runId]/page.tsx` subscribes to SSE on mount. Top: ticker header, `VerdictBadge`, version-before/after, parent-research-run link. Body: 5 collapsible step cards, each starts collapsed; the active step expands automatically and shows a spinner; on `step_complete` it renders its output and stays expanded.

Step cards are independent components in `components/workspace/StepCards/`. `ValidationCard` reuses the existing reverse-DCF components from `components/model/`. `DifferentiationCard` embeds the existing `ReadThroughDrawer` from `components/status/`.

**Entry points:**
- `/status` row: new `↻ Workspace` button next to the existing `⟿ N` read-throughs badge. POST → redirect to `/workspace/[runId]`.
- `/pipeline/[runId]` header: `Refresh workspace →` link, only enabled if `research_runs.status === "completed"`.
- Top-level nav: add "Workspace" entry pointing to `/workspace` index page (recent fleet-wide runs).

## Error handling

- **Step-level failure** wraps each step function in `try/except`. On exception: emit `step_failed`, store `{error: str}` in `step_outputs[step]`, **continue to next step**. Mirrors deep-dive's per-category resilience pattern.
- **Step 1 failure** is special: no new `ticker_models` version is created, `version_after` stays null, and Steps 3 + 4 fall back to running against the prior model state. The downstream verdict still resolves; the report just shows "Step 1 failed; downstream analysis ran against version N."
- **Step 4 failure** means no kill-criterion writebacks for this run — verdict falls back to the existing pre-run status from `_resolve_health(latest_research_run, latest_kill_criterion_states)`.
- **Step 5 per-peer failures** captured in `DifferentiationOutput.per_peer_errors`; the table renders with the peers that succeeded.
- **Orchestrator-level failure** (DB down, no `research_run` for ticker, etc.) sets `status="failed"` + `error=...` and emits `workspace_run_failed`.
- **Cancellation** (CancelledError from `BaseException`) bypasses `except Exception`; a `finally` block resolves any stuck `running` to `failed` to avoid stale "running forever" rows. Same pattern as `FanoutService`.
- **Concurrent runs for same ticker:** v1 accepts last-write-wins. Single-user personal tool; the practical race window is small. If it ever matters, add an advisory lock keyed on ticker.

## Testing

Pattern follows existing `backend/tests/` structure (stdlib `unittest`, run via `python -m unittest backend.tests.<module>` from project root):

- `tests/test_workspace_steps.py` — unit tests per step function with stubbed `WorkspaceContext`. LLM and FMP at boundaries are mocked.
- `tests/test_workspace_service.py` — orchestrator integration test using a real DB session + mocked external clients; verifies SSE event ordering, step_outputs persistence, verdict resolution.
- `tests/test_workspace_api.py` — FastAPI TestClient covering POST/GET/stream endpoints + TickerPath normalization.
- `tests/test_status_board_with_workspace.py` — extends existing status-board tests to cover the new workspace-aware staleness resolution.

Frontend: smoke-test the `/workspace/[runId]` SSE subscription against a recorded event sequence (no formal frontend test framework today; manual Playwright walkthrough acceptable).

## Open items / explicit non-goals for v1

- **No bulk fleet trigger.** "Refresh fleet" deferred until the manual flow is validated in real use.
- **No scheduler.** No auto-fire on earnings catalyst windows.
- **No Investor Council.** Step 4 reuses `risk_stress_test`; multi-persona deferred.
- **No valuation bands.** Historical EV/EBITDA / EV/Sales bands deferred (separate sub-feature).
- **No "variant view" LLM call** in Step 5. Peer comp + read-throughs are sufficient v1 punchline.
- **No human interrupts.** Auto-advance throughout.
- **Workspace runs do not produce a new `research_run`.** They reference one. The status board's "no research_run in 90d" rule becomes "no research_run *or* workspace_run in 90d."
- **No archival or cleanup of old workspace_runs.** Append-only for v1; eviction is future work if rows ever balloon.

## Done definition

- One-click workspace refresh from `/status` produces a complete report in ≤3 minutes for the median ticker.
- New `ticker_models` version is created at Step 1 and visible on `/model/{ticker}#history`.
- Step 4 stress-test writebacks update `kill_criterion_states` and the change is visible on `/status` without a page refresh (next 60s poll).
- `/status` staleness reflects the latest workspace_run, not just the parent research_run.
- All 5 step cards render their outputs end-to-end; failures in any single step do not abort the run.
- Manual Playwright walkthrough for at least 2 tickers (one with rich `competitor_landscape`, one without) confirms graceful degradation.

## Next steps

1. User reviews this spec and confirms the design.
2. Invoke writing-plans skill to produce the phased implementation plan.
3. Execute via subagent-driven-development or executing-plans.
