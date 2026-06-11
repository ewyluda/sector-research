# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**
Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**
When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**
Transform tasks into verifiable goals:

- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## PROJECT SPECIFIC INFO:

## What this is

Personal stock-research app. Two-pane split: **Discovery** (FMP fundamentals + X social signal merged into ranked company cards per theme) and **Pipeline** (a 6-phase LangGraph due-diligence flow with citations on every data point). No auth — local-only tool.

Ten top-level workspaces (see `frontend/components/Nav.tsx`):

- **Today** (`/`) — morning briefing: summary banner, 4-day calendar slice, needs-attention list (status-board health + open P1 questions). Pure frontend composition of the board/calendar/questions endpoints.
- **Themes / Discovery** (`/themes`, `/theme/[id]`) — ranked companies per theme.
- **Filings** (`/filings`, `/filings/graph`) — SEC EDGAR filing extraction, relationship graph (1- or 2-hop, optionally theme-gated), counterparty resolution.
- **Catalysts** (`/catalysts`) — upcoming-event calendar feeding the same data the status board surfaces.
- **Status** (`/status`) — fleet-management view: every active thesis bucketed by health (Healthy / Imminent / Stale / Triggered / Broken), kill-criteria toggles, read-through, earnings, and material-events drawers.
- **Prospectus** (`/prospectus`, `/prospectus/[reportId]`) — S-1 / S-1/A reports: 4-step pipeline (ingest → relationships → 7 IPO-tuned categories → thesis) reusing the EDGAR plumbing under a `synthetic_ticker`; verdicts participate / watch_post_lockup / pass.
- **Workspace** (`/workspace`, `/workspace/[runId]`) — 5-step workspace-loop orchestrator that refreshes a thesis (update_refresh → research → validation → challenge → differentiation) and produces an updated verdict + model deltas.
- **Questions** (`/questions`) — open-question log with retry/dismiss/resolve actions.
- **Library** (`/library`) — saved runs / archive.
- **Performance** (`/performance`) — verdict-outcome rollups (vs SPY / sector ETF / theme basket at 1d–6m horizons) plus the trade journal.

Plus the run-creation flow (`/pipeline/new`, `/pipeline/[runId]`), the per-ticker financial model (`/model/[ticker]`), the company workspace (`/company/[ticker]` with overview / financials / model / peers / research / theses / transcripts / filings tabs, backed by the `/api/company` router), and ad-hoc peer comparison at `/compare?tickers=` (URL is the state; no nav link by design).

Two deployables in a flat layout:

- `backend/` — FastAPI + async SQLAlchemy + LangGraph + PostgreSQL (Python 3, venv in `backend/venv/`)
- `frontend/` — Next.js 16 App Router + React 19 + Tailwind v4
- `.env` at **project root** is the single source of secrets for both sides

## ⚠️ Next.js 16 is not the Next.js you know

`frontend/AGENTS.md` says: _"This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code."_ Heed this before editing anything in `frontend/`. Do not assume `middleware.ts`, route-handler shapes, caching primitives, or Server Component APIs match older releases — check `node_modules/next/dist/docs/` first.

## Common commands

**Backend** (run from project root so `backend.app.*` absolute imports resolve):

```bash
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# Dev server — imports are absolute (backend.app.*), so launch from project root:
uvicorn backend.app.main:app --reload

# Migrations (alembic.ini lives in backend/):
cd backend && alembic upgrade head
cd backend && alembic revision --autogenerate -m "description"
```

Backend tests live in `backend/tests/` and run via Python's stdlib `unittest`. Invoke as `python -m unittest backend.tests.<module>` from project root with the venv active. No pytest, no coverage harness.

**Frontend:**

```bash
cd frontend
npm install
npm run dev        # Next dev server on :3000
npm run build
npm run lint       # eslint (flat config in eslint.config.mjs)
```

Frontend talks to the backend via `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). CORS on the backend allows `http://localhost:3000` by default.

## Environment

`SEC_USER_AGENT` is used by the EDGAR client — SEC requires a descriptive User-Agent string with a contact email (e.g. `"SectorResearch/1.0 ericwyluda@gmail.com"`). Set it in `config.py` settings.

Single `.env` at project root. `backend/app/config.py` reads it via `env_file="../../.env"` (relative to `backend/app/`), so the backend is hard-coded to that path — don't move the file. Required: `FMP_API_KEY`, `X_BEARER_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL` (asyncpg URL), `DATABASE_URL_SYNC` (used by Alembic).

### Test database (`sector_research_test`)

A local snapshot copy of the real `sector_research` Postgres DB (created 2026-06-10) for UX evaluation / destructive testing. Env vars beat `.env` (pydantic-settings precedence, verified), so point the backend at it without file changes:

```bash
DATABASE_URL="postgresql+asyncpg://ericwyluda@localhost:5432/sector_research_test" \
  uvicorn backend.app.main:app --reload
```

Refresh the snapshot from current real data:

```bash
psql -h localhost -d postgres -c "DROP DATABASE sector_research_test;"
psql -h localhost -d postgres -c "CREATE DATABASE sector_research_test;"
pg_dump -h localhost -Fc sector_research | pg_restore -h localhost -d sector_research_test --no-owner
```

Gotchas: use `pg_dump | pg_restore`, not `CREATE DATABASE … TEMPLATE` — idle sessions on the source DB block template copies. The 4 APScheduler cron jobs write into whichever DB the running backend points at, so a long-lived test-DB server diverges from the real DB (that's the point — just refresh before relying on it).

## Architecture essentials

### The pipeline (read this before touching `backend/app/graph/`)

`backend/app/graph/pipeline.py` compiles a LangGraph `StateGraph` around a single `ResearchState` dataclass (`graph/state.py`). Flow:

```
quick_screen (Haiku)
  → deep_dive (Sonnet, 9 categories in parallel)
  → targeted_followup (Haiku — retries P1 auto-answerable questions)
  → thesis_construction (Sonnet)
  → risk_stress_test (Sonnet)
       ├─ loop_required & loop_count ≤ 2 → back to deep_dive
       └─ else → completed
  → [optional: position_monitor (Haiku) — manually triggered]
```

**No interrupt gates.** Phases 1-5 run continuously after `POST /api/runs` starts a run. Each node sets `state.status = "in_progress"` to advance, or `"completed"` / `"watchlist"` to stop. The `PipelineService._run_phase()` loops while status is `in_progress`, automatically chaining through phases. Position monitor (phase 6) is manually triggered via `POST /api/runs/{run_id}/advance` with action `"approve"` on a completed run. If you add a new phase, update **both** `graph/pipeline.py` edges **and** `services/pipeline.py::_next_phase` — they're parallel sources of truth for routing.

**Prompt deduplication:** The thesis prompt receives quick screen context (verdict, thesis, key risk) and a concise deep dive summary (scores + top 2 findings per category) as "established findings" with instructions not to restate them. The risk prompt receives the thesis output with instructions to stress-test it, not re-derive the analysis.

`ResearchState` is persisted as JSONB into `research_runs.state` at every phase transition. All serialization goes through `to_dict()` / `from_dict()`. `CategoryResult` and `CategoryError` use a `__type__` discriminator in their dict form so `get_deep_dive_results()` can round-trip them. Add any new state field to `ResearchState` **and** make sure it's JSON-safe — datetime fields are stored as ISO strings, not `datetime` objects.

`CuratedFinancials` (in `graph/state.py`) holds a curated subset of FMP + FRED data for frontend dashboard charts. It's built once in `node_deep_dive` from the raw FMP fetch (8 quarters of income/balance/cashflow, profile, DCF, estimates, key-metrics-ttm, ratios-ttm, financial-growth, and 1-year daily OHLCV). Valuation ratios (PE, EV/EBITDA, P/B, P/FCF, P/S, PEG), dividend yield, and interest coverage come from `ratios-ttm`; return metrics (ROE, ROIC, ROA) from `key-metrics-ttm` — both via `_first_metric` fallback chains that keep the legacy key-metrics spellings working for old persisted payloads. Technical indicators (SMA 9/20/50/100/200, RSI 14) are computed in `_build_technical_data()` and stored in `daily_prices`. FRED macro indicators are attached after the main build. The report API returns it under `phases.deep_dive.curated_financials`. The `deep_dive_start` SSE event also carries it. Note: `phases.deep_dive` in the report API is `{ categories: Record<str, CategoryOutput>, curated_financials: CuratedFinancials | null }` — not a flat record.

Model selection lives in `graph/llm.py`: `SONNET = "claude-sonnet-4-6"`, `HAIKU = "claude-haiku-4-5-20251001"`. `complete()` and `stream_complete()` auto-enable prompt caching (`cache_control: ephemeral`) when the system prompt is >500 chars — keep reused system prompts long enough to benefit.

### Discovery engine

`services/discovery.py::DiscoveryEngine` runs two passes concurrently per theme:

1. **FMP screener pass** — runs the theme's `screener_criteria`, then enriches each ticker with income/balance/cashflow/profile via `_fetch_company_fundamentals` (batched 10 at a time to avoid hammering FMP).
2. **X signal pass** — **does not hit the X API at request time**. It reads pre-computed rows from the `signals` table. Those rows are written by the `signal_scheduler` APScheduler job that runs daily at 2 AM (wired up in `app/main.py` lifespan). Triggering a refresh on demand goes through `POST /api/themes/{id}/signals/refresh`.

Combined score = 40% X velocity + 40% fundamental quality + 20% discovery score when X data is fresh. When X is missing or stale, the weights collapse to 80% fundamental + 20% discovery. Staleness threshold lives in `clients/x_client.py::STALE_THRESHOLD_HOURS`.

The scheduler also dual-writes a `signal_history` row per signal_type per refresh — read it via `services/signal_history.list_signal_history()` or `GET /api/themes/{id}/signals/{ticker}/history?signal_type=velocity&days=N` (days clamped to [1, 365]). The current-value `signals` table semantics are unchanged.

### Citations as a first-class primitive

Every data-client method returns `tuple[data, Citation]`, not just data. `models/citation.py` defines two shapes: the `Citation` dataclass (in-memory / embedded in `CompanySignalCard` / etc.) and `CitationRecord` ORM (persisted rows). Inside the LangGraph state, use `StateCitation` (in `graph/state.py`) — it's the JSON-serializable form with an ISO-string timestamp. When adding a new data source, preserve this convention or the report endpoint and frontend's `Citation[]` typing break silently.

### Streaming

`services/pipeline.py::PipelineService` holds an in-memory `dict[run_id, asyncio.Queue]` for SSE subscribers. Events are pushed with `_emit()` and consumed via `event_stream()` which `GET /api/runs/{id}/stream` wraps in a `StreamingResponse`. Event types live as a discriminated union in `frontend/lib/api.ts::SSEEvent` — keep the Python `_emit` calls and the TS union in sync.

### Background task scheduling

Two kinds of async work run under the FastAPI process:

- **Phase execution** — `asyncio.create_task(pipeline._run_phase(...))` fires on `POST /api/runs` and on every `/advance`. The task holds the DB session passed from the request; if you change session lifecycle, verify the background task still has a live session.
- **Four `AsyncIOScheduler` cron jobs** registered in `app/main.py::lifespan`: daily X signal refresh (02:00 local, `services.signal_scheduler.run_daily_refresh`), daily earnings-prints refresh (21:00, `services.earnings_scheduler`), verdict-outcome snapshot refresh (03:00 UTC, `services.outcome_tracker.refresh_snapshots`), and the 8-K + Form 4 material-events scan (06:30 UTC, `services.material_events_scheduler`).

### SEC EDGAR filing pipeline (read this before touching `backend/app/services/edgar*`, `supply_chain.py`, `fanout.py`, or `relationship_context.py`)

Five-phase pipeline for extracting and consuming SEC filing narrative. All on-demand — no automatic trigger during pipeline runs.

**Phase A — Filing section extraction** (`services/edgar_sections_ingest.py` + `services/edgar_html.py`):

- `POST /api/filings/ingest/{ticker}` pulls the latest 10-K, 10-Q, and DEF 14A from EDGAR, extracts Item 1 Business, Item 1A Risk Factors, Item 7 MD&A (10-K) / Item 2 MD&A (10-Q), and DEF 14A Governance via BeautifulSoup.
- Strips inline XBRL (`ix:hidden` dropped, `ix:nonFraction`/`ix:nonNumeric` unwrapped to displayed value). Heading regex anchored to line-start (MULTILINE) for MD&A and Item 1 Business to avoid matching in-body cross-references.
- Item 1A regex tolerates mid-word whitespace: `R\s*I\s*S\s*K\s+F\s*A\s*C\s*T\s*O\s*R\s*S` — mirrors the `O\s*F` tolerance on MD&A patterns. Needed because XBRL/markup boundaries can split characters with `\n` mid-word (e.g., ORCL 10-K renders `Risk` as `R\nisk`).
- Full text stored in `filing_sections` table; prompt builders truncate to 5K chars per section via `FILING_EXCERPT_BUDGET_CHARS`.
- Idempotent on `(filing_id, section_key)`. Service functions return a summary dict with an `errors: []` list rather than raising on per-form problems — callers must either check the list or surface it to end users.

**Phase A — Prompt integration** (`FILING_EXCERPT_ROUTING` in `graph/nodes.py`):

- Deep-dive categories receive verbatim filing excerpts via `{filing_excerpts}` slot in `DEEP_DIVE_USER`: Business Quality ← Item 1, Risk Assessment ← Item 1A, Growth & Earnings ← Item 7 + Item 2, Management & Governance ← DEF 14A governance, Future Durability ← Item 7 + Item 1.
- Filing sections are fetched per-ticker in `PipelineService._fetch_filing_sections()` using a dedicated session (same pattern as `_fetch_edgar_facts`).

**Phase B — Relationship extraction** (`services/edgar_relationships.py`):

- `POST /api/filings/extract-relationships/{ticker}` runs one Haiku call per extractable section (Item 1, 1A, 7/2). Each section truncated to 15K chars.
- Pydantic structured output (`ExtractionResult` with `ExtractedRelationship` list) via `assistant_prefill='{"relationships":'`. Extracts counterparty_name, relationship_type, magnitude_pct, unnamed flag, verbatim_quote.
- Relationship types: `customer`, `supplier`, `partner`, `competitor`, `licensor`, `licensee`, `distributor`, `reseller`, `joint_venture`, `other`.
- Persisted in `relationships` table. Idempotent via `filing_sections.relationships_extracted_at` tombstone column — zero-relationship sections are marked too.

**Phase C — Counterparty resolution** (`services/counterparty_resolver.py`):

- `POST /api/relationships/resolve/{ticker}` normalizes counterparty names (strips Inc/Corp/LLC/Holdings/Group/etc, punctuation, lowercases) and matches against EDGAR's `company_tickers.json` (~10K entities).
- Exact match → auto-resolve. RapidFuzz `token_set_ratio` ≥ 95 → auto-resolve. 80-94 → curation queue. Below 80 → queue only.
- Aliases persisted in `counterparty_aliases` table (unique on `alias_normalized`). Write-through populates `relationships.resolved_to_cik` / `resolved_to_ticker` on every matching row.
- `GET /api/relationships/unresolved` → curation queue. `POST /api/relationships/alias` → manual override.

**Phase D — Supply-chain graph** (`services/supply_chain.py`):

- `GET /api/relationships/graph/{ticker}?direction=out|in|both&depth=1|2&theme_id=...` returns `{root_ticker, nodes[], edges[], summary}`. Depth defaults to 1; depth=2 runs a BFS over hop-1 counterparties to assemble their outbound/inbound edges as hop-2. `theme_id` (optional) gates which hop-1 nodes are expanded — only counterparties with a ticker tracked in that theme's `seed_tickers` get their hop-2 edges traversed, which is how the cross-theme "what does my universe see about NVDA's customers?" view is bounded.
- Each `GraphNode` carries `hop` and `in_selected_theme`; each `GraphEdge` carries `hop` and `source_ticker` (the node whose filing produced the edge — at hop 2 this is a hop-1 counterparty, not the root). `summary` is always the hop-1-only bucketed view the deep-dive card consumes, even when depth=2 — the multi-hop view bucketizes from `edges[]` directly.
- `POST /api/relationships/reconcile` flips `confirmed_bilateral=true` on reciprocal pairs (customer↔supplier, partner↔partner, competitor↔competitor, licensor↔licensee, distributor↔reseller, joint_venture↔joint_venture).
- Frontend: two consumers of this endpoint —
  1. `SupplyChainEcosystem` card in the deep-dive dashboard (after Business Quality) calls `getGraph(ticker, { depth: 1 })`. Groups counterparties by type, shows verbatim quotes, bilateral badges, tracker-links, and an **"Explore 2-hop graph →"** deep link to `/filings/graph?root={ticker}`.
  2. `/filings/graph` page (`MultiHopGraphView`) calls `getGraph(root, { depth: 2, theme_id? })` and renders a `RootHeader` + nested `HopGroup` disclosures with render-layer edge dedup (same `(from, to, type)` collapsed into one row with a disclosure-count badge).

**Phase E — Fan-out orchestration + deep-dive prompt routing** (`services/fanout.py` + `services/relationship_context.py`):

- `FanoutService` wired into `main.py::lifespan` as `app.state.fanout = FanoutService(edgar=app.state.edgar)` (reuses the shared EdgarClient). Three endpoints: `POST /api/themes/{id}/relationships/fanout?force=false` and `POST /api/tickers/{ticker}/relationships/fanout?force=false` return 202 + `fanout_id` immediately; `GET /api/fanouts/{id}` returns `FanoutStatus`. Status is in-memory (no restart persistence — acceptable for a personal tool).
- Per-ticker flow: serial ingest → extract → resolve, each in its own `async_session()` with an **explicit `await db.commit()`** (existing callers in `api/filings.py` do the same; `async_session` is `expire_on_commit=False` but does NOT autocommit — forgetting this means nothing persists). `force=True` only affects the extract stage; resolve already skips rows with `resolved_to_cik IS NOT NULL`. Ingest summary errors (no CIK, empty submissions, etc) are surfaced to `status.errors[]` so the UI doesn't report silent success.
- Per-ticker errors are captured in `status.errors[]` and don't abort the outer loop; `status = "failed"` only on orchestrator-level crashes. CancelledError (a `BaseException` subclass) bypasses `except Exception` and the `finally` block resolves the stuck "running" → "failed" state.
- Frontend: `/filings` page has a "Fan out" button per ticker card and "Fan out N" button per theme header; both poll `GET /api/fanouts/{id}` every 3s for progress.
- `relationship_context.py::get_counterparty_context(ticker, db) -> CounterpartyContext` pulls outbound + inbound relationship rows for a ticker (both via the denormalized `Relationship.ticker` column — no Filing join). Buckets are grouped by `relationship_type` and capped at 20 entries each (prefer rows with `magnitude_pct` populated as a salience proxy).
- Deep-dive prompt routing via `RELATIONSHIP_ROUTING: set[str] = {"Business Quality", "Risk Assessment", "Future Durability"}` (display-name keys matching `FILING_EXCERPT_ROUTING`'s convention). `_build_counterparty_context` is a nested closure inside `node_deep_dive` that renders the payload into the `{counterparty_context}` slot of `DEEP_DIVE_USER`, positioned immediately after `{filing_excerpts}`. Framing: "pre-extracted from the filing excerpts above; use these as anchors … do NOT re-quote verbatim text from the filings for these entities." Outbound renders with `$TICKER` notation for resolved counterparties; inbound renders under "Mentioned by others" and is the payoff for fan-out (e.g., MSFT's prompt sees `$ORCL — competitor`, `$NVDA — other` even when MSFT's own filings aren't ingested).
- `PipelineService._fetch_counterparty_context(ticker) -> CounterpartyContext` mirrors `_fetch_filing_sections` — dedicated `async_session()`, exception-safe empty-fallback. Threaded into `node_deep_dive` as the `counterparty_context=` kwarg alongside `filing_sections`, `edgar_facts`, etc.

Database tables (all in `models/filing.py`):

- `filings` — one row per accession_number (10-K, 10-Q, DEF 14A, etc.)
- `xbrl_facts` — XBRL numeric facts (RPO, debt maturity, credit). Customer concentration is NOT here: `ConcentrationRiskPercentage1` is always disclosed dimensionally and the SEC `companyfacts` API only exposes un-dimensioned parent facts. Concentration intel comes from Phase B narrative extraction (`Relationship.unnamed=true`).
- `filing_sections` — extracted narrative text per section per filing
- `relationships` — LLM-extracted counterparty relationships
- `counterparty_aliases` — normalized name → canonical CIK/ticker resolution

### Workspace loop (read this before touching `backend/app/services/workspace*.py`, `backend/app/api/workspace.py`, or `frontend/components/workspace/`)

Separate from the LangGraph pipeline. The **workspace loop** is a 5-step thesis-refresh orchestrator that pulls a completed research run forward in time: `update_refresh → research → validation → challenge → differentiation` (execution order pinned by `STEP_NAMES` in `services/workspace_steps.py`). Lives at `/workspace` (fleet list) and `/workspace/[runId]` (per-run report).

- `WorkspaceService` (in `services/workspace.py`) wired into `main.py::lifespan` as `app.state.workspace`. Mirrors `PipelineService` — in-memory `dict[run_id, asyncio.Queue]` SSE plumbing, `WorkspaceRunInFlight` guard against duplicate starts per ticker.
- Step implementations in `services/workspace_steps.py`. Output schemas in `models/workspace_schemas.py` (`UpdateRefreshOutput`, `ResearchOutput`, `ChallengeOutput`, `DifferentiationOutput`, `ValidationOutput` — each with a `WorkspaceVerdict` enum: `healthy | imminent | triggered | broken`). Run rows in `workspace_runs` (`models/workspace_run.py`) with a JSONB `step_outputs` column.
- API surface (`api/workspace.py`, prefix `/api/workspace`): kick off a run, poll status, stream SSE, list recent runs. Frontend `WorkspaceReport.tsx` dual-hydrates — REST on mount, then SSE for live updates as steps complete. `StepCards/` renders each step's output; `VerdictBadge` summarizes the final verdict on the index page.
- `update_refresh` is the only step that touches `ModelState`: it re-pulls FMP financials, promotes any newly-published forecast period from `ai_baseline` → `historical`, and warns when previously-edited override cells are evicted by a period rollover (`removed_cells` payload, surfaced in `UpdateRefreshCard`).

### Peer comparison (read this before touching `backend/app/services/peer_comp.py` or `peer_sets.py`)

`services/peer_comp.py` is the single peer-table builder shared by three consumers: `GET /api/peers/{ticker}/comp`, `GET /api/peers/compare?tickers=`, and workspace step 5 (differentiation). Schemas live in `models/peer_comp.py` (re-exported from `workspace_schemas.py` so old persisted `step_outputs` keep validating). 16 metrics from 4 FMP endpoints — note the /stable/ API serves valuation multiples (P/E, EV/EBITDA, P/B, P/FCF, P/S, PEG) from `ratios-ttm`, NOT `key-metrics-ttm` (live-verified 2026-06-09; `_fetch_one` uses a `_first` fallback-key helper; `fcf_margin` exists on neither endpoint and is derived as `p_s ÷ p_fcf`). Peer sets persist in `peer_sets` (ticker PK, JSONB peers) — auto-seeded from resolved `competitor_landscape` tickers ∪ `FMPClient.get_stock_peers`, capped at 8 (manual edits capped at 12). `services/peer_sets.py` functions write WITHOUT committing — callers own the session (API routes commit; `peers_for_ticker` is the read-only curated-first/fallback derivation the workspace step consumes). **Route-ordering footgun:** in `api/peers.py`, `/compare` must stay declared before `/{ticker}` — "compare" parses as a valid ticker (pinned by test). Frontend surfaces: `/company/[ticker]/peers` tab + `/compare` (URL is the state; no nav link by design).

### Status board, catalysts, and questions (read this before touching `backend/app/api/status.py`, `catalysts.py`, `questions.py`, `read_through.py`, or `frontend/components/status/`)

The post-thesis fleet-management surface — aggregate views over completed research runs, scheduled catalysts, and the open-question log.

- `GET /api/status/board` (`services/status_board.py`) → `{entries[], generated_at}`. One entry per `(ticker, theme)` keyed on the latest completed run, with `health` ∈ `healthy | imminent | stale | triggered | broken`, nearest catalyst, and kill-criteria summary. `POST /api/runs/{id}/archive` / `unarchive` hides/restores rows. `PUT /api/runs/{id}/kill-criteria/{ordinal}` flips an individual criterion's armed/triggered status (rows live in `kill_criterion_state`).
- `GET /api/status/read-throughs` and `POST /api/status/read-throughs/dismiss|summary` (`api/read_through.py`) feed the `ReadThroughDrawer` on the status board.
- `GET /api/catalysts` and `GET /api/catalysts/{id}` (`api/catalysts.py`) → the calendar view at `/catalysts`. Catalysts are promoted from research runs via `services/catalyst_promotion.py`; date resolution in `services/catalyst_dates.py`.
- `GET /api/catalysts/calendar?start=&end=` (`services/calendar_events.py`) → unified calendar: US high-impact economic releases + universe earnings (theme seeds ∪ active theses) + thesis catalysts, merged statelessly at request time (no tables, no scheduler). Two date-range FMP methods (`get_economic_calendar`, `get_earnings_calendar_range`, `TTL_CALENDAR` 6 h). FMP failures degrade to `warnings[]`, never 500. **Route-ordering footgun:** `/catalysts/calendar` must stay declared before `/catalysts/{catalyst_id}` (pinned by test). Frontend: `/catalysts` defaults to the calendar (week lanes + agenda, `components/catalysts/`), with the original bucket list behind the List toggle. Earnings rows deep-link `/status?expand_earnings=<run_id>` to auto-open the EarningsDrawer (one-shot per page load).
- `GET /api/questions`, `/by-ticker`, `POST /api/questions/{id}/dismiss|resolve|retry-auto` (`api/questions.py`) → the `/questions` page (`OpenQuestionsPanel` + `QuestionTickerRollupTable`). Open questions are minted by both pipeline runs and workspace steps; `retry-auto` re-runs the targeted follow-up Haiku.

### Trade journal (read this before touching `backend/app/services/journal*.py` or `frontend/components/journal/`)

Manual entry/exit trade log linked to `verdict_outcomes` (nullable FK, SET NULL). One row = one entry + one exit; null `exit_date` = open. `services/journal.py` is **commit-free** (callers own the session); `services/journal_comparison.py` is pure math — fractional returns, direction-aware (short = −long), SPY excess = trade − SPY over the holding period. Decision-vs-paper comparison picks the outcome snapshot at the offset nearest the holding period (`nearest_offset` midpoint thresholds 4/18/60/136 days) — labeled, never interpolated. `/api/journal`: trades CRUD (PATCH closes; explicit `exit_date: null` reopens + clears exit fields; a date move refreshes FMP-sourced fills but keeps manual prices sticky), `summary`, `price-preview` (FMP adjusted close on-or-before, 7-day lookback), `link-candidates` (non-superseded outcomes by ticker — lives here because `/api/outcomes` has no ticker filter). Price auto-fill is editable (`*_price_source`: `manual` | `fmp_eod_adjusted`); FMP failures degrade (SPY columns null, preview 404, no 500s). Frontend: journal section on `/performance` (`components/journal/`), "Log trade" buttons on status board + company header deep-link `/performance?log_trade=TICKER` (one-shot). Open-trade marks use live quotes (unadjusted vs adjClose entry — accepted approximation).

### Material events + insider signal (read this before touching `backend/app/services/material_events_scheduler.py`, `event_classifier.py`, `insider_*.py`, or `api/events.py`)

Daily 06:30 UTC cron (4th job in `main.py::lifespan`) scans the universe (theme seeds ∪ active theses — same derivation as the calendar, via the status board's latest-runs SQL). 8-K side: EDGAR submissions → item-code prefilter (skip non-empty subsets of {7.01, 9.01}; 2.02 kept — guidance lives there; empty items = missing metadata → classify) → Haiku classify (`event_classifier.py`, prefill + `parse_structured_output`, enum-normalized; classification errors are NOT tombstoned so they retry next run) → `Filing` (reuses `edgar_sections_ingest._upsert_filing`) + `material_events` (unique per filing, `dismissed_at` mirrors read-throughs). The 8-K side is fault-isolated: an EDGAR/Haiku failure rolls back and is recorded, but the insider ingest below still runs. Form 4 side: FMP `insider-trading/search` (`limit=100`; the SEC link field is `url`, live-verified 2026-06-10) → `insider_transactions` upsert idempotent on a sha256 `natural_key` over PARSED values (so `1000` vs `1000.0` serialization drift can't mint duplicates); `accession_number`/`sec_link` kept for future raw-EDGAR backfill. `insider_signal.py` is pure (90-day aggregate: open-market P/S only, null-price rows count but don't add value, cluster = ≥2 distinct buyers within 30d) → `signals` row `signal_type="insider"` per (ticker, theme) + `signal_history` dual-write. Discovery applies it as a bounded modifier (`apply_insider_modifier`: +5 cluster / +2 net buying / −3 pronounced selling, 48h staleness via `INSIDER_STALE_HOURS`, clamp [0,100]) — deliberately NOT a 4th weight; `InsiderSnapshot.is_stale` is overloaded (true for fresh-but-zero-modifier too — see its docstring before adding consumers). Status board joins a 14-day undismissed summary per ticker (one query, `_summarize_material_events`). `/api/events`: list (filterable), `{id}/dismiss`, `scan` (202 fire-and-forget; cron is primary). Frontend: `MaterialEventsDrawer` + badge on `/status` (deep link `/status?expand_events=<ticker>` — only resolves for tickers with a board entry; seed-only gap tracked in TODO), amber attention rows on Today (high materiality, 7d), insider chip on discovery cards.

### Company workspace (read this before touching `backend/app/api/company.py` or `frontend/components/company/`)

Fiscal.ai-inspired per-ticker shell at `/company/[ticker]` (PR #32) with tabs: overview / financials / model / peers / research / theses / transcripts / filings. Backed by the `/api/company` router (`header`, `overview`, `financials`, `transcripts` list/get/summary) over `services/company_snapshot.py` + `services/company_transcripts.py`. The model and filings tabs reuse the existing `/model/[ticker]` and filings surfaces; the Peers tab shares `components/peers/` with `/compare`. "Log trade" on the company header deep-links `/performance?log_trade=TICKER`.

### Prospectus pipeline (read this before touching `backend/app/services/prospectus_*.py` or `frontend/components/prospectus/`)

S-1 / S-1/A analysis pipeline (PR #31), parallel to research/workspace runs. `ProspectusService` (wired as `app.state.prospectus`) runs 4 steps — ingest → relationships → 7 IPO-tuned categories → thesis — with in-memory SSE queues and per-step session+commit, persisting into `prospectus_reports` (`step_outputs` JSONB; status ingesting | analyzing | completed | failed). Verdicts: `participate | watch_post_lockup | pass`. Key trick: issuers are written into `filings.ticker` / `relationships.ticker` under a **`synthetic_ticker`** (`proposed_ticker` if disclosed, else a slug of `issuer_name`, derived as a `@property` — don't re-normalize at the endpoint boundary), which lets the whole 5-phase EDGAR pipeline work unchanged on pre-IPO issuers. IPO category scores use their own rubric (0-30 disqualifying / 31-55 uncertain / 56-75 typical / 76-100 standout in `graph/prospectus_prompts.py`) — not the equity 40/55/70 tiers.

### Theme delete + cascade

`DELETE /api/themes/{id}` (in `api/themes.py`) is the single entry point — fired from `DeleteThemeButton` on the home-page `ThemeCard`. Cascade policy is set by migration `3cf8b874da39`: signal rows are ON DELETE CASCADE; `research_runs.theme_id` and `workspace_runs.theme_id` go to ON DELETE SET NULL so historical runs survive a theme deletion as orphans. `ResearchState.theme_id` stays non-nullable at the dataclass layer — nullable theme_id propagates safely through every caller (verified in PR #29 review).

### Financial model + reverse DCF (read this before touching `backend/app/services/model_*.py`, `backend/app/api/models_api.py`, or `frontend/components/model/`)

Editable 5-year financial model per ticker, AI-seeded from the latest completed `research_run`, with version history and a reverse-DCF engine. All on-demand — no automatic trigger from the LangGraph pipeline. The **`ModelState`** Pydantic model (`backend/app/models/model_state.py`) is the in-memory and JSONB-on-disk shape: `periods` (8 historical Q + 8 forecast Q + 5 forecast Y), `drivers[period][key]`, three statements (`income_statement`, `balance_sheet`, `cash_flow`) keyed `[line_item][period] -> ModelCell`, and an `assumptions` block (WACC, terminal growth, terminal multiple, share counts). Every `ModelCell` carries `value`, `source` (`historical` / `ai_baseline` / `driver` / `formula` / `override`), `formula`, `citation_id`, and edit-audit fields.

**Pipeline (services):**

- `model_baseline.py::build_baseline_state(ticker)` — orchestrator: load latest `research_run` + risk-free rate (FRED `DGS10`) → call Sonnet baseline-drivers node → seed historical cells from `CuratedFinancials` → seed forecast drivers → call `recompute()` → return state.
- `graph/model_baseline_node.py::generate_baseline_drivers(...)` — Sonnet pass that emits the forecast driver template (annual, then cloned to quarterly to stay in token budget). Uses markdown-fence stripping (no `assistant_prefill`) and `max_tokens=8192`.
- `model_balancing.py::recompute(state)` — pure synchronous: rebuilds P&L from drivers, then cash flow, then balance sheet rollforward; plugs the BS imbalance into `retained_earnings` so A=L+E holds. Cell-level overrides flow through: any non-null `source="override"` cell is preserved, downstream calculations consume the overridden value. Raises `ModelBalanceError` if the plug exceeds tolerance.
- `dcf.py::dcf(state, overrides=None)` — discounted cash flow over forecast periods + terminal value (Gordon growth or EV/EBITDA multiple, whichever the assumptions set). Reads `cash_flow.free_cash_flow` straight from state — caller must call `recompute()` first. Raises `ValueError` if any forecast FCF cell is missing.
- `reverse_dcf.py::solve_implied_driver(...)` / `solve_implied_irr(...)` / `sensitivity_grid(...)` / `thesis_vs_priced_in(...)` — bisection solvers and 21x21 grid evaluation. Driver overrides go through `_apply_uniform_override(state, dim, value)` + `deepcopy(state)` + `recompute()`, NOT the unused `overrides=` parameter on `dcf()`. `terminal_multiple` overrides skip recompute (only affects terminal value).
- `model_diff.py::diff_states(a, b)` — cell-path-keyed JSON diff between two `ModelState`s for the history viewer.
- `model_baseline.py::initialize_or_get_model(ticker, force=False)` — service-layer entry point used by `POST /api/models/{ticker}/initialize`. Uses its own `async_session()` with explicit `await db.commit()`.

**API surface** (`backend/app/api/models_api.py`, prefix `/api/models`, registered in `main.py` without a second prefix):

- `GET /{ticker}` — latest version + draft (or both null).
- `POST /{ticker}/initialize?force=` — seed (or re-seed) baseline. 400 on no completed `research_run`.
- `PUT /{ticker}/draft` — apply one cell edit (`cell_path` = `drivers.<period>.<key>` or `<stmt>.<line>.<period>` or `assumptions.<key>`), recompute, persist into `ticker_model_drafts` (idempotent per ticker — at most one draft row). 422 on bad `cell_path`, 409 on `ModelBalanceError`. The `cell_path` string is parsed/validated by `backend/app/models/cell_path.py` (typed `CellPath` discriminated union — `DriverPath` | `StatementCellPath` | `AssumptionPath`); frontend builds the string via `frontend/lib/cellPath.ts`. `AssumptionPath` is intentionally restricted to ModelCell-shaped keys (`discount_rate`, `terminal_multiple`, `perpetuity_growth`, `tax_rate`); the categorical assumptions (`terminal_method`, `plug_priority`) are not editable through this endpoint and need a separate typed surface.
- `POST /{ticker}/save` — promote draft → new `ticker_models` version, delete draft.
- `DELETE /{ticker}/draft` — discard.
- `GET /{ticker}/reverse-dcf?price=&from_draft=` — single payload: `implied_drivers` (3 scalar bisection solves), `implied_irr`, `sensitivity_grids` (3 × 21×21), `thesis_vs_priced_in`. `price` defaults to a live FMP quote via the shared `app.state.fmp` singleton (do NOT instantiate `FMPClient()` here). Wraps `Request` to access `request.app.state.fmp`.
- `GET /{ticker}/versions` — list. `GET /{ticker}/versions/{version}/diff?against=` — cell-keyed diff payload.

**Convention:** every endpoint normalizes `ticker = ticker.upper()` at entry — `ticker_models`, `ticker_model_drafts`, and `research_runs` all store tickers upper-case (matches `api/filings.py` and `api/earnings.py`). Skipping this normalization breaks lookup against existing rows and risks duplicate-identity drafts.

**Frontend (`/model/[ticker]`):** App-router page with three hash tabs (`#forecast` / `#reverse-dcf` / `#history`). Components in `frontend/components/model/`:

- `ForecastGrid.tsx` (the spreadsheet — sticky title h2 + sticky left line-item column, cells wired to `PUT /draft` via `CellRenderer.tsx`)
- `DriverPanel.tsx` (annual + quarterly driver inputs; some keys like `interest_income_yield` / `revolver_rate` are surfaced for future use but currently no-op'd by `model_balancing.py`)
- `FormulaBar.tsx` (active-cell readout)
- `ReverseDcfPanel.tsx`, `SensitivityHeatmap.tsx`, `ThesisVsPricedTable.tsx`, `WhatIfScratchPanel.tsx` — reverse-DCF tab UI
- `HistoryDiffViewer.tsx` — version-list + diff for the history tab
- `heatmapColors.ts` — diverging palette for the sensitivity grid (value-relative coloring; do not replace with `scoreColors.ts` which is for score-tier coloring)

The deep-dive `ReportHeader.tsx` carries a small `ModelStatusBadge` that links to `/model/{ticker}#forecast`. It calls `getModel(ticker)` only — it does NOT call `getReverseDcf` (which would trigger a live FMP quote on every report-page open). A `loaded` sentinel suppresses the initial render so users with a saved model don't see a "Create model →" flicker.

Database tables:

- `ticker_models` — saved versions. `(ticker, version)` unique. JSONB `state` column. `parent_research_run_id` FK to seeding run.
- `ticker_model_drafts` — at most one row per ticker (the unsaved working copy). `base_version_id` FK to the `ticker_models` row it forked from.

`StateCitation` (`graph/state.py`) gained a `cell_path` field so research-run citations can deep-link to specific model cells (migration `2db2e8812418`). Existing JSONB rows return as raw dicts so the new optional field doesn't break round-trip.

### Import conventions

Backend uses **absolute imports rooted at project root**: `from backend.app.config import get_settings`. That's why uvicorn must be launched from project root. `backend/migrations/env.py` also imports from `backend.app.*`, so Alembic commands need project root on `PYTHONPATH` (running `alembic` from inside `backend/` works if you've activated the venv and `pip install -e .`'d — otherwise use `PYTHONPATH=.. alembic ...`).

### Frontend layout

- `app/` — App Router pages: `/` (Today dashboard), `/themes` (themes grid), `/theme/[id]` + `/theme/new`, `/filings` (SEC filing extraction + curation queue), `/filings/graph` (multi-hop supply-chain graph view), `/catalysts`, `/status` (fleet board), `/prospectus` + `/prospectus/[reportId]` (S-1 reports), `/workspace` + `/workspace/[runId]` (workspace-loop runs), `/questions`, `/library`, `/performance` (outcomes + trade journal), `/pipeline/new`, `/pipeline/[runId]` (unified research page — handles both live streaming and completed reports), `/model/[ticker]` (editable financial model + reverse-DCF tabs), `/company/[ticker]` (company workspace — overview / financials / model / peers / research / theses / transcripts / filings tabs), `/compare` (ad-hoc peer comparison, URL-state). `/report/[runId]` redirects to `/pipeline/[runId]`.
- `lib/api.ts` — **every** backend call goes through the typed client here. Types mirror backend Pydantic/dataclass shapes; if you change a backend response, update this file or TS will silently accept stale shapes at the fetch boundary.
- `components/` — presentational pieces (`Nav`, `ScoreRing`, `SourceBadge`, `VelocityBadge`)
- `components/filings/` — `ThemeFilingsPanel`, `TickerFilingsCard`, `SectionReader` (modal), `CurationPanel` (counterparty resolution queue), `MultiHopGraphView` + `RootHeader` + `HopGroup` + `EdgeRowBody` (the `/filings/graph` page)
- `components/workspace/` — `WorkspaceReport` (dual-hydrating REST+SSE consumer), `VerdictBadge`, `StepCards/` (one card per workspace step: `UpdateRefreshCard`, etc.)
- `components/status/` — `ReadThroughDrawer`, `EarningsDrawer` (drawers off the status board)
- `components/questions/` — `OpenQuestionsPanel`, `QuestionRow`, `QuestionTickerRollupTable`
- `components/peers/` — `PeerCompTable` (grouped comparison table shared by the company Peers tab and `/compare`), `PeerSetEditor` (chip editor)
- `components/catalysts/` — `CatalystsView` (Calendar/List toggle), `CalendarView` + `WeekLanes` + `AgendaList`/`AgendaRow` + `EventCard` (the unified calendar UI)
- `components/company/` — company-workspace shell: `CompanyHeader`, `TabStrip`, `StatementTable`, `StatisticsGrid`, `PriceChart`, `TranscriptReader`, `ResearchTab`, `ThesesTab`, `BullsBears`
- `components/journal/` — `TradeJournalSection`, `TradeForm`, `TradeList`, `DecisionVsOutcomePanel`, `ExitReasonTable`
- `components/performance/` — `HeroBand`, `PerformanceFilters`, `ByVerdictTable`, `ByThemeTable`, `BySignalBucketPanel`, `OutcomeList`, `ReturnCell`
- `components/prospectus/` — `ProspectusList`, `NewProspectusButton`, `ProspectusReport` (REST + SSE), `VerdictPill`, `StepCards/` (⚠ `CategoryCard` uses IPO-specific score thresholds — do NOT swap in `scoreColors.ts`)
- `components/themes/` — `DeleteThemeButton`
- `components/today/` — `SummaryBanner`, `TodayLanes` (reuses catalysts `EventCard`), `AttentionList` (reuses `components/status/WorkspaceButton`, extracted from the status page); derivation logic in `lib/todayDerive.ts` (unit-tested via `node --test`)
- `components/deep-dive/` — 30+ component module for the financial dashboard: `DeepDiveDashboard` orchestrator (receives `ticker` prop for supply-chain card), `SectionNav` (sticky horizontal scroll-spy nav, pills grouped into Summary / Financials / Context / Qualitative clusters with visual dividers), `CommandPalette` (⌘K / Ctrl-K fuzzy jump over the same `sections.ts` registry), `ReportHeader` (company identity + verdict + thesis/risk callouts — the scoreboards live in `OverviewBanner`, not here), `OverviewBanner` (synthesized verdict line + radar + HeadlineMetrics + ScoreBar, single source for these), `VelocitySparkline` (X signal badge), `sections/` (9 category sections + CrossCategoryCorrelation + `SupplyChainEcosystem`), `charts/` (Recharts bar/line/trend + lightweight-charts candlestick), `panels/` (AI companion + findings table), `skeleton/` (loading placeholders)
- **Shared utilities under `components/deep-dive/`:**
  - `scoreKeys.ts` — `DISPLAY_TO_KEY` + `normalizeScoreKeys`. Use at every boundary where the backend hands you a `scores` object; the report API returns display-name keys (`"Macro & Regime"`) while the chip/radar components expect snake_case. Skipping this normalizer silently produces an all-em-dash ScoreBar.
  - `scoreColors.ts` — shared 4-tier palette at 40/55/70 thresholds with `scoreTier` / `scoreBadge` / `scoreSegment` helpers. Don't reintroduce local `if score >= 70 / >= 50` palettes; they cluster everything in 40-60 into a single amber band.
  - `sections.ts` — single registry the SectionNav and CommandPalette both read, so adding a section only needs one edit to stay in sync.
  - `usePersistedCollapse.ts` — per-section `useState`-compatible hook backed by `localStorage["sr:collapse:{id}"]`. Uses a skip-first-write pattern (`isFirstWrite` ref) so the default value from the initial render doesn't clobber the persisted value before the read effect hydrates.
- **Section shell contract:** `DataRichSection` and `MixedSection` render `AICompanionPanel` twice per section — once with `section="summary"` (score callout + key findings) inside the chart grid, and once with `section="analysis"` as a full-width block below. This prevents the analysis paragraph from making the right column 2x taller than the charts and leaving empty whitespace on the left. `QualitativeCard` still renders the panel without a `section` prop because it's already a single-column layout.
- **Print view:** `@media print` in `app/globals.css` hides any element carrying `data-print-hide="true"` and forces opaque surfaces. When you add new sticky UI (nav, action buttons, modals), tag it with that attribute so it drops out of the PDF.
- Path alias: `@/*` → project root. Tailwind v4 via `@tailwindcss/postcss`.
- Chart libraries: **Recharts** (bar, line, radar charts) and **lightweight-charts** (TradingView candlestick + RSI).

### Deep-dive data routing

`_fmt_fundamentals()` in `graph/nodes.py` builds the data payload every category receives. It includes: company profile, valuation ratios (PE, EV/EBITDA, P/B, P/FCF, P/S, PEG), return metrics (ROE, ROIC, ROA, interest coverage), 8 quarters of income statement trends with YoY growth, balance sheet with ST/LT debt structure, cash flow with SBC, DCF valuation, forward analyst estimates with earnings surprise, and historical growth rates. On top of that base payload, categories receive supplementary data via routing tables in `graph/deep_dive_routing.py`, rendered into prompt slots by the seven module-level builders in `graph/deep_dive_context.py` (each a pure function over a `DeepDiveContext` snapshot + category name; `node_deep_dive` builds the snapshot once after the FRED fetch block and calls `build_all_contexts`):

- **Transcript routing** (`TRANSCRIPT_ROUTING`): Management & Governance (all 5 passes), Business Quality (pass3, pass5), Growth & Earnings (pass1, pass4, pass6), Sentiment & Narrative (pass3, pass5), Risk Assessment (pass1, pass4), Future Durability (pass1, pass5).
- **Macro routing** (`MACRO_ROUTING`): Macro & Regime (all 9 FRED series), Risk Assessment (all 9), Future Durability (5 series), Financial Health (rates + yield curve).

- **Filing excerpt routing** (`FILING_EXCERPT_ROUTING`): Business Quality (Item 1), Risk Assessment (Item 1A), Growth & Earnings (Item 7 + Item 2), Future Durability (Item 7 + Item 1), Management & Governance (DEF 14A). Truncated to `FILING_EXCERPT_BUDGET_CHARS` (5000) per section.
- **Relationship routing** (`RELATIONSHIP_ROUTING`): Business Quality, Risk Assessment, Future Durability. Uses display-name keys. Rendered by `build_counterparty_context` in `deep_dive_context.py` from the `CounterpartyContext` fetched in `PipelineService._fetch_counterparty_context`. Positioned in `DEEP_DIVE_USER` right after `{filing_excerpts}` so the "anchors not re-quotes" instruction reads against the filing text. Empty payload → empty string → slot drops out cleanly.
- **EDGAR XBRL routing** (`EDGAR_ROUTING`): Growth & Earnings (RPO), Future Durability (RPO), Financial Health (debt maturity + credit), Risk Assessment (debt maturity + credit). Customer concentration is intentionally absent — see the `xbrl_facts` note above; concentration arrives via the relationship-routing path instead.
- **Quant routing** (`QUANT_ROUTING`): deterministic quant fingerprint metric groups (Piotroski F, Altman Z, Beneish M, accruals, FCF conversion, SBC dilution, margin OLS slopes) computed in pure Python by `services/quant_fingerprint.py` from the same 8-quarter FMP statements, attached to `CuratedFinancials.quant_fingerprint` inside `_build_curated_financials`, rendered into the `{quant_data}` slot by `build_quant_context`. Financial Health / Risk Assessment / Growth & Earnings / Business Quality / Management & Governance. TTM (quarters 0–3) vs prior-TTM (quarters 4–7); every metric independently nullable; Altman/Beneish marked not-applicable for Financial Services. Frontend: `QuantFingerprint.tsx` card (Financials cluster), hidden for runs predating the feature.

The deep dive fetches 11 FMP endpoints in parallel: income statement (8Q), balance sheet (8Q), cash flow (8Q), profile, DCF, analyst estimates (8Q), historical price (1Y), earnings transcript, key-metrics-ttm, ratios-ttm, and financial-growth (8Q). It also pulls ingested filing sections (if any) via `PipelineService._fetch_filing_sections()`, XBRL facts via `_fetch_edgar_facts()`, and the counterparty graph via `_fetch_counterparty_context()`.

## State-of-repo notes

`TODO.md` at the repo root is the live rolling tracker for in-progress work, backlog, and a "Done (recent)" log — read it before starting anything substantive so you know what's already shipped. The `skills/due-diligence/` + `BACKLOG.md` design-phase artifacts are gone; active specs live in `docs/superpowers/specs/` (which is itself `.gitignore`d, so it's local-only). If you need old plans or the due-diligence methodology, recover from git history (`git log --all --diff-filter=D -- docs/`).

## Agent skills

### Issue tracker

Issues live as GitHub issues in `ewyluda/sector-research` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
