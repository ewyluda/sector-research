# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Personal stock-research app. Two-pane split: **Discovery** (FMP fundamentals + X social signal merged into ranked company cards per theme) and **Pipeline** (a 6-phase LangGraph due-diligence flow with human-in-the-loop interrupts and citations on every data point). No auth — local-only tool.

Two deployables in a flat layout:

- `backend/` — FastAPI + async SQLAlchemy + LangGraph + PostgreSQL (Python 3, venv in `backend/venv/`)
- `frontend/` — Next.js 16 App Router + React 19 + Tailwind v4
- `.env` at **project root** is the single source of secrets for both sides

## ⚠️ Next.js 16 is not the Next.js you know

`frontend/AGENTS.md` says: *"This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code."* Heed this before editing anything in `frontend/`. Do not assume `middleware.ts`, route-handler shapes, caching primitives, or Server Component APIs match older releases — check `node_modules/next/dist/docs/` first.

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

No test framework is configured for the backend.

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

Single `.env` at project root. `backend/app/config.py` reads it via `env_file="../../.env"` (relative to `backend/app/`), so the backend is hard-coded to that path — don't move the file. Required: `FMP_API_KEY`, `X_BEARER_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL` (asyncpg URL), `DATABASE_URL_SYNC` (used by Alembic).

## Architecture essentials

### The pipeline (read this before touching `backend/app/graph/`)

`backend/app/graph/pipeline.py` compiles a LangGraph `StateGraph` around a single `ResearchState` dataclass (`graph/state.py`). Flow:

```
quick_screen (Haiku)
  → [interrupt]
  → deep_dive (Sonnet, 9 categories in parallel)
  → [interrupt]
  → thesis_construction (Sonnet)
  → risk_stress_test (Sonnet)
       ├─ loop_required & loop_count ≤ 2 → back to deep_dive
       └─ else → position_monitor (Haiku)
  → [interrupt]
  → END
```

**Interrupts are not LangGraph `interrupt()` calls.** They're modeled as a status flag: a node sets `state.status = "awaiting_approval"`, the conditional edge returns `END`, and the graph compiles out. The API route `POST /api/runs/{run_id}/advance` rewrites the status, advances `state.phase`, and kicks off the next phase via `asyncio.create_task(pipeline_service._run_phase(...))`. If you add a new phase, update **both** `graph/pipeline.py` edges **and** `services/pipeline.py::_next_phase` — they're parallel sources of truth for routing.

`ResearchState` is persisted as JSONB into `research_runs.state` at every phase transition. All serialization goes through `to_dict()` / `from_dict()`. `CategoryResult` and `CategoryError` use a `__type__` discriminator in their dict form so `get_deep_dive_results()` can round-trip them. Add any new state field to `ResearchState` **and** make sure it's JSON-safe — datetime fields are stored as ISO strings, not `datetime` objects.

`CuratedFinancials` (in `graph/state.py`) holds a curated subset of FMP data for frontend dashboard charts. It's built once in `node_deep_dive` from the raw FMP fetch (quarterly income/balance/cashflow, profile, DCF, estimates, and 1-year daily OHLCV). Technical indicators (SMA 9/20/50/100/200, RSI 14) are computed in `_build_technical_data()` and stored in `daily_prices`. The report API returns it under `phases.deep_dive.curated_financials`. The `deep_dive_start` SSE event also carries it. Note: `phases.deep_dive` in the report API is `{ categories: Record<str, CategoryOutput>, curated_financials: CuratedFinancials | null }` — not a flat record.

Model selection lives in `graph/llm.py`: `SONNET = "claude-sonnet-4-6"`, `HAIKU = "claude-haiku-4-5-20251001"`. `complete()` and `stream_complete()` auto-enable prompt caching (`cache_control: ephemeral`) when the system prompt is >500 chars — keep reused system prompts long enough to benefit.

### Discovery engine

`services/discovery.py::DiscoveryEngine` runs two passes concurrently per theme:

1. **FMP screener pass** — runs the theme's `screener_criteria`, then enriches each ticker with income/balance/cashflow/profile via `_fetch_company_fundamentals` (batched 10 at a time to avoid hammering FMP).
2. **X signal pass** — **does not hit the X API at request time**. It reads pre-computed rows from the `signals` table. Those rows are written by the `signal_scheduler` APScheduler job that runs daily at 2 AM (wired up in `app/main.py` lifespan). Triggering a refresh on demand goes through `POST /api/themes/{id}/signals/refresh`.

Combined score = 40% X velocity + 40% fundamental quality + 20% discovery score when X data is fresh. When X is missing or stale, the weights collapse to 80% fundamental + 20% discovery. Staleness threshold lives in `clients/x_client.py::STALE_THRESHOLD_HOURS`.

### Citations as a first-class primitive

Every data-client method returns `tuple[data, Citation]`, not just data. `models/citation.py` defines two shapes: the `Citation` dataclass (in-memory / embedded in `CompanySignalCard` / etc.) and `CitationRecord` ORM (persisted rows). Inside the LangGraph state, use `StateCitation` (in `graph/state.py`) — it's the JSON-serializable form with an ISO-string timestamp. When adding a new data source, preserve this convention or the report endpoint and frontend's `Citation[]` typing break silently.

### Streaming

`services/pipeline.py::PipelineService` holds an in-memory `dict[run_id, asyncio.Queue]` for SSE subscribers. Events are pushed with `_emit()` and consumed via `event_stream()` which `GET /api/runs/{id}/stream` wraps in a `StreamingResponse`. Event types live as a discriminated union in `frontend/lib/api.ts::SSEEvent` — keep the Python `_emit` calls and the TS union in sync.

### Background task scheduling

Two kinds of async work run under the FastAPI process:

- **Phase execution** — `asyncio.create_task(pipeline._run_phase(...))` fires on `POST /api/runs` and on every `/advance`. The task holds the DB session passed from the request; if you change session lifecycle, verify the background task still has a live session.
- **Daily signal refresh** — `AsyncIOScheduler` cron job registered in `app/main.py::lifespan`, calls `services.signal_scheduler.run_daily_refresh`.

### Import conventions

Backend uses **absolute imports rooted at project root**: `from backend.app.config import get_settings`. That's why uvicorn must be launched from project root. `backend/migrations/env.py` also imports from `backend.app.*`, so Alembic commands need project root on `PYTHONPATH` (running `alembic` from inside `backend/` works if you've activated the venv and `pip install -e .`'d — otherwise use `PYTHONPATH=.. alembic ...`).

### Frontend layout

- `app/` — App Router pages: `/` (themes), `/theme/[id]`, `/library`, `/pipeline/new`, `/pipeline/[runId]`, `/report/[runId]`
- `lib/api.ts` — **every** backend call goes through the typed client here. Types mirror backend Pydantic/dataclass shapes; if you change a backend response, update this file or TS will silently accept stale shapes at the fetch boundary.
- `components/` — presentational pieces (`Nav`, `ScoreRing`, `SourceBadge`, `VelocityBadge`)
- `components/deep-dive/` — 28-component module for the deep-dive financial dashboard: `DeepDiveDashboard` orchestrator, `DashboardSidebar` (scroll-tracked nav), `OverviewBanner` (radar + metrics + score bar), `sections/` (9 category-specific components in 3 tiers: data-rich, mixed, qualitative), `charts/` (Recharts bar/line/trend charts + lightweight-charts candlestick), `panels/` (AI companion + findings table), `skeleton/` (loading placeholders)
- Path alias: `@/*` → project root. Tailwind v4 via `@tailwindcss/postcss`.
- Chart libraries: **Recharts** (bar, line, radar charts) and **lightweight-charts** (TradingView candlestick + RSI).

## State-of-repo notes

The git working tree has a large block of deleted files under `docs/superpowers/` and `skills/due-diligence/` — these were design-phase artifacts replaced by the actual implementation under `backend/` and `frontend/`. The README still references some of them but they no longer exist on disk. If you need the due-diligence methodology that was in `skills/due-diligence/`, recover it from `git show HEAD:...` rather than assuming those files are missing in error.
