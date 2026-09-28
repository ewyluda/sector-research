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

Personal stock-research app. Two-pane split: **Discovery** (FMP fundamentals + X social signal merged into ranked company cards per theme) and **Pipeline** (a 6-phase due-diligence flow with citations on every data point). No auth — local-only tool.

Six nav entries (see `frontend/components/Nav.tsx`) + a global ⌘K command palette (`frontend/components/GlobalCommandPalette.tsx`, mounted in the root layout: tickers from `GET /api/tickers`, 14 surfaces, recent runs, contextual `New run:`/`Log trade:` actions, report sections on `/pipeline/[runId]` pages):

- **Today** (`/`) — morning briefing with a Briefing/Calendar tab strip (`?tab=calendar`): summary banner, 4-day calendar slice, needs-attention list (severity-tiered: broken/triggered health + high-materiality events → stale + medium → question rollups, which deep-link `/questions?ticker=`). The Calendar tab absorbed the old Catalysts page (week lanes + agenda with per-ticker undated-catalyst compaction and `archived thesis` chips); `/catalysts` is a server redirect to `/?tab=calendar`.
- **Status** (`/status`) — fleet-management view: every active thesis bucketed by health (Healthy / Imminent / Stale / Triggered / Broken), kill-criteria toggles + `KC n/m` drawer, read-through, earnings, and material-events drawers; row ⋯ menu links Company workspace / Model / View questions; ticker cells link `/company/[ticker]`.
- **Themes / Discovery** (`/themes`, `/theme/[id]`) — ranked companies per theme; cards carry a `Researched` chip linking the latest completed run; the stale-signals banner has an inline `Refresh signals` action.
- **Filings** (`/filings`, `/filings/graph`, `/filings/graph/theme`) — SEC EDGAR filing extraction, relationship graph (defaults to 2-hop, optionally theme-gated), theme-wide D3 force-graph map, counterparty resolution + dismiss tombstones, ingest-chore chip, and a collapsed Prospectus-reports disclosure.
- **Performance** (`/performance`) — verdict-outcome rollups (vs SPY / sector ETF / theme basket at 1d–6m horizons; data-first default offset, superseded hidden behind a toggle) plus the trade journal.
- **Library** (`/library`) — grouped-by-ticker run archive: expandable ticker groups, status/theme/has-thesis filters, greyed `abandoned` runs with a confirm-guarded Abandon action on >7-day zombies (`POST /api/runs/{id}/abandon`).

Demoted but live (reachable via ⌘K or contextual links, no nav entry):

- **Prospectus** (`/prospectus`, `/prospectus/[reportId]`) — S-1 / S-1/A reports: 4-step pipeline (ingest → relationships → 7 IPO-tuned categories → thesis) reusing the EDGAR plumbing under a `synthetic_ticker`; verdicts participate / watch_post_lockup / pass. Also listed on `/filings`.
- **Workspace** (`/workspace`, `/workspace/[runId]`) — 5-step workspace-loop orchestrator that refreshes a thesis (update_refresh → research → validation → challenge → differentiation) and produces an updated verdict + model deltas; failed rows get a preflight-gated Retry.
- **Questions** (`/questions`) — open-question log with retry/dismiss/resolve, priority/category filter chips (URL-state), row checkboxes + bulk dismiss/snooze (`POST /api/questions/bulk`; `snoozed_until` rows drop out of open lists and rollups until expiry).

Plus the run-creation flow (`/pipeline/new`, `/pipeline/[runId]`), the per-ticker financial model (`/model/[ticker]`), the company workspace (`/company/[ticker]` with overview / financials / model / peers / research / theses / transcripts / filings tabs, backed by the `/api/company` router), and ad-hoc peer comparison at `/compare?tickers=` (URL is the state; no nav link by design).

Two deployables in a flat layout:

- `backend/` — FastAPI + async SQLAlchemy + PostgreSQL + the Anthropic SDK (Python 3, venv in `backend/venv/`)
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

Backend tests live in `backend/tests/` and run via Python's stdlib `unittest`. Invoke as `python -m unittest backend.tests.<module>` from project root with the venv active. No pytest, no coverage harness. `backend/tests/` has no `__init__.py` (PEP 420 namespace package) — `unittest discover` fails; run the full suite via explicit enumeration:

```bash
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

End-to-end research run (real Postgres, recorded FMP responses, fake LLM — no network; CI runs it after `alembic upgrade head && alembic check` against a fresh database). It needs its own process so `DATABASE_URL` is set before app modules import:

```bash
PIPELINE_E2E=1 DATABASE_URL=postgresql+asyncpg://…/<migrated db> python -m unittest backend.tests.test_pipeline_e2e
DATABASE_URL=… python -m backend.scripts.record_pipeline_fixture VRT   # re-record backend/tests/fixtures/fmp_VRT.json
```

Harness: `backend/tests/pipeline_harness.py` (`ReplayFMP` — unrecorded calls raise `FMPClientError`, like an outage; `FakeAnthropic` — canned JSON per schema title). Models declare every index the migrations create, so `alembic check` is a real gate — keep them in sync.

Backend lint is ruff (config in root `ruff.toml`, pinned in `backend/requirements-dev.txt`): `ruff check backend` from project root. Shared `ModelState` test fixtures live in `backend/tests/model_fixtures.py` (no `test_` prefix so the enumeration glob skips it).

**Frontend:**

```bash
cd frontend
npm install
npm run dev        # Next dev server on :3000
npm run build
npm run lint       # eslint (flat config in eslint.config.mjs)
npm run typecheck  # tsc --noEmit (tsconfig has allowImportingTsExtensions for the .mts tests)
npm test           # node --test lib/*.test.mts (6 logic suites)
NEXT_PUBLIC_API_URL=http://127.0.0.1:8010 npm run build && npm run test:e2e   # Playwright smoke + axe
```

`test:e2e` serves a production build against `e2e/mock-api.mjs`, which replays `e2e/fixtures/api.json` (re-record with `MOCK_API_RECORD=http://127.0.0.1:8000 npx playwright test` against a running backend). Each nav page and a finished report must render with no console errors and no serious/critical axe violations — `KNOWN_A11Y_EXCEPTIONS` in `e2e/smoke.spec.ts` is empty; keep it that way. Colour tokens: text on dark uses `--primary-dk` (not `--primary`, which is the fill behind white text) and `--text-faint` is the dimmest text that clears 4.5:1.

**CI:** `.github/workflows/ci.yml` runs on every push — backend job (ruff + full unittest suite, dummy env vars for the required keys) and frontend job (tsc / eslint / node --test). Keep it green; it's the only regression gate.

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

### Where the detailed notes live

Subsystem notes sit next to the code and load when you work there:

- `backend/app/graph/CLAUDE.md` — the pipeline (phases, routing, state, `llm.py`, caching) and deep-dive data routing. Read before touching `backend/app/graph/`.
- `backend/app/services/CLAUDE.md` — discovery; the SEC EDGAR filing pipeline (extraction → relationships → resolution → supply-chain graph → fan-out); workspace loop; peer comparison; status board, catalysts and questions; trade journal; material events, insider and congress signals; company workspace; prospectus pipeline; theme delete; financial model + reverse DCF.
- `frontend/CLAUDE.md` — frontend layout, the `lib/api` client package, shared deep-dive utilities, section shell contract, print view.
- `backend/evals/README.md` — the eval harness. `docs/ARCHITECTURE.md` — the long-form reference. `docs/adr/` — decisions.

**Pipeline in one paragraph:** an explicit state machine (ADR-0004) — `quick_screen` (FAST_MODEL) → `deep_dive` (9 categories, DEEP_MODEL, warm-then-fan-out) → `thesis_construction` → `risk_stress_test`, which loops back to `deep_dive` when `graph/routing.py::should_loop` says so (≤ 2 loops), else completes; `position_monitor` is manual. `PHASE_SEQUENCE` / `next_phase()` in `graph/routing.py` are the single source of routing truth. JSON-producing calls must use `llm.complete_structured` (no assistant prefill — it 400s on current models).

### Citations as a first-class primitive

Every data-client method returns `tuple[data, Citation]`, not just data. `models/citation.py` defines two shapes: the `Citation` dataclass (in-memory / embedded in `CompanySignalCard` / etc.) and `CitationRecord` ORM (persisted rows). Inside the pipeline state, use `StateCitation` (in `graph/state.py`) — it's the JSON-serializable form with an ISO-string timestamp. When adding a new data source, preserve this convention or the report endpoint and frontend's `Citation[]` typing break silently. As of the 2026-06-11 polish pack, `node_deep_dive` persists the Citation halves of all primary + tier-2 FMP fetches into `state.citations` (previously only transcript + FRED citations landed). `ResearchState.add_citation` dedupes on `(source_url, metric)` — a duplicate key replaces the existing entry in place (latest fetch wins), so risk-loop re-runs don't mint duplicate chips.

### Streaming

SSE fan-out lives in one module: `services/event_broker.py::EventBroker` (emit / replay / terminal-close / heartbeat behind one class; per-subscriber queues bounded at 500, QueueFull drops for that subscriber only). Each orchestrator holds a configured instance and delegates its `_emit()` / `event_stream()`: **pipeline** (terminal `complete`/`error`, replay **off** — pre-subscribe events drop by design because `/pipeline/[runId]` REST-hydrates and pipeline runs emit hundreds of `token` chunks that must not replay into a hydrated UI; 30s heartbeat; `event_stream` yields SSE-framed strings via `broker.sse()`), **workspace** (`workspace_run_complete`/`_failed`, replay on) and **prospectus** (`prospectus_complete`/`_failed`, replay on) — both yield raw dicts via `broker.stream()`; their API routes do the SSE framing. `GET /api/runs/{id}/stream` wraps pipeline's in a `StreamingResponse`. Event types live as a discriminated union in `frontend/lib/api/pipeline.ts::SSEEvent` — keep the Python `_emit` calls and the TS union in sync. Selective replay for pipeline (buffer all but `token`) is the documented extension point in the module — do not add replay wholesale.

### Background task scheduling

Two kinds of async work run under the FastAPI process:

- **Phase execution** — `asyncio.create_task(pipeline._run_phase(...))` fires on `POST /api/runs` and on every `/advance`. The task opens its own `async_session()` internally (M1.2) — request-scoped sessions never cross into background tasks.
- **Four `AsyncIOScheduler` cron jobs** registered in `app/main.py::lifespan`: daily X signal refresh (02:00 local, `services.signal_scheduler.run_daily_refresh` — also computes per-theme graph centrality after the X pass), daily earnings-prints refresh (21:00, `services.earnings_scheduler`), verdict-outcome snapshot refresh (03:00 UTC, `services.outcome_tracker.refresh_snapshots`), and the 8-K + Form 4 material-events scan (06:30 UTC, `services.material_events_scheduler`).
### Import conventions

Backend uses **absolute imports rooted at project root**: `from backend.app.config import get_settings`. That's why uvicorn must be launched from project root. `backend/migrations/env.py` also imports from `backend.app.*`, so Alembic commands need project root on `PYTHONPATH` (running `alembic` from inside `backend/` works if you've activated the venv and `pip install -e .`'d — otherwise use `PYTHONPATH=.. alembic ...`).
## State-of-repo notes

`TODO.md` at the repo root is the live tracker for in-progress work and backlog, and `CHANGELOG.md` records what shipped — read both before starting anything substantive. The `skills/due-diligence/` + `BACKLOG.md` design-phase artifacts are gone; active specs live in `docs/superpowers/specs/` (which is itself `.gitignore`d, so it's local-only). If you need old plans or the due-diligence methodology, recover from git history (`git log --all --diff-filter=D -- docs/`).

## Agent skills

### Issue tracker

Issues live as GitHub issues in `ewyluda/sector-research` via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
