# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

A personal stock research application — currently in the **design phase**. The repo contains:

1. **Design spec** (`docs/superpowers/specs/2026-04-10-sector-research-app-design.md`) — the authoritative source for the planned architecture, data model, UI pages, and LangGraph pipeline. Read this before any implementation work.
2. **Due diligence skills** (`skills/due-diligence/`) — the investment research methodology that the app's LangGraph pipeline will execute. These are loaded as system context into LLM phases during a research run.

No application code exists yet.

---

## Planned Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router) |
| Backend | FastAPI (Python) |
| Agent orchestration | LangGraph |
| Database | PostgreSQL |
| LLM (heavy) | Claude Sonnet (`claude-sonnet-4-6`) |
| LLM (light) | Claude Haiku (`claude-haiku-4-5-20251001`) |
| Data: fundamentals | FMP API (ultimate tier) |
| Data: social signal | X API v2 |

Environment variables go in a single `.env` at project root: `FMP_API_KEY`, `X_BEARER_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL`.

---

## Skills Framework Architecture

The `skills/due-diligence/` tree is a **methodology library** — not executable code. It defines the analysis the LLM agents will perform. Structure:

```
skills/due-diligence/
  framework.md              ← Master 6-phase pipeline; read this first
  scoring-methodology.md    ← Score definitions, weighting math, traffic-light system
  platform-mapping.md       ← Which skills are Full/Partial/Manual automation
  categories/               ← 11 analytical categories (01–11), each with sub-skills
  workflows/                ← 5 pre-built workflows (quick-screen, deep-dive, etc.)
```

### The 6-Phase Pipeline

Phases run sequentially with human interrupts at gates 1, 3, and 5:

1. **Screening** (Phase 1+2, combined as `quick_screen` node) — GO / WATCHLIST / PASS gate
2. **Deep Dive** (Phase 3, `deep_dive` node) — 9 categories run in parallel as a subgraph
3. **Thesis Construction** (Phase 4)
4. **Risk Stress-Test** (Phase 5) — can loop back to Phase 3 for specific categories if risk/reward < 2:1
5. **Position & Monitor** (Phase 6)

### LangGraph State

The `ResearchState` TypedDict (defined in the spec) carries: `ticker`, `theme`, `phase`, `phase_outputs`, `citations`, `scores`, `conviction_score`, `thesis_status`, `human_feedback`, `loop_context`. State is persisted to PostgreSQL at every interrupt so runs can be paused and resumed.

### Citation Model

Every data client method returns `(data, Citation)`. Citations are never optional. The `Citation` dataclass carries: `value`, `metric`, `source_name`, `source_url`, `tier` (1 = authoritative, 2 = qualitative), `retrieved_at`. All citations accumulate in state and render as inline footnotes in the UI.

### LLM Assignment by Phase

- Phases 1–2: Claude Haiku (scoring, summarization)
- Phase 3: Claude Sonnet per category (parallel)
- Phases 4–5: Claude Sonnet
- Phase 6: Claude Haiku (structured output)

Each phase loads the corresponding skill file from `skills/due-diligence/` as system context. Files >~2000 tokens use Anthropic prompt caching.

---

## Key Design Decisions

- **No auth** — personal local tool only
- **FMP caching TTLs**: quote/price 5 min, fundamentals 24 hr, options 15 min, transcripts 7 days
- **X API signals run on a schedule** (default every 4 hours) due to rate limits — not on-demand
- **Discovery signal score** formula: `(mention count / total theme mentions) × 1.5 if not in seed list, × 1.0 if in seed list`
- **Combined signal score** default weights: 40% X velocity, 40% FMP fundamental quality, 20% discovery score — configurable per theme
- **Conviction score** weights: Business Quality 20%, Financial Health 15%, Growth 15%, Management 10%, Technical 5%, Macro 5%, Sentiment 5%, Risk (inverted) 10%, Future Durability 15%
- **Export target**: Obsidian markdown (`01_Projects/` or `02_Areas/Investing-Portfolio/`)

---

## Database Schema (PostgreSQL)

| Table | Purpose |
|---|---|
| `themes` | Curated investment themes with seed tickers, screener criteria, X search terms |
| `research_runs` | Pipeline runs with full `state` jsonb column |
| `citations` | All citations from all runs |
| `signals` | Cached X API signal outputs per ticker/theme |
| `watchlist` | Tickers parked at interrupt gates |
