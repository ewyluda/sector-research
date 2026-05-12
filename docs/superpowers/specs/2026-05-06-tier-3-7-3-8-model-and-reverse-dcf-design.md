# Tier 3.7 + 3.8 — Editable Financial Model & Reverse DCF

**Status:** Design — not yet planned. Brainstormed 2026-05-06.
**Roadmap reference:** `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md` Tier 3 items 7 and 8.
**Scope decision (per roadmap):** This spec settles the model's coverage. **γ — full 3-statement model**, 5Y annual + 8Q quarterly forecast.
**Out of scope (deferred to Tier 3.9 or later):** Workspace 5-step loop, MAMR Investor Council integration, M&A accretion-dilution push-button template, snapshot/Obsidian export, calibration_snapshots, auto-trigger on earnings prints.

The absorbed plan `docs/2026-05-03-model-workspace-plan.md` remains the implementation reference for **3.9** (Phases 4, 5, 7, 8, 9 of that plan are 3.9 territory). This spec covers Phases 0, 2, 3 of that plan in expanded form, plus a fully fleshed reverse-DCF surface.

---

## 1. Goal

A per-ticker, editable, AI-seeded full 3-statement financial model with a versioned history and a reverse-DCF readout that decomposes current price into the assumptions priced in. The model is the keystone for the entire B-bucket workflow: it gates the workspace 5-step loop (3.9) and supplies the analytical depth that the existing thesis (Tier 1.1) and earnings cycle (Tier 2.5) features can only gesture at today.

**Success looks like:**
- Open `/model/<ticker>` for any ticker that has a completed `research_run`. Within ~15 seconds, see a populated 3-statement model with 8 quarters of historicals, 8 quarters of forecast detail, 5 years of annual forecast, and a baseline driver set seeded by the deep-dive's existing analysis.
- Edit any driver. Watch downstream P&L / BS / CF cells recompute. Override individual computed cells when guidance or one-offs require it.
- Switch to the Reverse DCF tab. Read implied growth / margin / terminal multiple, implied IRR, and a thesis-vs-priced-in delta table — all live against current price.
- Save the model as a labeled version. Diff later versions against earlier ones.

---

## 2. Architecture

```
                    ┌──────────────────────────────────┐
                    │  GET /api/models/<ticker>        │
                    │  POST /api/models/<ticker>/init  │
                    │  PUT  /api/models/<ticker>/draft │
                    │  POST /api/models/<ticker>/save  │
                    │  GET  /api/models/<ticker>/      │
                    │       reverse-dcf?price=...      │
                    └─────────────┬────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────────────┐
                  │ services/                           │
                  │  ├─ model_baseline.py (Sonnet)      │
                  │  ├─ model_balancing.py (plug logic) │
                  │  ├─ model_diff.py                   │
                  │  ├─ dcf.py (pure)                   │
                  │  └─ reverse_dcf.py (4 solvers)      │
                  └─────────────┬───────────────────────┘
                                │
                                ▼
                ┌─────────────────────────────────────┐
                │ ticker_models (Postgres, JSONB)     │
                │ + citations.cell_path extension     │
                └─────────────────────────────────────┘
```

The model is **per-ticker**, not per-research-run. Versions roll forward independently. Each version optionally records a `parent_research_run_id` linking to the run whose deep-dive seeded it (or whose update triggered the version, in 3.9 land).

---

## 3. Data model

### 3.1 `ticker_models` table

| column | type | notes |
|---|---|---|
| `id` | UUID (as_uuid=False per project convention) | PK |
| `ticker` | str | indexed |
| `version` | int | auto-increment per ticker via app logic |
| `state` | JSONB | full `ModelState` (Pydantic-validated on read/write) |
| `parent_research_run_id` | str FK → `research_runs.id` | nullable |
| `label` | str | nullable, e.g. `"post-Q3-print baseline"` |
| `created_at` | timestamp | from `TimestampMixin` |
| `updated_at` | timestamp | from `TimestampMixin` |

Composite unique on `(ticker, version)`. Use `Base + TimestampMixin`, `UUID(as_uuid=False)`, `Mapped[str]` per project convention (see `models/question.py` for the established pattern).

### 3.2 `ModelState` (Pydantic, persisted as `state` JSONB)

```python
class Period(BaseModel):
    label: str               # "2024Q1", "2026", etc.
    kind: Literal["Q", "Y"]
    is_historical: bool
    quarter_index: int | None  # 1-4 for kind=Q, None for kind=Y

class ModelCell(BaseModel):
    value: float | None
    source: Literal["historical", "ai_baseline", "driver", "computed", "override"]
    formula: str | None      # e.g. "= revenue * gross_margin_pct"
    citation_id: str | None  # FK to citations.id
    last_edited_at: str | None  # ISO
    last_edited_by: Literal["system", "ai_baseline", "user"] | None

class ModelState(BaseModel):
    periods: list[Period]
    drivers: dict[str, dict[str, ModelCell]]            # {period_label: {driver_key: cell}}
    income_statement: dict[str, dict[str, ModelCell]]   # {line_item: {period: cell}}
    balance_sheet: dict[str, dict[str, ModelCell]]
    cash_flow: dict[str, dict[str, ModelCell]]
    assumptions: ModelAssumptions

class ModelAssumptions(BaseModel):
    discount_rate: ModelCell        # CAPM default
    terminal_method: Literal["exit_multiple", "perpetuity"]
    terminal_multiple: ModelCell    # EV/EBITDA
    perpetuity_growth: ModelCell
    tax_rate: ModelCell
    plug_priority: list[Literal["debt_paydown", "buyback", "dividend", "cash"]]
```

`ModelCell` is the **single audit-trail primitive**. Every numeric value the user sees on screen, in any tab, comes from a `ModelCell`. The `source` discriminator drives the UI's color coding (historical = grey, ai_baseline = pale yellow, driver = yellow, computed = white, override = orange-bordered).

### 3.3 Driver and line-item registry

Closed lists, defined as Python constants (no DB metadata). Driver keys are stable, lowercased, snake_case identifiers. Line item keys mirror FMP's statement structure to make seeding trivial.

**Drivers** (per period, ~25 keys):
- Revenue: `revenue_growth_pct` *or* `revenue_absolute` (mutually exclusive — only one populated, the other is `None`)
- Margins: `gross_margin_pct`, `sga_pct_revenue`, `rd_pct_revenue`, `other_opex_pct_revenue`, `da_pct_revenue`
- Below the line: `effective_tax_rate`, `interest_income_yield`, `interest_expense_rate`
- Capex/WC: `capex_pct_revenue`, `dso_days`, `dio_days`, `dpo_days`
- Capital return: `dividend_payout_ratio`, `buyback_dollars`, `share_count_change_pct`
- Debt: `debt_repayment_dollars`, `revolver_rate`
- M&A & one-offs: deferred (Tier 4 / 3.9 — workspace plan Phase 7)

**Line items** (P&L: ~12, BS: ~16, CF: ~12). Concrete enumeration is captured in `backend/app/models/model_state.py::LINE_ITEMS`. Use FMP's existing income/balance/cashflow response keys verbatim where possible to make `model_baseline.py` ingest trivial.

### 3.4 `Citation` extension

Add nullable `cell_path: str | None` to:
- `Citation` dataclass (`models/citation.py`)
- `CitationRecord` ORM
- `StateCitation` (`graph/state.py`)

Cell-path format: `{statement}.{line_item}.{period_label}` for line-item cells, `drivers.{period_label}.{driver_key}` for driver cells, `assumptions.{key}` for assumption cells. Example: `income_statement.revenue.2026Q1`. Empty cell_path on existing rows is unaffected.

Add `Citation.with_cell(path: str) -> Citation` helper for chained construction inside the baseline node.

---

## 4. Initial population (lazy, on first `/model/<ticker>` request)

**Trigger:** frontend calls `POST /api/models/<ticker>/initialize` if the ticker has no `ticker_models` row yet (or `?force=true`).

**Flow:**

1. **Load the seeding context.** Pull the most recent completed `research_run` for `ticker`. Hydrate `ResearchState` from `state` JSONB. Extract:
   - `curated_financials` (already includes 8Q income/balance/cashflow, profile, DCF, key-metrics-ttm, financial-growth, analyst estimates).
   - Deep-dive findings for Growth & Earnings, Business Quality, Future Durability, Financial Health (these are the categories most informative to the model's drivers).
   - Macro context: latest 10Y yield from FRED (for CAPM `rf`), beta from FMP profile.
   - Thesis output (`core_thesis`, bull/bear case titles).
2. **Fill historicals.** Map FMP's 8Q income/balance/cashflow responses into `ModelCell`s with `source="historical"` and a `Citation` pointing to the FMP fetch. No LLM here.
3. **Run the baseline forecast node.** A new Sonnet call (`graph/model_baseline_node.py`):
   - System prompt: "You are building a baseline financial forecast for a 3-statement model. Use the deep-dive findings, analyst consensus, and historical trends to produce structured driver assumptions for the next 8 quarters and 5 annual years..."
   - User content: historicals + analyst estimates + deep-dive summaries + thesis output. Prompt-cached if the system prompt is >500 chars (it will be).
   - `assistant_prefill = '{"drivers":'`. Parse with `model_validate_json` into `ForecastDrivers` Pydantic schema (mirrors `ModelState.drivers` structure).
   - Each driver in the response carries a `reason` field and a `source_citation` pointing back to a deep-dive finding ID, an analyst estimate, or a historical-trend regression. Persist these via `Citation.with_cell(...)`.
4. **Compute derived line items.** Pure Python: drivers → P&L → CF → BS, in that order. `services/model_balancing.py` runs the plug-priority logic (default: `debt_paydown → buyback → dividend → cash`) and rolls net debt forward. BS must balance to within $1k; mismatch raises `ModelBalanceError` and bails the seed (which gets surfaced to the UI).
5. **Set CAPM defaults.** `discount_rate = rf + β × 0.055`. `terminal_method = "exit_multiple"`, `terminal_multiple` = trailing EV/EBITDA from key-metrics-ttm, `perpetuity_growth = 0.025`.
6. **Persist.** Write `ticker_models` row, version=1, label=`"AI baseline"`, `parent_research_run_id` = the seeding run.

**Idempotency:** If a row already exists, `POST /initialize` returns the latest version. `?force=true` triggers reseed → new version with label `"AI reseed"`.

---

## 5. Editing & versioning

### 5.1 Edit semantics

- **Driver cell** (yellow bg) — edit propagates: `PUT /api/models/<ticker>/draft` accepts the changed cell, runs the recompute pass server-side, and returns the full updated draft state synchronously (no SSE for v1 — recompute is sub-100ms for a single ticker). The driver cell's `source` stays `"driver"`; downstream cells flip to `"computed"`.
- **Computed cell** (white bg) — double-click promotes to **override**. The cell becomes `source="override"` with a fixed `value`; the formula is preserved as a comment but no longer evaluated. Downstream computed cells continue to cascade *from the override value*. A "revert override" action restores `source="computed"` and the original formula.
- **Historical cells** are read-only.
- **Assumption cells** edit inline (discount rate, terminal multiple, etc.).

### 5.2 Draft state

Edits accumulate in a server-side **draft** keyed by ticker (no per-user concept — single-user app). Draft is a separate row in a small `ticker_model_drafts` table:

| column | type |
|---|---|
| `ticker` | str PK |
| `base_version_id` | UUID FK → `ticker_models.id` |
| `state` | JSONB |
| `updated_at` | timestamp |

`PUT /api/models/<ticker>/draft` last-write-wins overwrites the draft. `GET /api/models/<ticker>` returns `{latest_version, draft | null}`. Frontend renders the draft if present, else the latest version.

### 5.3 Save & versioning

- **Save Version** — `POST /api/models/<ticker>/save` with `{label}`. Promotes the current draft to a new `ticker_models` row (version+1). Clears the draft.
- **Discard Draft** — deletes the draft row.
- **History tab** — list of versions (label, timestamp, version#). Diff viewer between any two versions uses `services/model_diff.py` to produce `{added: [...], removed: [...], changed: [{cell_path, before, after}]}`. Same diff format the workspace plan's Step 1 will reuse later in 3.9.

---

## 6. Reverse DCF (Tier 3.8)

### 6.1 DCF engine — `services/dcf.py`

One pure function:

```python
def dcf(
    state: ModelState,
    *,
    overrides: dict[str, float] | None = None,
    terminal_method: Literal["exit_multiple", "perpetuity"] | None = None,
    discount_rate: float | None = None,
) -> DcfResult:
    """
    Walk the forecast cash-flow schedule, discount FCFF, apply terminal value,
    return intrinsic value + per-share + schedule. `overrides` lets solvers
    swap a driver value uniformly across forecast periods without mutating state.
    """
```

`DcfResult`: `intrinsic_value, intrinsic_per_share, fcf_schedule, pv_schedule, terminal_value`. Pure function, no IO, no DB. Trivially unit-testable.

### 6.2 Solvers — `services/reverse_dcf.py`

Four pure functions, all built on `dcf()`:

1. **`solve_implied_driver(state, dimension, target_price)`** — bisection on a single driver. The candidate value is applied to every forecast period uniformly via the `overrides` parameter on `dcf()`, replacing the per-period values in `state.drivers` for that dimension only. `dimension ∈ {"revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"}`. Returns the driver value where intrinsic_per_share == target_price.
2. **`solve_implied_irr(state, target_price)`** — bisection on `discount_rate`.
3. **`sensitivity_grid(state, x_dim, y_dim, x_range, y_range)`** — 21×21 evaluations of `dcf()` with each (x,y) pair applied uniformly. Three predefined grids: growth×margin, growth×multiple, margin×multiple.
4. **`thesis_vs_priced_in(state, target_price)`** — calls `solve_implied_driver` three times; joins to current driver values for the delta column.

All four take and return primitives (no DB). Cumulative compute for one full reverse-DCF call against current price: ~3 ms (bisection ~30 evaluations each + 21×21 grid × 3 = ~1350 evaluations). Negligible.

### 6.3 API — `GET /api/models/<ticker>/reverse-dcf?price=<float|null>`

Single endpoint returns all four payloads:

```json
{
  "price_used": 142.31,
  "price_source": "fmp_live" | "user_override",
  "implied_drivers": { "revenue_growth_pct": 0.082, "ebit_margin_pct": 0.211, "terminal_multiple": 14.5 },
  "implied_irr": 0.094,
  "sensitivity_grids": {
    "growth_margin":   { "x_dim": "revenue_growth_pct", "y_dim": "ebit_margin_pct", "values": [[...21x21]] },
    "growth_multiple": { ... },
    "margin_multiple": { ... }
  },
  "thesis_vs_priced_in": [
    { "dimension": "revenue_growth_pct", "thesis": 0.12, "priced_in": 0.082, "delta": 0.038 },
    { "dimension": "ebit_margin_pct",    "thesis": 0.24, "priced_in": 0.211, "delta": 0.029 },
    { "dimension": "terminal_multiple",  "thesis": 16.0, "priced_in": 14.5,  "delta": 1.5 }
  ]
}
```

If `price` is omitted, FMP live price is fetched (existing client). Reverse-DCF endpoint always reads from the latest *saved version* (not the draft) to keep the readout stable while editing — frontend can pass `?from_draft=true` to opt in.

---

## 7. UI surface

### 7.1 Routes

- `/model/[ticker]/page.tsx` — three tabs: **Forecast**, **Reverse DCF**, **History**. Tab state is a URL hash (`#forecast` etc.) for deep-linkability.

### 7.2 Forecast tab

- **Top section: drivers panel.** Collapsible. Grouped: Revenue / Margins / Capex & WC / Capital Return / Debt. Each row = one driver, columns = periods. Inline edit.
- **Middle section: 3-statement grid.** One scrollable table per statement (P&L / BS / CF), or a single tabbed switcher within this section. Sticky left column = line items (grouped: Revenue → Gross Profit → Operating Income → ... ); sticky top row = periods (8 historical Q + 8 forecast Q + 5 forecast Y).
- **Formula bar** (top of page, sticky): when a cell is focused, show `{cell_path} = {formula or value} | source: {source} | citation: <pill>`. Citation pill click opens the existing source modal.
- **Action bar** (bottom right, sticky): Save Version (with label modal), Discard Draft. Disabled when no draft.
- **CommandPalette** (⌘K) jumps to a line item or driver. Uses the same registry pattern as deep-dive's `sections.ts`.
- **Print stylesheet:** `data-print-hide="true"` on action bar, formula bar, command palette. Grid prints as static page.

### 7.3 Reverse DCF tab

Three vertically-stacked sections:

1. **Headline row.** Implied IRR (single big number) on the left. Thesis-vs-priced-in 4-row table (one row per dimension + one summary row) on the right. Color the delta column green/red based on direction.
2. **Sensitivity grids.** Three 21×21 heatmaps side by side (growth×margin, growth×multiple, margin×multiple). Hover shows (x, y, intrinsic_per_share). Current-price iso-curve overlaid as a contour line.
3. **What-if scratch panel.** "Clone current state to scenario" button. User edits drivers in a scoped scratch panel; reverse-DCF auto re-runs against the scratch state without saving a new version. Clear-scratch button.

### 7.4 Deep-dive integration

- Add a **"Model"** pill to `components/deep-dive/SectionNav.tsx`. Click → navigates to `/model/<ticker>#forecast`.
- Add a **model status badge** to the deep-dive header next to the verdict callout: `"Model v3 · Saved 2d ago · IRR 12.4%"`. One API call to `GET /api/models/<ticker>` populates it. Hidden if no model exists yet (with a "Create model" button instead).

### 7.5 New component layout

```
frontend/components/model/
├── ForecastGrid.tsx           # the 3-statement grid
├── DriverPanel.tsx            # collapsible driver group panel
├── FormulaBar.tsx             # sticky top, shows ModelCell metadata
├── CellRenderer.tsx           # single cell — color-coded by source
├── ReverseDcfPanel.tsx        # tab content
├── SensitivityHeatmap.tsx     # one heatmap (Recharts custom or d3)
├── ThesisVsPricedTable.tsx
├── HistoryDiffViewer.tsx
├── SaveVersionModal.tsx
├── CommandPaletteModel.tsx    # adapted from deep-dive's CommandPalette
└── modelSections.ts           # registry mirroring deep-dive/sections.ts
```

Reuse `components/deep-dive/scoreColors.ts` palette tier helpers where the heatmaps need a divergent scale; otherwise pick a fresh diverging palette in `components/model/heatmapColors.ts`.

---

## 8. Where the code lives (backend)

```
backend/app/
├── models/
│   ├── ticker_model.py            # ORM (TickerModel)
│   ├── ticker_model_draft.py      # ORM (TickerModelDraft)
│   ├── model_state.py             # Pydantic: ModelState, ModelCell, etc.
│   └── citation.py                # extended: cell_path
├── services/
│   ├── model_baseline.py          # initialize flow (loads run, runs Sonnet, fills cells)
│   ├── model_balancing.py         # plug-priority logic, BS rollforward
│   ├── model_diff.py              # JSON diff (cell-path keyed)
│   ├── dcf.py                     # pure DCF engine
│   └── reverse_dcf.py             # 4 solvers
├── graph/
│   ├── model_baseline_node.py     # the Sonnet node (factored)
│   └── state.py                   # extended: StateCitation.cell_path
├── api/
│   └── models_api.py              # CRUD + initialize + draft + save + reverse-dcf
└── alembic/versions/
    ├── XXXX_add_cell_path_to_citations.py
    ├── XXXX_create_ticker_models.py
    └── XXXX_create_ticker_model_drafts.py
```

Register `TickerModel` and `TickerModelDraft` in `models/__init__.py` (both the import line and the `__all__` entry — established convention from Tier 1.2).

---

## 9. Verification

### 9.1 Unit tests

- `services/test_dcf.py` — three hand-calculated tickers (mature dividend payer, high-growth, cyclical). Assert intrinsic per-share within 1¢ of the spreadsheet reference. Cover both terminal methods.
- `services/test_reverse_dcf.py` — for each fixture, the four solvers converge and round-trip (i.e., feeding the implied driver back into `dcf()` reproduces target_price within 1¢).
- `services/test_model_balancing.py` — given fixture drivers, BS balances to within $1k after rollforward; plug-priority order is honored.
- `services/test_model_diff.py` — diffs reflect added / removed / changed correctly under cell-path keys.

### 9.2 Integration smoke

- One real ticker with a completed `research_run` and recent FMP data.
- `POST /initialize` → version 1 created, all cells populated, BS balances.
- `PUT /draft` with a single driver edit → downstream cells recompute server-side.
- `POST /save` → version 2 created, draft cleared.
- `GET /reverse-dcf?price=<live>` → all four payloads non-null and shape-valid.

### 9.3 Frontend

- `npm run lint && npm run build && npx tsc --noEmit` clean.
- Manual: open `/model/<ticker>`, edit a driver, save, view history diff, switch to Reverse DCF, hover heatmap.

---

## 10. Risks & open questions

1. **BS balancing edge cases.** Rolling the BS forward from CF is mechanical for vanilla businesses but fragile for: (a) tickers with non-trivial deferred revenue or unearned subscriptions, (b) financial-services tickers (banks, insurers), (c) commodity tickers with large WC swings. Mitigation: scope v1 to non-financials; raise `ModelBalanceError` and surface to UI on imbalance rather than silently plugging — gives the user a chance to override. Tag the deep-dive's `Industry` field on the seeding run; if "financials," refuse to seed and message the user.
2. **AI baseline quality.** A Sonnet-generated 8Q forecast can drift unrealistically from analyst consensus. Mitigation: the baseline node prompt explicitly includes consensus estimates and instructs the model to anchor near consensus unless the deep-dive findings contradict (with explicit reasoning and a citation). Post-seed, surface a warning in the UI for any driver where the AI's value differs from consensus by >30% relative (or >5pp absolute for margin-style drivers), so the user reviews before saving.
3. **Live price freshness.** FMP live-quote latency. Mitigation: cache live price for 60s in the reverse-DCF endpoint; show timestamp in the UI.
4. **Reverse-DCF on draft state.** Per §6.3, default reads latest saved version. The `?from_draft=true` flag exists but the what-if scratch panel (§7.3.3) is the primary "live recompute" surface to keep iteration fast without polluting the saved-version readout.
5. **Citation density.** Every cell has a citation slot; the AI baseline produces ~600 cells × 1 citation each ≈ 600 citation rows on first seed. Audit: does the existing citations table comfortably handle this volume per-ticker? Sample test against one ticker before committing.

---

## 11. Definition of done

- Schema migrations applied; ORM models registered.
- `dcf()` and the four reverse-DCF solvers pass the regression fixtures.
- One real ticker can be initialized, edited, saved, and reverse-DCF'd end-to-end through the UI.
- Deep-dive header shows the model status badge.
- Existing deep-dive, status board, earnings navigator, and question-log features are unaffected (regression smoke).
- Spec for **Tier 3.9** (workspace 5-step loop) can be written against this model as the substrate without further schema changes (the absorbed `2026-05-03-model-workspace-plan.md` already assumes this primitive shape).
