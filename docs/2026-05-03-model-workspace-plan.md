# Model Workspace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `sector-research` with a per-ticker, post-earnings *model workspace* — a recurring 5-step refresh loop (Update / Research / Validate / Challenge / Differentiate) that operates on already-thesised tickers. Adds a structured financial-model assembly layer (starting with accretion/dilution), versioned per-ticker model state with diffs, and per-cell audit trails. Harvests proven patterns from `stock-comparison` (implied solver, sensitivity grid, valuation bands, snapshot/export) and `multi-agent-market-research` (Investor Council, signal_contract_v2 envelope, calibration snapshots) without rebuilding them.

**Architecture decision:** Build into `sector-research`, not a new repo. Sector-research already owns the closest structural fit (Citation primitive, Postgres state, LangGraph + interrupts, structured Pydantic phase outputs, Obsidian export). MAMR's Investor Council is exposed as an HTTP service — kept in MAMR, called from sector-research. Stock-comparison's valuation logic is *ported* into sector-research, not consumed remotely (the valuation surface needs to live next to the model state). Shared `mam-data` package extraction is deferred until duplication is real.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, LangGraph, Pydantic, Anthropic SDK (Sonnet + Haiku), Next.js 16 + React 19 + Recharts + lightweight-charts, PostgreSQL 16

**Reference docs:**
- 13-Step Exoskeleton: `13-step-exoskeleton.md`
- Push-button workflows + 5-step model workspace: `13-step-exoskeleton.md` (Slides 23, 46)
- Sector-research design spec: `docs/superpowers/specs/2026-04-10-sector-research-app-design.md`
- MAMR Investor Council design: `01_Projects/Multi-Agent-Market-Research/Investor-Council-Design.md`
- Stock-comparison valuation: `https://github.com/ewyluda/stock-comparison` (`/valuation` route)

---

## How the Workspace Maps to the Exoskeleton

| Workspace step | Exoskeleton step(s) | Source of truth |
|---|---|---|
| 1. Update / Refresh | 04 (Model Build), 09 (Catalyst Maintenance), 10 (Earnings Navigation) | Sector-research FMP client + EDGAR ingestion + transcript pull |
| 2. Research | 02 (Triage), 03 (Foundational DD), 12 (News Navigation) | Sector-research deep-dive nodes + Citation infra |
| 3. Validation / Sensitivity | 04 (Model Build), 07 (Expectations & Valuation) | Ported from stock-comparison (implied solver, sensitivity, bands) |
| 4. Challenge / Sharpen | 06 (Insight Formation), 08 (Thesis Construction), 11 (Mgmt Touchpoints) | MAMR Investor Council (HTTP) + sector-research risk_stress_test |
| 5. Differentiation | 03 (Foundational DD — Comps), 09 (Catalyst — Peer Read-Throughs) | Ported peer-comparison logic + EDGAR supply-chain graph |

The push-button accretion/dilution example (Slide 23) sits underneath Step 1 — it's the *mechanical scaffolding* the workspace assembles, with Steps 2–5 doing the analytical work on top.

---

## File Map

```
sector-research/
├── backend/
│   ├── alembic/versions/
│   │   ├── 00XX_ticker_models.py              ← NEW migration
│   │   └── 00XX_workspace_runs.py             ← NEW migration
│   ├── app/
│   │   ├── models/
│   │   │   ├── ticker_model.py                ← NEW: versioned per-ticker model state
│   │   │   ├── workspace_run.py               ← NEW: workspace run records
│   │   │   ├── ma_models/                     ← NEW: M&A model templates
│   │   │   │   ├── __init__.py
│   │   │   │   └── accretion_dilution.py      ← Pydantic schema + populator
│   │   │   └── workspace_schemas.py           ← Pydantic outputs per workspace step
│   │   ├── graph/
│   │   │   ├── pipeline.py                    ← existing 6-phase DD (unchanged)
│   │   │   ├── workspace.py                   ← NEW: 5-step workspace graph
│   │   │   ├── workspace_nodes.py             ← NEW: node implementations
│   │   │   └── workspace_prompts.py           ← NEW: prompts for each step
│   │   ├── services/
│   │   │   ├── model_diff.py                  ← NEW: ticker_model JSON diff
│   │   │   ├── implied_solver.py              ← PORTED from stock-comparison
│   │   │   ├── sensitivity_grid.py            ← PORTED from stock-comparison
│   │   │   ├── valuation_bands.py             ← PORTED from stock-comparison
│   │   │   └── investor_council_client.py     ← NEW: HTTP client to MAMR council endpoint
│   │   ├── api/
│   │   │   ├── workspace.py                   ← NEW: workspace CRUD + run endpoints
│   │   │   └── ma_models.py                   ← NEW: /api/models/ma/{acquirer}/{target}
│   │   └── clients/
│   │       └── citation.py                    ← extended: cell-level audit trail support
│   └── tests/
│       ├── graph/test_workspace.py            ← NEW
│       ├── services/test_implied_solver.py    ← NEW
│       ├── services/test_sensitivity_grid.py  ← NEW
│       ├── services/test_model_diff.py        ← NEW
│       └── api/test_workspace.py              ← NEW
└── frontend/
    ├── app/workspace/
    │   ├── page.tsx                           ← NEW: workspace dashboard (list)
    │   └── [runId]/page.tsx                   ← NEW: workspace runner
    ├── components/workspace/
    │   ├── ModelStateView.tsx                 ← NEW: current vs prior version
    │   ├── DiffPanel.tsx                      ← NEW: "what changed"
    │   ├── ImpliedSolverPanel.tsx             ← PORTED from stock-comparison
    │   ├── SensitivityGrid.tsx                ← PORTED from stock-comparison
    │   ├── ValuationBandsChart.tsx            ← PORTED from stock-comparison
    │   ├── InvestorCouncilPanel.tsx           ← NEW: renders MAMR council perspectives
    │   └── PeerBenchmarkTable.tsx             ← PORTED from stock-comparison
    └── lib/api.ts                             ← extended: workspace + ma_models endpoints

multi-agent-market-research/                   ← changes scoped to one new endpoint
└── src/api.py                                 ← NEW: POST /api/council/evaluate
└── src/agents/investor_council.py             ← NEW: orchestrates 5 investor profiles
└── tests/test_investor_council.py             ← NEW
```

---

## Phase 0 — Foundations (sector-research)

### 0.1 — Schema additions

- [ ] Create Alembic migration `ticker_models` table:
  - `id` (uuid, pk), `ticker` (str, indexed), `version` (int), `state` (jsonb), `parent_research_run_id` (fk, nullable), `created_at`
  - Composite unique on `(ticker, version)`; auto-increment `version` per ticker via app logic
- [ ] Create Alembic migration `workspace_runs` table:
  - `id` (uuid, pk), `ticker_model_id` (fk), `step` (str), `status` (str: running/awaiting_review/complete/failed), `state` (jsonb), `created_at`, `updated_at`
- [ ] Extend `citations` table with optional `cell_path` (str, nullable) — the dotted path within a model state where this citation applies (e.g., `ma.accretion_dilution.synergies.cost_runrate`)
- [ ] Run migrations against dev DB; verify with `\d ticker_models` etc.

### 0.2 — ORM + Pydantic models

- [ ] `app/models/ticker_model.py` — SQLAlchemy ORM mirroring schema; `state` typed as `dict`
- [ ] `app/models/workspace_run.py` — SQLAlchemy ORM; relationships to `ticker_model`
- [ ] `app/models/workspace_schemas.py` — Pydantic schemas for each workspace step output:
  - `UpdateOutput`, `ResearchOutput`, `ValidationOutput`, `ChallengeOutput`, `DifferentiationOutput`
  - Each carries `citations: list[CitationRef]` and `summary: str`
- [ ] Register all new models in `app/models/__init__.py` (Alembic autogenerate dependency)

### 0.3 — Citation extension

- [ ] Update `app/clients/citation.py` `Citation` dataclass: add optional `cell_path: str | None = None`
- [ ] Add `Citation.with_cell(path: str) -> Citation` helper for chained construction
- [ ] Backfill: existing citations are unaffected (`cell_path` defaults to None)
- [ ] Add unit test confirming cell-aware citations serialize correctly

---

## Phase 1 — Workspace graph skeleton

### 1.1 — LangGraph definition

- [ ] `app/graph/workspace.py` — define `WorkspaceState` TypedDict with: `ticker`, `current_version`, `prior_version`, `step`, `step_outputs` (dict), `citations` (list), `human_feedback` (dict)
- [ ] Define 5-node graph: `update_refresh → research → validation_sensitivity → challenge_sharpen → differentiation → END`
- [ ] Insert human interrupts after `update_refresh` (review diff), `validation_sensitivity` (review reverse-DCF + bands), and `challenge_sharpen` (review council + variant view)
- [ ] State persistence to Postgres via existing checkpoint pattern from `pipeline.py`

### 1.2 — Stub nodes (wire end-to-end before filling logic)

- [ ] `app/graph/workspace_nodes.py` — five stub functions, each writing a deterministic placeholder to `step_outputs` and returning state
- [ ] All stubs emit at least one `Citation` so the citation accumulation path is exercised end-to-end
- [ ] Test: a workspace run with stubs completes through all 5 steps + 3 interrupts and persists final state

### 1.3 — API surface

- [ ] `app/api/workspace.py`:
  - `POST /api/workspace/{ticker}/runs` — kick off a new run, requires existing `research_runs` row for ticker
  - `GET /api/workspace/runs/{run_id}` — fetch state + step outputs
  - `POST /api/workspace/runs/{run_id}/resume` — resume after interrupt with `{action, notes}`
  - `GET /api/workspace/{ticker}/versions` — list ticker_model versions
  - `GET /api/workspace/{ticker}/versions/{version}/diff?against=N` — JSON diff
- [ ] OpenAPI schema generated cleanly; smoke test via curl

---

## Phase 2 — Step 1 (Update / Refresh) — real implementation

### 2.1 — Pull-from-source services

- [ ] Reuse existing FMP client to fetch latest 10-Q financials for the ticker
- [ ] Reuse EDGAR client to fetch latest filing narrative + transcript (already exists)
- [ ] New service `app/services/model_diff.py`: deterministic JSON diff between ticker_model versions. Output: `{added, removed, changed}` with cell-path keys.
- [ ] Consensus sync: call FMP analyst estimates, store as `consensus_overlay` block in state

### 2.2 — Update node logic

- [ ] `update_refresh` node: 
  1. Load latest `ticker_model` version
  2. Pull new actuals; populate updated `state` JSON
  3. Compute diff vs prior; attach to step output
  4. Write new `ticker_model` row (version += 1) with updated state
  5. Emit citations on every changed cell
- [ ] Test: given a fixture ticker_model + mocked FMP response, node produces expected diff + cited cells

### 2.3 — Frontend Step 1 view

- [ ] `components/workspace/DiffPanel.tsx` — collapsible tree of changed cells, citation footnotes inline
- [ ] `components/workspace/ModelStateView.tsx` — side-by-side prior/current with delta column
- [ ] Wire into `app/workspace/[runId]/page.tsx` as the first phase view

---

## Phase 3 — Step 3 (Validation / Sensitivity) — port from stock-comparison

> Build Step 3 before Step 2 because the ported logic from stock-comparison is the highest-leverage migration; Step 2 is mostly orchestration of existing sector-research deep-dive nodes.

### 3.1 — Port the implied solver

- [ ] Read stock-comparison's `/valuation` implementation (likely in `src/lib/valuation/` or similar)
- [ ] Port to `app/services/implied_solver.py`:
  - Input: current price, financials, peer multiple, required return
  - Output: implied growth, implied margin, implied terminal multiple (the three solver columns)
- [ ] Preserve PV-discounting semantics; add Pydantic input/output models
- [ ] Test: regression against 3 known tickers with hand-calculated expected values

### 3.2 — Port sensitivity grid

- [ ] Port grid generator to `app/services/sensitivity_grid.py`
- [ ] Three axes (growth/multiple, margin/multiple, growth/margin) — each returns a 2D numpy array + axis labels
- [ ] Test with deterministic inputs against known reference output

### 3.3 — Port valuation bands

- [ ] Port historical EV/Sales + EV/EBITDA band computation to `app/services/valuation_bands.py`
- [ ] Port cheap/fair/rich verdict (`PERCENTRANK.INC` equivalent — use `scipy.stats.percentileofscore`)
- [ ] Quarterly/annual granularity toggle preserved
- [ ] Test against fixture historical financials

### 3.4 — Validation node logic

- [ ] `validation_sensitivity` node:
  1. Run implied solver on current ticker_model state
  2. Generate 3 sensitivity grids
  3. Compute 5Y valuation bands + verdict
  4. Run formula validation (circularity check, hardcoded-vs-derived audit) — start with simple ruleset, expand later
  5. Emit per-cell citations on every assumption used
- [ ] Test: full node run against fixture ticker_model

### 3.5 — Frontend Step 3 views

- [ ] Port `ImpliedSolverPanel.tsx`, `SensitivityGrid.tsx`, `ValuationBandsChart.tsx` from stock-comparison
- [ ] Match sector-research's existing dashboard styling (slate-based dark theme)
- [ ] Wire into workspace runner page

---

## Phase 4 — Step 4 (Challenge / Sharpen) — Investor Council via MAMR

### 4.1 — MAMR side: expose the council

- [ ] In `multi-agent-market-research/src/agents/investor_council.py`:
  - Define 5 investor profile prompts (Druckenmiller, PTJ, Munger, Dalio, Marks) — pull from existing 27-profile library at `01_Projects/Multi-Agent-Market-Research/Investor-Profiles/`
  - Each profile takes a thesis JSON + market context, returns `{perspective, supporting_signals, dissenting_view, conviction_modifier}`
  - Run the 5 in parallel
- [ ] In `multi-agent-market-research/src/api.py`:
  - `POST /api/council/evaluate` — body: `{thesis, ticker, context}`; response: `{perspectives: [...], synthesis: {...}}`
- [ ] Test: smoke run with a fixture thesis returns 5 perspectives in deterministic order
- [ ] Document endpoint in MAMR README

### 4.2 — Sector-research side: client + node

- [ ] `app/services/investor_council_client.py` — typed httpx wrapper around MAMR endpoint with retry + timeout
- [ ] Configurable `MAMR_BASE_URL` env var (default `http://localhost:8001`)
- [ ] `challenge_sharpen` node:
  1. Build thesis JSON from prior workspace step outputs + ticker_model state
  2. Call MAMR council endpoint
  3. Run sector-research's existing `risk_stress_test` logic for structural risks (already exists in pipeline)
  4. Synthesize: variant view + what's priced in (from Step 3 implied solver) + kill criteria
  5. Emit citations on every claim
- [ ] Test: with mocked MAMR response, node produces expected `ChallengeOutput`

### 4.3 — Frontend Step 4 view

- [ ] `components/workspace/InvestorCouncilPanel.tsx` — 5-card layout (one per investor), conviction modifier badge, dissenting-view callouts
- [ ] Variant-view section showing where the thesis diverges from consensus (from Step 3 outputs)
- [ ] Kill criteria as an editable list (saved to `human_feedback` on interrupt)

---

## Phase 5 — Step 5 (Differentiation) — peer benchmark

### 5.1 — Peer benchmark service

- [ ] Port stock-comparison's peer comparison to `app/services/peer_benchmark.py`
- [ ] Reuse sector-research's theme system: peers default to ticker's primary theme membership; user can override
- [ ] Side-by-side: revenue growth, gross margin, op margin, FCF margin, ROIC, EV/Sales, EV/EBITDA, P/E
- [ ] "Best-in-class gap" computation: distance to the leader on each metric, normalized

### 5.2 — Read-across via supply-chain graph

- [ ] Reuse existing EDGAR supply-chain graph from `services/supply_chain.py`
- [ ] When a peer has a recent earnings print, surface read-across signal: "PEER reported X — relevant because [edge in supply graph]"
- [ ] Expose as `differentiation_node` sub-step that runs *only* if any peer has reported within last 14 days

### 5.3 — Differentiation node logic

- [ ] `differentiation` node:
  1. Resolve peer set (theme-based default)
  2. Run peer benchmark
  3. Run read-across pass
  4. Emit citations on every comparable metric
- [ ] Test: with fixture peer set + supply graph, produces expected `DifferentiationOutput`

### 5.4 — Frontend Step 5 view

- [ ] Port `PeerBenchmarkTable.tsx` from stock-comparison
- [ ] Add read-across panel — list of recent peer prints with relevance edge from supply graph
- [ ] Best-in-class gap visualization (radar chart + delta column)

---

## Phase 6 — Step 2 (Research) — wire to existing deep-dive

### 6.1 — Reuse don't rebuild

- [ ] `research` node in `workspace_nodes.py` calls existing sector-research deep-dive nodes for: news pull (recent developments since last refresh), drill-downs (segment/geo/SKU), risk surfacing
- [ ] *No new agent code* — this step is glue; the deep-dive logic already lives in `pipeline.py`
- [ ] Output: `ResearchOutput` with `recent_news`, `drill_downs`, `risk_register`, citations

### 6.2 — "What am I missing" sub-step

- [ ] New Haiku prompt: given the current model state + recent news + Step 1 diff, identify risks not currently in the model
- [ ] Append to `ResearchOutput.risk_register`
- [ ] Test: regression against fixture model state

### 6.3 — Frontend Step 2 view

- [ ] Reuse existing deep-dive components from `frontend/components/deep-dive/` — render `ResearchOutput` through the same skeleton
- [ ] No new components required

---

## Phase 7 — Push-button: M&A model template

### 7.1 — Accretion/dilution Pydantic schema

- [ ] `app/models/ma_models/accretion_dilution.py`:
  - Block-structured schema matching the DHR/MASI example (Slide 23):
    1. `AcquirerStandalone` — Revenue, EBITDA, EPS, shares, net income (5Y forecast)
    2. `TargetContribution` — Revenue, EBITDA, D&A, EBIT (5Y)
    3. `SynergyPhaseIn` — phase-in %, cost synergies (run-rate), revenue synergies, realized, EBITDA from rev synergies, total
    4. `AcquisitionFinancing` — debt, cost of debt, tax rate, pre-tax/after-tax interest, lost interest on cash
    5. `ProFormaEPS` — composed from above with explicit formula recorded per cell
    6. `Output` — accretion/dilution per share + percent
- [ ] Each cell carries `(value, formula, citation_id, timestamp)` — implement as `ModelCell` Pydantic submodel

### 7.2 — Populator service

- [ ] `app/services/ma_model_populator.py`:
  - Input: acquirer ticker, target ticker, deal terms (cash %, debt cost, premium)
  - Pulls FMP financials for both, builds the schema, computes the math, attaches citations
  - Returns fully populated `AccretionDilutionModel` instance
- [ ] Test: regression against a known historical deal (pick one with public accretion guidance)

### 7.3 — API + minimal frontend

- [ ] `app/api/ma_models.py`:
  - `POST /api/models/ma/accretion-dilution` — body: `{acquirer, target, deal_terms}`
  - `GET /api/models/ma/{model_id}` — fetch a saved model
- [ ] `app/workspace/ma/page.tsx` — minimal form (acquirer/target/deal terms), renders the populated block-structured model with citation footnotes
- [ ] Snapshot/export reuses existing snapshot pattern from sector-research

---

## Phase 8 — Snapshot, export, history

### 8.1 — Workspace snapshot

- [ ] On workspace run completion, freeze final state to a `workspace_snapshots` table (mirror stock-comparison's snapshot pattern)
- [ ] Snapshot includes: ticker_model state at completion, all 5 step outputs, all citations, council perspectives
- [ ] Naming: auto-generated `{ticker}-workspace-{YYYY-MM-DD}-{shortid}` with rename support

### 8.2 — Markdown export

- [ ] `app/services/workspace_export.py` — render snapshot to Obsidian-ready markdown
- [ ] Output path: `02_Areas/Investing-Portfolio/Workspace - {TICKER} - {YYYY-MM-DD}.md`
- [ ] Frontmatter: `date`, `ticker`, `tags: [workspace, refresh]`, `status: complete`, `conviction_modifier`
- [ ] Inline `[[WikiLinks]]` to peer tickers, theme, prior workspace runs

### 8.3 — PDF export

- [ ] Reuse stock-comparison's `@react-pdf/renderer` pattern — port the renderer config
- [ ] Single PDF per snapshot with all sections + chart PNGs

### 8.4 — Workspace history view

- [ ] `app/workspace/page.tsx` — table of all workspace runs across all tickers
- [ ] Columns: ticker, last refresh, version, conviction_modifier (from council), thesis_status (carried from latest research_run), action
- [ ] Click row → snapshot detail or resume in-progress run

---

## Phase 9 — Calibration hooks (forward-looking)

### 9.1 — Adopt MAMR's signal_contract_v2 envelope

- [ ] Wrap each workspace step output in a `signal_contract_v2`-compatible structure (port the schema from MAMR)
- [ ] Versioned: `analysis_schema_version`, deterministic ev_score, confidence_calibrated, data_quality_score, regime_label
- [ ] This is *additive* — `WorkspaceStepOutput` carries both the step-specific Pydantic model and a `signal_contract` field

### 9.2 — Calibration_snapshots equivalent

- [ ] On each workspace refresh, write a `workspace_calibration_snapshots` row recording: implied_solver outputs vs realized, council conviction_modifier vs subsequent return
- [ ] Defer the actual calibration analytics — just capture the data faithfully now
- [ ] Document: this is the input for a future "model says X, actual was Y" analytics dashboard

---

## Phase 10 — Hardening

### 10.1 — End-to-end test

- [ ] Pick one ticker with a complete prior `research_run` (suggest: a name from your existing watchlist with a recent earnings print)
- [ ] Run a full workspace refresh end-to-end through all 5 steps + 3 interrupts
- [ ] Verify: every cell has a citation, MAMR council was called, peer benchmark resolved, snapshot exported to vault, markdown opens cleanly in Obsidian

### 10.2 — Verification commands

- [ ] `cd backend && pytest backend/tests/graph/test_workspace.py backend/tests/services/ backend/tests/api/test_workspace.py -v` — all pass
- [ ] `cd frontend && npm run lint && npm run build && npx tsc --noEmit` — clean
- [ ] `cd ../multi-agent-market-research && pytest tests/test_investor_council.py -v` — passes

### 10.3 — Documentation

- [ ] Update sector-research README with workspace section + architecture diagram update
- [ ] Add `docs/workspace.md` covering: when to run a workspace refresh (post-earnings, on catalyst, on thesis-drift signal), state model, citation contract, MAMR dependency
- [ ] Add `02_Areas/Investing-Portfolio/Workspace-Workflow.md` to vault — the human-side SOP for running a refresh

---

## Out of Scope (this plan)

- Extracting `mam-data` shared package — defer until duplicate FMP client method is written *twice* in sector-research
- Migrating MAMR off SQLite to Postgres
- LBO model template (only accretion/dilution in v1)
- DCF model template (Step 3's reverse-DCF/implied solver covers the immediate need)
- Auto-trigger on earnings — start with manual trigger; auto-schedule is a follow-on
- Real-time price-driven workspace refresh (the workspace is event-driven, not tick-driven)

---

## Lessons-Learned Discipline

These come from the audit of MAMR / sector-research / stock-comparison and should be enforced in this plan:

1. **Citation on every datum** — sector-research's `Citation` primitive is the single best pattern across your three repos. Every workspace cell carries one. Non-negotiable.
2. **Pydantic-validated structured outputs with prose fallback** — sector-research's `parse_structured_output` pattern. Adopt for every workspace step.
3. **LangGraph interrupts at decision gates** — never auto-advance through Step 1, 3, or 4. Eric is the synthesizer.
4. **Snapshot + Obsidian export per run** — stock-comparison's pattern. Workspace runs feed the vault; the vault is the durable record.
5. **Standardize on Anthropic** — calibration data isn't comparable across providers. Sector-research is already Anthropic; MAMR will be. Drop OpenAI dependency in stock-comparison logic when porting.
6. **Don't duplicate FMP client yet** — port logic, not connectors. Extract shared package only after the same method exists in two repos.
7. **MAMR Investor Council stays in MAMR** — sector-research calls it over HTTP. Don't fork.

---

## Suggested execution order

1. Phase 0 (foundations) — blocking for everything
2. Phase 1 (skeleton with stubs) — get end-to-end run working before filling in logic
3. Phase 3 (port from stock-comparison) — highest-leverage migration, do this before deeper graph work
4. Phase 4 (Investor Council) — touches MAMR, do early so any API contract issues surface
5. Phase 2 (Update/Refresh) — fills in real Step 1 logic
6. Phase 6 (Research) — glue to existing deep-dive
7. Phase 5 (Differentiation) — depends on theme/peer set work
8. Phase 7 (M&A push-button) — independent, can start anytime after Phase 0
9. Phase 8 (snapshot/export/history) — once steps 1–5 produce real outputs
10. Phase 9 (calibration hooks) — additive, do before Phase 10 hardening
11. Phase 10 (end-to-end test + docs) — gate before declaring complete
