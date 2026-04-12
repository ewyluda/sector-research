# TODO — Phase Output Dashboard Migrations

## What's done

### Quick Screen (Phase 1) ✅
- Structured JSON contract (`QuickScreenOutput` Pydantic model)
- `QuickScreenCard` dashboard component (score ring, dimension table, thesis/risk callouts, citation footer)
- Integrated on pipeline runner page + report page with prose fallback for old runs

### Thesis Construction (Phase 4) ✅
- Structured JSON contract (`ThesisOutput` Pydantic model)
- `ThesisCard` "Analyst Memo" dashboard (conviction ring, core thesis callout, bull/bear columns, variant perception, catalyst timeline, conviction rationale)
- Thesis promoted to a proper interrupt phase (was a latent bug — node never set `awaiting_approval`)
- Integrated on pipeline runner page + report page with prose fallback

### Risk Stress-Test (Phase 5) ✅
- Structured JSON contract (`RiskStressTestOutput` Pydantic model with `RiskEntry` sub-model)
- Prompt rewritten from regex-parsed free-text to JSON-only output
- `node_risk_stress_test` migrated to `parse_structured_output` with regex fallback for loop-back fields
- `RiskCard` dashboard component (RR ratio ring, verdict callout, risk register cards with probability/impact/mitigation, loop-back footer)
- Integrated on pipeline runner page + report page with prose fallback for old runs
- Verify script: `python -m backend.scripts.verify_risk_parser` (11 tests)

### Bug fixes shipped along the way
- Removed ghost `transcript_analysis` phase from UI (it runs inside deep_dive, not as its own phase)
- Fixed autopopulate ticker + theme on `/pipeline/new` from URL params (theme detail CTA was broken)
- Fixed phase name → storage key mismatch in SSE interrupt events (`thesis_construction` → `thesis`, `risk_stress_test` → `risk`, `position_monitor` → `position`) — mapping lives in `PHASE_OUTPUT_KEYS` in `backend/app/services/pipeline.py`
- Fixed `nodes` import scope in `services/pipeline.py` (was local to `_run_phase`, moved to module-level)
- Removed `assistant_prefill` for Sonnet calls — Sonnet 4.6 doesn't support it (Haiku does)
- Relaxed Pydantic `max_length` constraints for thesis — Sonnet is verbose

---

## What's next

### Position Monitor (Phase 6) ✅
- Structured JSON contract (`PositionMonitorOutput` Pydantic model with `MonitoringItem` sub-model)
- Prompt rewritten from prose-style to JSON-only output
- `node_position_monitor` migrated to `parse_structured_output` with `assistant_prefill="{"` for Haiku
- `PositionCard` dashboard component (position size ring, entry zone card, stop loss/invalidation split, add triggers, monitoring schedule table, exit conditions)
- Integrated on pipeline runner page + report page with prose fallback for old runs
- Verify script: `python -m backend.scripts.verify_position_parser` (11 tests)

### Deep Dive (Phase 2) ✅
- Structured JSON contract (`DeepDiveCategoryOutput` Pydantic model with `DeepDiveFinding` sub-model) — one shared schema for all 9 categories
- Prompt rewritten from prose-style to JSON-only output with `analysis` field preserving full prose
- `_run_one_category` migrated to `parse_structured_output` with `assistant_prefill="{"` for Sonnet, regex fallback on parse failure
- `CategoryResult` gained optional `structured` field for serialization through state + SSE
- `DeepDiveCategoryCard` dashboard component (score rationale callout, key findings with evidence, analysis prose, data gap warnings)
- Integrated on report page with prose fallback for old runs; pipeline `DeepDiveCategoryGrid` unchanged (it's a progress view)
- Verify script: `python -m backend.scripts.verify_deep_dive_parser` (11 tests)

---

## Current state of main

```
27 commits on main ahead of origin/main (not pushed)
Branch: main at 7bf067b
Working tree: clean except ?? README.md (untracked)
docs/ is gitignored — design specs + plans live on disk locally but not in git
```

## Key files to know

| File | What it does |
|---|---|
| `backend/app/models/phase_schemas.py` | All Pydantic schemas — add new ones here |
| `backend/app/graph/output_parser.py` | Generic JSON parser — don't modify, just use |
| `backend/app/graph/prompts.py` | All LLM prompts — edit per-phase |
| `backend/app/graph/nodes.py` | All phase nodes — edit per-phase |
| `backend/app/graph/llm.py` | `complete()` helper — `assistant_prefill` works for Haiku only |
| `backend/app/services/pipeline.py` | Phase routing, SSE emit, `PHASE_OUTPUT_KEYS` mapping |
| `frontend/lib/api.ts` | All TypeScript types — add new structured types here |
| `frontend/app/pipeline/[runId]/page.tsx` | Pipeline runner — extend the render conditional |
| `frontend/app/report/[runId]/page.tsx` | Report page — extend per-phase SectionCards |
| `frontend/app/globals.css` | Theme tokens — use `--bg`, `--text`, `--primary`, `--success`, `--warning`, `--error` etc. |
