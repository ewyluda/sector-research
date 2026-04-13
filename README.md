# Sector Research

A personal stock research application combining structured equity data with social signal to surface investment ideas and run them through a structured due diligence pipeline.

---

## What It Does

Two core workflows:

**Discovery** — Open a curated investment theme (e.g., "AI Power Infrastructure") and see every company in that space ranked by signal strength. FMP screener data and X mention velocity surface unknown players alongside known ones. Combined signal score = 40% X velocity + 40% FMP fundamental quality + 20% discovery score.

**Pipeline** — Push any ticker through a 6-phase due diligence framework powered by LangGraph. AI automation on each phase, human-in-the-loop validation at three interrupt gates, citations on every data point. Exports to Obsidian markdown when complete. Every phase produces structured JSON output rendered as purpose-built dashboard components.

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
| Data: fundamentals | FMP API (ultimate tier) — financials, key metrics TTM, growth rates, DCF, estimates, transcripts |
| Data: macro | FRED API — 9 economic series (fed funds, treasuries, CPI, unemployment, GDP, M2, payrolls) |
| Data: social signal | X API v2 |

---

## Architecture

```
┌─────────────────────────────────────────┐
│            Next.js 16 Frontend          │
│  Theme Dashboard │ Pipeline Runner │ Library │
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
│          │ FMP · X · FRED│             │
│          └───────┬───────┘             │
└──────────────────┼─────────────────────┘
                   │
┌──────────────────▼─────────────────────┐
│              PostgreSQL                 │
│  themes · research_runs · citations     │
│  signals · watchlist                    │
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
```

No auth system — personal local tool.

---

## Key Files

| File | Purpose |
|---|---|
| `CLAUDE.md` | Claude Code guidance for this repo |
| `backend/app/models/phase_schemas.py` | All Pydantic schemas for structured phase outputs |
| `backend/app/graph/pipeline.py` | LangGraph StateGraph definition |
| `backend/app/graph/nodes.py` | Phase node implementations |
| `backend/app/graph/prompts.py` | All LLM prompts |
| `frontend/lib/api.ts` | Typed API client + all TypeScript interfaces |
| `frontend/components/deep-dive/` | 28-component financial dashboard module (charts, sections, panels, skeletons) |
| `BACKLOG.md` | Prioritized backlog of pending features and improvements |
