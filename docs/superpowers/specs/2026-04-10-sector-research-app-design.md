# Sector Research App — Design Spec

**Date:** 2026-04-10
**Author:** Eric Wyluda
**Status:** Approved

---

## Overview

A personal stock research app that combines structured equity data (FMP ultimate tier) with X API social signal to power two core workflows:

1. **Discovery** — drill into a curated theme (e.g., "AI Power Infrastructure"), see every company in that space ranked by signal strength, surface unknown players dynamically
2. **Pipeline** — push a ticker through a structured 6-phase due diligence framework, with AI automation on each phase, human-in-the-loop validation at key gates, and citations on every data point

The app is a personal tool — no auth system, runs locally on Mac Mini or MacBook. Output exports cleanly to Obsidian markdown.

---

## Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Frontend | Next.js 15 (App Router) | Dashboard-style multi-page UI, SSE streaming support |
| Backend | FastAPI (Python) | Familiar, async, good for streaming LangGraph output |
| Agent orchestration | LangGraph | Native support for stateful graphs, parallel subgraphs, human-in-the-loop interrupts, conditional loops |
| Database | PostgreSQL | Persistent research runs, citations, signals, themes |
| LLM (heavy) | Claude Sonnet (claude-sonnet-4-6) | Deep dive analysis, thesis construction, risk stress-test |
| LLM (light) | Claude Haiku (claude-haiku-4-5-20251001) | X narrative summarization, quick-screen scoring |
| Data: fundamentals | FMP API (ultimate tier) | Trading data, financials, options, transcripts, DCF, analyst forecasts |
| Data: social signal | X API v2 | Mention velocity, community discovery, narrative shift |

---

## Architecture

```
┌─────────────────────────────────────────┐
│            Next.js 15 Frontend          │
│  Theme Dashboard │ Pipeline Runner │ Library │
└────────────────────┬────────────────────┘
                     │ HTTP / SSE streaming
┌────────────────────▼────────────────────┐
│              FastAPI Backend            │
│  ┌─────────────┐  ┌────────────────┐   │
│  │  Discovery  │  │ LangGraph      │   │
│  │  Engine     │  │ Pipeline       │   │
│  │  (FMP+X)    │  │ (6-phase DD)   │   │
│  └──────┬──────┘  └───────┬────────┘   │
│         └────────┬─────────┘           │
│          ┌───────▼───────┐             │
│          │  Data Clients │             │
│          │  FMP · X API  │             │
│          └───────┬───────┘             │
└──────────────────┼─────────────────────┘
                   │
┌──────────────────▼─────────────────────┐
│              PostgreSQL                 │
│  themes · research_runs · citations     │
│  signals · watchlist                    │
└─────────────────────────────────────────┘
```

The Discovery Engine and LangGraph Pipeline are independent subsystems sharing data clients and the database. Discovery can run without triggering the pipeline. The pipeline only starts on explicit user action.

---

## Section 1: Discovery Engine

### Theme Management

Each theme is a database record containing:
- Display name and description
- Seed tickers (companies already known to belong to this theme)
- FMP screener criteria (sector, sub-industry, market cap range, exchange)
- X search terms (hashtags, $tickers, product names, keywords)

Themes are fully editable from the UI — no code changes required to add or modify a theme.

### Dynamic Discovery

When a theme is opened, two parallel discovery passes run:

**FMP Screener Pass**
- Queries FMP using the theme's screener criteria
- Returns matching companies with: name, ticker, market cap, sector, P/E, revenue growth, gross margin, ROIC
- Surfaces structurally-relevant companies not in the seed list

**X Signal Pass**
- Searches X for the theme's keywords over rolling 7-day and 30-day windows
- Computes three signals per mentioned company:
  - **Velocity** — 7d vs 30d mention ratio (accelerating / stable / decelerating)
  - **Narrative** — Claude Haiku summary of post clusters (what people are actually saying)
  - **Discovery score** — (mention count within theme keyword search results / total theme mentions) × 1.5 if ticker is not in seed list, × 1.0 if it is. Higher score = more prominent in theme discussion but less known to you.
- Runs on a schedule (not on-demand) due to X API rate limits; results cached in `signals` table

### Company Signal Card

Each company in a theme view shows:
- Name, ticker, market cap, sector/sub-industry
- FMP health snapshot: 3–4 key metrics with Tier 1 source tags
- X signal badge: velocity trend indicator + narrative one-liner (Tier 2 tag)
- Citation on every metric (source name + link, Tier 1 or Tier 2)
- "Run Quick Screen" button — the bridge to the pipeline
- Research library status: last pipeline result if previously researched

The list is sortable by: X velocity, fundamental quality score, market cap, or combined signal score. Combined signal score default weighting: 40% X velocity, 40% FMP fundamental quality (ROIC vs WACC + margin profile), 20% discovery score. Weights are configurable per theme.

---

## Section 2: LangGraph Pipeline

Maps directly to the 6-phase due diligence framework in `skills/due-diligence/framework.md`.

### Graph Structure

```
START
  │
  ▼
[quick_screen]          ← Phases 1+2: auto-runs, pulls FMP data, scores dimensions
  │
  ▼
⚡ INTERRUPT             ← Review: GO / WATCHLIST / PASS
  │ (GO only)
  ▼
[deep_dive]             ← Phase 3: 9 categories run in parallel subgraph
  │
  ▼
⚡ INTERRUPT             ← Review category reports, flag any for re-run
  │
  ▼
[thesis_construction]   ← Phase 4: synthesizes Phase 3 outputs
  │
  ▼
[risk_stress_test]      ← Phase 5: stress-tests thesis
  │
  ├──(risk/reward < 2:1)──► [deep_dive] ← loops back; risk_stress_test node outputs which specific categories (by name) need deeper investigation, stored in loop_context
  │
  ▼
⚡ INTERRUPT             ← Review thesis + risk register
  │ (approved)
  ▼
[position_monitor]      ← Phase 6: entry zones, sizing, stops, monitoring cadence
  │
  ▼
END
```

### State

Persisted to PostgreSQL at every interrupt so runs can be paused and resumed:

```python
class ResearchState(TypedDict):
    ticker: str
    theme: str
    phase: str                    # current phase name
    phase_outputs: dict           # keyed by phase name, accumulated
    citations: list[Citation]     # all sources used, accumulated across phases
    scores: dict                  # per-category composite scores (0-100)
    conviction_score: int         # 0-100 overall
    thesis_status: str            # ON TRACK / DRIFTING / BROKEN
    human_feedback: dict          # notes added at each interrupt
    loop_context: dict | None     # set when Phase 5 loops back to Phase 3
```

### Citation Model

Every data client method returns `(data, Citation)`. Citations are never optional.

```python
@dataclass
class Citation:
    value: str | float
    metric: str           # e.g., "Revenue Growth YoY"
    source_name: str      # e.g., "FMP /income-statement"
    source_url: str       # direct link to endpoint or SEC filing
    tier: int             # 1 = authoritative, 2 = qualitative signal only
    retrieved_at: datetime
```

Citations accumulate in state as the graph runs. In the UI, every number renders as a superscript footnote linked to its source. Tier 2 sources are visually distinct from Tier 1. The full citation list appears at the bottom of each phase output.

### Human Interrupt UX

At each interrupt, the user sees the current phase output with all citations inline and three actions:
- **Approve** — advance to next phase
- **Flag + notes** — add a comment and advance (flag travels with state)
- **Stop** — archive the run as WATCHLIST or PASS with a reason

When Phase 5 triggers a loop back to Phase 3, the app shows a notification: which gate failed (risk/reward < 2:1), which specific categories are being re-investigated, and why. The loop does not re-run all 9 categories — only the flagged ones.

### LLM Strategy

- **Phase 1–2 (quick_screen)**: Claude Haiku for scoring and summarization
- **Phase 3 (deep_dive)**: Claude Sonnet for each category analysis, running in parallel
- **Phase 4–5 (thesis, risk)**: Claude Sonnet
- **Phase 6 (position)**: Claude Haiku (structured output, lower reasoning load)

All phase prompts load the relevant skill file from `skills/due-diligence/` as system context. Files longer than ~2000 tokens use Anthropic prompt caching to avoid re-tokenizing on repeat runs.

---

## Section 3: Frontend (Next.js 15)

Five pages with clear single responsibilities.

### Page 1 — Theme Dashboard (/)
Home screen. Grid of curated themes, each card showing:
- Theme name + description
- Top 3 companies by combined signal score this week
- X velocity summary ("3 tickers accelerating")
- Last refreshed timestamp
- "Open Theme" button

### Page 2 — Theme Detail (/theme/[id])
Two-panel layout:
- **Left panel**: sortable/filterable company list with signal cards. Filter by velocity, market cap, sector, researched vs new.
- **Right panel**: expanded company view with raw X post samples, full FMP metric breakdown, and "Run Quick Screen" button.

### Page 3 — Pipeline Runner (/pipeline/[runId])
Main research workspace:
- **Left rail**: phase progress tracker (steps 1–6), current phase highlighted, completed phases checkmarked, interrupt phases show feedback note
- **Main panel**: current phase output with inline citation footnotes, streaming token-by-token while agent runs
- **Action bar** (bottom): Approve / Flag + notes / Stop — disabled while running, enabled at interrupts

### Page 4 — Research Library (/library)
Table of all research runs. Columns: ticker, theme, date started, phase reached, conviction score (0-100), thesis status (traffic light badge), last action. Click any row to resume (if in-progress) or view full report (if complete).

### Page 5 — Full Report (/report/[runId])
Read-only view of a completed run. All phase outputs concatenated into a structured document. Full citation list at bottom. Export to markdown button — output formatted to drop directly into Obsidian vault (`01_Projects/` or `02_Areas/Investing-Portfolio/`).

---

## Section 4: Data Layer

### Database Schema (PostgreSQL)

| Table | Key Columns |
|---|---|
| `themes` | id, name, description, seed_tickers (jsonb), screener_criteria (jsonb), x_search_terms (jsonb), created_at, updated_at |
| `research_runs` | id, ticker, theme_id, phase, status, state (jsonb), created_at, updated_at |
| `citations` | id, run_id, metric, value, source_name, source_url, tier, retrieved_at |
| `signals` | id, ticker, theme_id, signal_type, value (jsonb), computed_at |
| `watchlist` | id, ticker, theme_id, trigger_condition, added_at, run_id (nullable) |

### FMP Client

One Python module. One method per data type: `get_screener()`, `get_income_statement()`, `get_balance_sheet()`, `get_cash_flow()`, `get_dcf()`, `get_options_flow()`, `get_earnings_transcript()`, `get_analyst_estimates()`. Every method returns `tuple[data, Citation]`.

Response caching with TTL:
- Quote/price data: 5 minutes
- Fundamental data: 24 hours
- Options data: 15 minutes
- Transcripts/filings: 7 days (rarely changes)

### X API Client

Searches by ticker symbol, company name, and theme keywords. Returns posts with engagement metrics. Three computed signals per ticker (velocity, discovery, narrative). Runs on a schedule (configurable, default: every 4 hours) and writes results to the `signals` table. Rate limit handling via token bucket.

### Environment

Single `.env` file at project root:
```
FMP_API_KEY=
X_BEARER_TOKEN=
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql://...
```

No auth system. Personal local tool.

---

## Out of Scope (v1)

- Multi-user support / auth
- Mobile layout
- Automated position alerts or monitoring cadence execution
- Integration with the existing multi-agent-market-research system
- Real-time price streaming

These can be added later without architectural changes.

---

## Key Files Reference

- Due diligence framework: `skills/due-diligence/framework.md`
- Quick screen workflow: `skills/due-diligence/workflows/quick-screen.md`
- Deep dive workflow: `skills/due-diligence/workflows/deep-dive.md`
- Scoring methodology: `skills/due-diligence/scoring-methodology.md`
