# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Personal stock-research app. Two-pane split: **Discovery** (FMP fundamentals + X social signal merged into ranked company cards per theme) and **Pipeline** (a 6-phase LangGraph due-diligence flow with human-in-the-loop interrupts and citations on every data point). No auth — local-only tool.

Three-pane split: **Discovery** (ranked companies per theme), **Pipeline** (6-phase due diligence), and **Filings** (SEC EDGAR filing extraction, relationship graph, and counterparty resolution).

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

`SEC_USER_AGENT` is used by the EDGAR client — SEC requires a descriptive User-Agent string with a contact email (e.g. `"SectorResearch/1.0 ericwyluda@gmail.com"`). Set it in `config.py` settings.

Single `.env` at project root. `backend/app/config.py` reads it via `env_file="../../.env"` (relative to `backend/app/`), so the backend is hard-coded to that path — don't move the file. Required: `FMP_API_KEY`, `X_BEARER_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL` (asyncpg URL), `DATABASE_URL_SYNC` (used by Alembic).

## Architecture essentials

### The pipeline (read this before touching `backend/app/graph/`)

`backend/app/graph/pipeline.py` compiles a LangGraph `StateGraph` around a single `ResearchState` dataclass (`graph/state.py`). Flow:

```
quick_screen (Haiku)
  → deep_dive (Sonnet, 9 categories in parallel)
  → thesis_construction (Sonnet)
  → risk_stress_test (Sonnet)
       ├─ loop_required & loop_count ≤ 2 → back to deep_dive
       └─ else → completed
  → [optional: position_monitor (Haiku) — manually triggered]
```

**No interrupt gates.** Phases 1-5 run continuously after `POST /api/runs` starts a run. Each node sets `state.status = "in_progress"` to advance, or `"completed"` / `"watchlist"` to stop. The `PipelineService._run_phase()` loops while status is `in_progress`, automatically chaining through phases. Position monitor (phase 6) is manually triggered via `POST /api/runs/{run_id}/advance` with action `"approve"` on a completed run. If you add a new phase, update **both** `graph/pipeline.py` edges **and** `services/pipeline.py::_next_phase` — they're parallel sources of truth for routing.

**Prompt deduplication:** The thesis prompt receives quick screen context (verdict, thesis, key risk) and a concise deep dive summary (scores + top 2 findings per category) as "established findings" with instructions not to restate them. The risk prompt receives the thesis output with instructions to stress-test it, not re-derive the analysis.

`ResearchState` is persisted as JSONB into `research_runs.state` at every phase transition. All serialization goes through `to_dict()` / `from_dict()`. `CategoryResult` and `CategoryError` use a `__type__` discriminator in their dict form so `get_deep_dive_results()` can round-trip them. Add any new state field to `ResearchState` **and** make sure it's JSON-safe — datetime fields are stored as ISO strings, not `datetime` objects.

`CuratedFinancials` (in `graph/state.py`) holds a curated subset of FMP + FRED data for frontend dashboard charts. It's built once in `node_deep_dive` from the raw FMP fetch (8 quarters of income/balance/cashflow, profile, DCF, estimates, key-metrics-ttm, financial-growth, and 1-year daily OHLCV). Valuation ratios (PE, EV/EBITDA, P/B, P/FCF, P/S, PEG) and return metrics (ROE, ROIC, ROA, interest coverage, dividend yield) come from the `key-metrics-ttm` endpoint. Technical indicators (SMA 9/20/50/100/200, RSI 14) are computed in `_build_technical_data()` and stored in `daily_prices`. FRED macro indicators are attached after the main build. The report API returns it under `phases.deep_dive.curated_financials`. The `deep_dive_start` SSE event also carries it. Note: `phases.deep_dive` in the report API is `{ categories: Record<str, CategoryOutput>, curated_financials: CuratedFinancials | null }` — not a flat record.

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

### SEC EDGAR filing pipeline (read this before touching `backend/app/services/edgar*` or `supply_chain.py`)

Four-phase pipeline for extracting and consuming SEC filing narrative. All on-demand — no automatic trigger during pipeline runs.

**Phase A — Filing section extraction** (`services/edgar_sections_ingest.py` + `services/edgar_html.py`):
- `POST /api/filings/ingest/{ticker}` pulls the latest 10-K, 10-Q, and DEF 14A from EDGAR, extracts Item 1 Business, Item 1A Risk Factors, Item 7 MD&A (10-K) / Item 2 MD&A (10-Q), and DEF 14A Governance via BeautifulSoup.
- Strips inline XBRL (`ix:hidden` dropped, `ix:nonFraction`/`ix:nonNumeric` unwrapped to displayed value). Heading regex anchored to line-start (MULTILINE) for MD&A and Item 1 Business to avoid matching in-body cross-references.
- Full text stored in `filing_sections` table; prompt builders truncate to 5K chars per section via `FILING_EXCERPT_BUDGET_CHARS`.
- Idempotent on `(filing_id, section_key)`.

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
- `GET /api/relationships/graph/{ticker}?direction=out|in|both` returns `{root_ticker, nodes[], edges[], summary}`. 1-hop depth. Nodes identified by CIK (resolved) or normalized name (unresolved). `tracked` flag from theme seed_tickers.
- `POST /api/relationships/reconcile` flips `confirmed_bilateral=true` on reciprocal pairs (customer↔supplier, partner↔partner, competitor↔competitor, licensor↔licensee, distributor↔reseller, joint_venture↔joint_venture).
- Frontend: `SupplyChainEcosystem` card in the deep-dive dashboard (after Business Quality). Groups counterparties by type, shows verbatim quotes, bilateral badges, tracker-links.

Database tables (all in `models/filing.py`):
- `filings` — one row per accession_number (10-K, 10-Q, DEF 14A, etc.)
- `xbrl_facts` — XBRL numeric facts (RPO, debt maturity, concentration, credit)
- `filing_sections` — extracted narrative text per section per filing
- `relationships` — LLM-extracted counterparty relationships
- `counterparty_aliases` — normalized name → canonical CIK/ticker resolution

### Import conventions

Backend uses **absolute imports rooted at project root**: `from backend.app.config import get_settings`. That's why uvicorn must be launched from project root. `backend/migrations/env.py` also imports from `backend.app.*`, so Alembic commands need project root on `PYTHONPATH` (running `alembic` from inside `backend/` works if you've activated the venv and `pip install -e .`'d — otherwise use `PYTHONPATH=.. alembic ...`).

### Frontend layout

- `app/` — App Router pages: `/` (themes), `/theme/[id]`, `/filings` (SEC filing extraction + curation queue), `/library`, `/pipeline/new`, `/pipeline/[runId]` (unified research page — handles both live streaming and completed reports). `/report/[runId]` redirects here.
- `lib/api.ts` — **every** backend call goes through the typed client here. Types mirror backend Pydantic/dataclass shapes; if you change a backend response, update this file or TS will silently accept stale shapes at the fetch boundary.
- `components/` — presentational pieces (`Nav`, `ScoreRing`, `SourceBadge`, `VelocityBadge`)
- `components/filings/` — `ThemeFilingsPanel`, `TickerFilingsCard`, `SectionReader` (modal), `CurationPanel` (counterparty resolution queue)
- `components/deep-dive/` — 30+ component module for the financial dashboard: `DeepDiveDashboard` orchestrator (receives `ticker` prop for supply-chain card), `SectionNav` (sticky horizontal scroll-spy nav with per-section pills), `ReportHeader` (company identity + verdict + metrics + radar), `OverviewBanner` (radar + metrics + score bar), `VelocitySparkline` (X signal badge), `sections/` (9 category sections + CrossCategoryCorrelation + `SupplyChainEcosystem`), `charts/` (Recharts bar/line/trend + lightweight-charts candlestick), `panels/` (AI companion + findings table), `skeleton/` (loading placeholders)
- Path alias: `@/*` → project root. Tailwind v4 via `@tailwindcss/postcss`.
- Chart libraries: **Recharts** (bar, line, radar charts) and **lightweight-charts** (TradingView candlestick + RSI).

### Deep-dive data routing

`_fmt_fundamentals()` in `graph/nodes.py` builds the data payload every category receives. It includes: company profile, valuation ratios (PE, EV/EBITDA, P/B, P/FCF, P/S, PEG), return metrics (ROE, ROIC, ROA, interest coverage), 8 quarters of income statement trends with YoY growth, balance sheet with ST/LT debt structure, cash flow with SBC, DCF valuation, forward analyst estimates with earnings surprise, and historical growth rates. On top of that base payload, categories receive supplementary data via routing tables:

- **Transcript routing** (`TRANSCRIPT_ROUTING` in `nodes.py`): Management & Governance (all 5 passes), Business Quality (pass3, pass5), Growth & Earnings (pass1, pass4, pass6), Sentiment & Narrative (pass3, pass5), Risk Assessment (pass1, pass4), Future Durability (pass1, pass5).
- **Macro routing** (`MACRO_ROUTING`): Macro & Regime (all 9 FRED series), Risk Assessment (all 9), Future Durability (5 series), Financial Health (rates + yield curve).

- **Filing excerpt routing** (`FILING_EXCERPT_ROUTING` in `nodes.py`): Business Quality (Item 1), Risk Assessment (Item 1A), Growth & Earnings (Item 7 + Item 2), Future Durability (Item 7 + Item 1), Management & Governance (DEF 14A). Truncated to `FILING_EXCERPT_BUDGET_CHARS` (5000) per section.
- **EDGAR XBRL routing** (`EDGAR_ROUTING`): Growth & Earnings (RPO), Future Durability (RPO), Financial Health (debt maturity + credit), Risk Assessment (debt maturity + concentration + credit), Business Quality (concentration).

The deep dive fetches 10 FMP endpoints in parallel: income statement (8Q), balance sheet (8Q), cash flow (8Q), profile, DCF, analyst estimates (8Q), historical price (1Y), earnings transcript, key-metrics-ttm, and financial-growth (8Q). It also pulls ingested filing sections (if any) via `PipelineService._fetch_filing_sections()` and XBRL facts via `_fetch_edgar_facts()`.

## State-of-repo notes

Design-phase artifacts (`skills/due-diligence/`, `TODO.md`, `BACKLOG.md`) have been cleaned up. Active specs live in `docs/superpowers/specs/`. If you need old plans or the due-diligence methodology, recover from git history (`git log --all --diff-filter=D -- docs/`).
