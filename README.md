# Sector Research

A personal stock research application combining structured equity data with social signal to surface investment ideas and run them through a structured due diligence pipeline.

---

## What It Does

Three core workflows:

**Discovery** — Open a curated investment theme (e.g., "AI Power Infrastructure") and see every company in that space ranked by signal strength. FMP screener data and X mention velocity surface unknown players alongside known ones. Combined signal score = 40% X velocity + 40% FMP fundamental quality + 20% discovery score.

**Pipeline** — Push any ticker through a 6-phase due diligence framework powered by LangGraph. AI automation on each phase, human-in-the-loop validation at three interrupt gates, citations on every data point. Exports to Obsidian markdown when complete. Every phase produces structured JSON output rendered as purpose-built dashboard components.

**Filings** — Extract and analyze SEC EDGAR 10-K / 10-Q / DEF 14A narrative sections. Haiku-powered relationship extraction surfaces customers, suppliers, partners, competitors, and concentration risks from filings. Counterparty names are resolved to canonical tickers via fuzzy matching against the EDGAR universe (~10K entities). Results power a supply-chain graph card in the deep-dive dashboard, a curation queue for manual resolution, and the Business Quality / Risk Assessment / Future Durability deep-dive prompts — the LLM cites named counterparties as anchors rather than re-quoting filing text. One-click fan-out walks a whole theme's seed tickers through ingest → extract → resolve in sequence.

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
│  Theme Dashboard │ Filings │ Pipeline │ Library │
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
└─────────────────────────────────────────┘
```

---

## The Pipeline

```
START
  │
  ▼
[quick_screen]          ← Phases 1+2: FMP data pull + scoring
  │
  ▼
⚡ INTERRUPT             ← GO / WATCHLIST / PASS
  │ (GO)
  ▼
[deep_dive]             ← Phase 3: 9 categories in parallel
  │
  ▼
⚡ INTERRUPT             ← Review category reports
  │
  ▼
[thesis_construction]   ← Phase 4
  │
  ▼
[risk_stress_test]      ← Phase 5
  │
  ├──(risk/reward < 2:1)──► [deep_dive] ← targeted loop back
  │
  ▼
⚡ INTERRUPT             ← Approve thesis + risk register
  │
  ▼
[position_monitor]      ← Phase 6: entry zones, sizing, stops
  │
  ▼
END
```

Phases 1–2 use Claude Haiku. Phases 3–5 use Claude Sonnet. Phase 6 uses Claude Haiku. Every data point carries a `Citation` — source name, URL, tier (1 = authoritative, 2 = qualitative), and retrieval timestamp.

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
| `frontend/lib/api.ts` | Typed API client + all TypeScript interfaces |
| `frontend/components/deep-dive/` | 30+ component financial dashboard (charts, sections, panels, skeletons) |
| `frontend/components/filings/` | Filing ingest, section reader, curation panel |
