# Sector Research

A personal stock research application combining structured equity data with social signal to surface investment ideas and run them through a structured due diligence pipeline.

---

## What It Does

Five core workflows:

**Discovery** — Open a curated investment theme (e.g., "AI Power Infrastructure") and see every company in that space ranked by signal strength. FMP screener data and X mention velocity surface unknown players alongside known ones. Combined signal score = 40% X velocity + 40% FMP fundamental quality + 20% discovery score.

**Pipeline** — Push any ticker through a 6-phase due diligence framework powered by LangGraph. Phases 1-5 (quick_screen → deep_dive → thesis_construction → risk_stress_test) run continuously after `POST /api/runs`; risk_stress_test can loop back to deep_dive when `loop_required` is set (capped at 2 loops). Phase 6 (position_monitor) is the only manually-gated step — triggered via `POST /api/runs/{id}/advance` once the prior phases complete. Citations on every data point. Exports to Obsidian markdown when complete. Every phase produces structured JSON output rendered as purpose-built dashboard components.

**Filings** — Extract and analyze SEC EDGAR 10-K / 10-Q / DEF 14A narrative sections. Haiku-powered relationship extraction surfaces customers, suppliers, partners, competitors, and concentration risks from filings. Counterparty names are resolved to canonical tickers via fuzzy matching against the EDGAR universe (~10K entities). Results power a supply-chain graph card in the deep-dive dashboard, a curation queue for manual resolution, and the Business Quality / Risk Assessment / Future Durability deep-dive prompts — the LLM cites named counterparties as anchors rather than re-quoting filing text. One-click fan-out walks a whole theme's seed tickers through ingest → extract → resolve in sequence.

**Model** — Editable 5-year financial model per ticker, AI-seeded from the latest completed research run. Sonnet emits forecast drivers, the balancing engine recomputes the full 3-statement P&L / BS / CF on every cell edit (plug into `retained_earnings` keeps A=L+E), versions persist to `ticker_models` with a single working draft per ticker. The reverse-DCF tab solves implied revenue growth / EBIT margin / terminal multiple from the live FMP quote, computes the implied IRR, and renders three 21×21 sensitivity heatmaps plus a thesis-vs-priced-in summary. Cell edits, history diff (cell-path-keyed), and a what-if scratch panel (illustrative sliders).

**Status Board** — Live tracker of every active thesis across all themes. Aggregates the latest completed run per `(ticker, theme)` with health badges (Healthy / Imminent / Stale / Triggered / Broken), nearest-catalyst proximity, and a kill-criteria summary you can toggle armed/triggered inline. Polls every 60s while the tab is visible. The post-thesis fleet-management view — what to pay attention to and what's quietly aging out. Companion `/catalysts` and `/questions` pages surface the calendar and open-question log feeding the same data.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind v4 + Recharts + lightweight-charts |
| Backend | FastAPI + async SQLAlchemy |
| Agent orchestration | LangGraph |
| Database | PostgreSQL |
| LLM (heavy) | Claude Sonnet (`claude-sonnet-4-6`) |
| LLM (light) | Claude Haiku (`claude-haiku-4-5-20251001`) |
| Data: fundamentals | FMP API (ultimate tier) — financials, key metrics TTM, growth rates, DCF, estimates, transcripts, analyst grades, insider trading |
| Data: macro | FRED API — 9 economic series (fed funds, treasuries, CPI, unemployment, GDP, M2, payrolls) |
| Data: SEC filings | SEC EDGAR — 10-K / 10-Q / DEF 14A narrative sections, XBRL company facts |
| Data: social signal | X API v2 |
| Fuzzy matching | RapidFuzz — counterparty name → ticker resolution |
| HTML parsing | BeautifulSoup + lxml — inline XBRL stripping + section extraction |

---

## Architecture

```
┌─────────────────────────────────────────┐
│            Next.js 16 Frontend          │
│  Themes │ Filings │ Pipeline │ Model │ Library │
└────────────────────┬────────────────────┘
                     │ HTTP / SSE streaming
┌────────────────────▼────────────────────┐
│              FastAPI Backend            │
│  ┌─────────────┐  ┌────────────────┐   │
│  │  Discovery  │  │  LangGraph     │   │
│  │  Engine     │  │  Pipeline      │   │
│  │  (FMP + X)  │  │  (6-phase DD)  │   │
│  └──────┬──────┘  └───────┬────────┘   │
│         └────────┬─────────┘           │
│          ┌───────▼───────┐             │
│          │  Data Clients │             │
│          │FMP·X·FRED·EDGAR│            │
│          └───────┬───────┘             │
└──────────────────┼─────────────────────┘
                   │
┌──────────────────▼─────────────────────┐
│              PostgreSQL                 │
│  themes · research_runs · citations     │
│  signals · watchlist                    │
│  filings · xbrl_facts · filing_sections │
│  relationships · counterparty_aliases   │
│  ticker_models · ticker_model_drafts    │
└─────────────────────────────────────────┘
```

---

## The Pipeline

```
START (POST /api/runs)
  │
  ▼
[quick_screen]          ← Phase 1: FMP data pull + scoring (Haiku)
  │
  ▼
[deep_dive]             ← Phase 2: 9 categories in parallel (Sonnet)
  │
  ▼
[thesis_construction]   ← Phase 3 (Sonnet)
  │
  ▼
[risk_stress_test]      ← Phase 4 (Sonnet)
  │
  ├──(loop_required & loop_count ≤ 2)──► [deep_dive] ← targeted loop back
  │
  ▼
COMPLETED  ← phases 1-5 run continuously, no interrupts
  │
  ▼
⚡ MANUAL ADVANCE       ← POST /api/runs/{id}/advance (action="approve")
  │
  ▼
[position_monitor]      ← Phase 6: entry zones, sizing, stops (Haiku)
  │
  ▼
END
```

Every data point carries a `Citation` — source name, URL, tier (1 = authoritative, 2 = qualitative), and retrieval timestamp.

---

## SEC EDGAR Filings Pipeline

Separate on-demand pipeline for extracting business intelligence from SEC filings. All endpoints manual-trigger, no automatic inline execution during pipeline runs.

```
POST /api/filings/ingest/{ticker}
  ↓  Fetches latest 10-K, 10-Q, DEF 14A from EDGAR
  ↓  Extracts narrative sections (Item 1, 1A, 7, DEF 14A governance)
  ↓  Strips inline XBRL, persists to filing_sections

POST /api/filings/extract-relationships/{ticker}
  ↓  One Haiku call per section (~15K chars each)
  ↓  Extracts: counterparty_name, relationship_type, magnitude_pct, verbatim_quote
  ↓  Persists to relationships table (idempotent per section)

POST /api/relationships/resolve/{ticker}
  ↓  Normalizes names (strips Inc/Corp/LLC/Holdings etc.)
  ↓  Exact match → auto-resolve
  ↓  RapidFuzz ≥ 95 → auto-resolve
  ↓  80-94 → curation queue
  ↓  Persists to counterparty_aliases, backfills relationships

GET /api/relationships/graph/{ticker}?direction=both
  ↓  Returns {nodes, edges, summary} for the supply-chain card

POST /api/relationships/reconcile
  ↓  Finds reciprocal pairs (customer↔supplier, etc.)
  ↓  Flips confirmed_bilateral on both sides

POST /api/themes/{id}/relationships/fanout
POST /api/tickers/{ticker}/relationships/fanout
  ↓  Kicks off a background FanoutService task that chains
  ↓    ingest → extract → resolve over every seed ticker
  ↓    (serial, one EdgarClient reused, per-stage DB commit)
  ↓  Returns { fanout_id, status, total_tickers, ... } immediately.

GET /api/fanouts/{fanout_id}
  ↓  Poll for progress: { status, current_ticker, current_stage,
  ↓    completed_tickers, errors[] }. Frontend polls at 3s intervals
  ↓    from the "Fan out" buttons on /filings.
```

The Supply Chain & Ecosystem card in the deep-dive dashboard renders the graph data — counterparties grouped by type with verbatim SEC quotes, bilateral confirmation badges, and tracker-links for companies in your discovery universe.

Beyond the card, the resolved counterparty list is routed into the Business Quality, Risk Assessment, and Future Durability deep-dive prompts via `RELATIONSHIP_ROUTING` in `graph/nodes.py`. The prompt slot lists outbound relationships grouped by type (plus inbound mentions from other tickers that named this one in their own filings), and the framing tells the LLM to cite entities by name and NOT to re-quote filing excerpts for them — making the supply-chain data an authoritative index rather than material to restate.

---

## Financial Model + Reverse DCF

Per-ticker editable 3-statement model with versioning and a reverse-DCF engine. Lives at `/model/{ticker}`. All on-demand — no automatic trigger from the LangGraph pipeline.

```
POST /api/models/{ticker}/initialize?force=
  ↓  Loads latest completed research_run + risk-free rate (FRED DGS10)
  ↓  Sonnet emits forecast drivers (annual, cloned to quarterly)
  ↓  Seeds historical cells from CuratedFinancials, runs recompute()
  ↓  Persists v1 to ticker_models (idempotent unless force=true)

GET /api/models/{ticker}
  ↓  Returns latest_version + draft (or both null)

PUT /api/models/{ticker}/draft
  ↓  Apply one cell edit (cell_path = drivers.<period>.<key>
  ↓    | <stmt>.<line>.<period> | assumptions.<key>)
  ↓  Recompute: P&L → CF → BS rollforward (plug into retained_earnings)
  ↓  Persist into ticker_model_drafts (one row per ticker)
  ↓  422 on bad cell_path, 409 on imbalance > tolerance

POST /api/models/{ticker}/save
  ↓  Promote draft → next ticker_models version, delete draft

GET /api/models/{ticker}/reverse-dcf?price=&from_draft=
  ↓  Single payload with four blocks:
  ↓    implied_drivers (3 scalar bisection solves: revenue_growth_pct,
  ↓      ebit_margin_pct, terminal_multiple)
  ↓    implied_irr (solve discount rate that produces target_per_share)
  ↓    sensitivity_grids (3 × 21×21 grids for each driver pair)
  ↓    thesis_vs_priced_in (delta between user-saved drivers and implieds)
  ↓  price defaults to live FMP /quote via shared singleton

GET /api/models/{ticker}/versions
GET /api/models/{ticker}/versions/{version}/diff?against=
  ↓  Cell-path-keyed JSON diff for the history viewer
```

Frontend has three hash-routed tabs: `#forecast` (the spreadsheet + driver panel + formula bar), `#reverse-dcf` (IRR + thesis-vs-priced + heatmaps + what-if sliders), `#history` (version list + diff viewer). The deep-dive `ReportHeader` carries a small Model badge that links into `/model/{ticker}`.

---

### Structured Phase Outputs

Every pipeline phase produces validated JSON output via Pydantic schemas, parsed with a generic `parse_structured_output` function that handles LLM quirks (prose preamble, markdown fences). Each phase has a dedicated React dashboard component with prose fallback for old runs or parse failures.

| Phase | Schema | Dashboard |
|---|---|---|
| Quick Screen | `QuickScreenOutput` | Score ring, dimension table, thesis/risk callouts |
| Deep Dive (×9) | `DeepDiveCategoryOutput` | Scrollable financial dashboard: radar chart, headline metrics, score bar, per-category charts (Recharts bar/line/trend), 1Y candlestick chart with SMA/RSI (lightweight-charts), AI companion panels, sticky sidebar nav |
| Thesis | `ThesisOutput` | Conviction ring, bull/bear columns, catalyst timeline |
| Risk Stress-Test | `RiskStressTestOutput` | R/R ratio ring, risk register cards, loop-back footer |
| Position Monitor | `PositionMonitorOutput` | Entry zone, sizing, stop loss, monitoring schedule, exit conditions |

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 24+
- PostgreSQL

### Backend

```bash
# From project root
cd backend && python -m venv venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# Run migrations
cd backend && alembic upgrade head

# Dev server (run from project root for absolute imports)
cd ..
uvicorn backend.app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # Dev server on :3000
```

### Environment Variables

Single `.env` at project root:

```
FMP_API_KEY=
X_BEARER_TOKEN=
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql+asyncpg://...
DATABASE_URL_SYNC=postgresql://...
FRED_API_KEY=              # optional — macro data skipped if empty
```

No auth system — personal local tool.

---

## Key Files

| File | Purpose |
|---|---|
| `CLAUDE.md` | Claude Code guidance for this repo |
| `backend/app/models/phase_schemas.py` | All Pydantic schemas for structured phase outputs |
| `backend/app/models/filing.py` | Filing, FilingSection, Relationship, CounterpartyAlias ORM models |
| `backend/app/graph/pipeline.py` | LangGraph StateGraph definition |
| `backend/app/graph/nodes.py` | Phase node implementations + data routing tables |
| `backend/app/graph/prompts.py` | All LLM prompts |
| `backend/app/clients/edgar.py` | SEC EDGAR client (CIK lookup, company facts, filing fetch) |
| `backend/app/services/edgar_html.py` | BS4 section extractor (heading regex, XBRL stripping) |
| `backend/app/services/edgar_relationships.py` | Haiku relationship extraction service |
| `backend/app/services/counterparty_resolver.py` | Normalizer + RapidFuzz matcher + alias management |
| `backend/app/services/supply_chain.py` | Graph traversal + bilateral reconciliation |
| `backend/app/services/fanout.py` | FanoutService — orchestrates ingest → extract → resolve across a theme or a single ticker; in-memory status tracker wired through `app.state.fanout` |
| `backend/app/services/relationship_context.py` | Read-path query layer: builds the `CounterpartyContext` (outbound + inbound, grouped by type) consumed by the deep-dive prompt routing |
| `backend/app/api/fanouts.py` | Fan-out endpoints (theme, ticker, status polling) |
| `backend/app/models/model_state.py` | `ModelState` Pydantic + `ModelCell` (drivers/statements/assumptions) |
| `backend/app/services/model_baseline.py` | Sonnet-seeded baseline orchestrator (`build_baseline_state`, `initialize_or_get_model`) |
| `backend/app/services/model_balancing.py` | Pure recompute pipeline: P&L → CF → BS plug into `retained_earnings` |
| `backend/app/services/dcf.py` | DCF over forecast FCF + terminal value (Gordon growth or EV/EBITDA multiple) |
| `backend/app/services/reverse_dcf.py` | Bisection solvers + 21×21 sensitivity grids + thesis-vs-priced-in |
| `backend/app/services/model_diff.py` | Cell-path-keyed JSON diff between two `ModelState`s |
| `backend/app/api/models_api.py` | Model REST surface (`/api/models/{ticker}/...`) |
| `frontend/lib/api.ts` | Typed API client + all TypeScript interfaces |
| `frontend/components/deep-dive/` | 30+ component financial dashboard (charts, sections, panels, skeletons) |
| `frontend/components/filings/` | Filing ingest, section reader, curation panel |
| `frontend/components/model/` | Forecast grid, driver panel, formula bar, reverse-DCF panel, heatmaps, history diff |
