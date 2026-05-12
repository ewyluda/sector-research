# Tier 1.1 — Thesis Enrichment

**Date:** 2026-05-03
**Parent roadmap:** `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md`
**Exoskeleton step:** Step 8 — Thesis Construction (sub-actions: Pre-Mortem, Kill Criteria, Catalyst Map)
**Status:** Design approved, ready for implementation plan

---

## Context

This is the first sub-project from the framework improvements roadmap. The current `thesis_construction` phase (Sonnet, `backend/app/graph/nodes.py:1218`) produces a structured thesis with `core_thesis`, `bull_case`, `bear_case`, `variant_perception`, `catalysts`, `conviction_score`, `conviction_rationale`. The exoskeleton's Step 8 also calls for **pre-mortem**, **kill criteria**, and a richer **catalyst map** — none of which are currently captured.

This spec adds those three to the existing thesis output. It is deliberately scoped narrow: schema + prompt + minimal frontend surfacing. Programmatic consumption (e.g., flagging when a kill criterion fires) is left for Tier 2.5 (earnings navigator) and Tier 2.6 (status board).

## Strategic decisions captured upstream

- **Generation strategy:** Single Sonnet call. Extend the existing `THESIS_SYSTEM` / `THESIS_USER` prompts; do not add a new pipeline node.
- **Schema shape:** Structured (not free-text) for kill criteria and catalysts so downstream tiers can consume them programmatically. Pre-mortem is lighter (analyst self-reflection, not a programmatic trigger).
- **Frontend:** F2 — collapsible accordions inside `ThesisCard` for the new fields; inline enrichment of `CatalystList`; pillar-link chips that highlight `BullBearColumns` on hover.
- **Backwards compatibility:** All new fields optional. Old runs render without errors.

## Architecture

- **No new pipeline nodes.** Extend `node_thesis_construction` in `backend/app/graph/nodes.py:1218`. No edge changes in `pipeline.py`.
- **No new DB tables / no Alembic migration.** New fields persist via the existing JSONB at `state.phase_outputs["thesis"].structured`.
- **No new frontend pages or routes.** Changes are confined to `ThesisCard.tsx`, `CatalystList.tsx`, `BullBearColumns.tsx`, and `lib/api.ts`.
- **No new dependencies** on either side.

## Schema

All Pydantic models live in `backend/app/models/phase_schemas.py` alongside the existing `ThesisOutput`, `ThesisPoint`, and `Catalyst`. The existing `Catalyst` class is extended in place; three new classes (`KillCriterion`, `FailureMode`, `PreMortem`) are added.

```python
from typing import Literal
from pydantic import BaseModel, Field

# ── EXTENDED in place (was: timeframe + description only) ──
class Catalyst(BaseModel):
    timeframe: str = Field(..., min_length=1, max_length=60)
    description: str = Field(..., min_length=1, max_length=600)
    type: Literal["earnings", "product", "regulatory", "m_and_a", "macro", "other"] | None = None
    signposts: list[str] = Field(default_factory=list, max_length=3)
    linked_pillar: str | None = Field(default=None, pattern=r"^(bull|bear):[1-5]$")

# ── NEW ──
class KillCriterion(BaseModel):
    condition: str = Field(..., min_length=1, max_length=300)
    threshold: str = Field(..., min_length=1, max_length=300)         # observable trigger
    monitoring_source: str = Field(..., min_length=1, max_length=200) # where it's observed
    kills_pillar: str | None = Field(default=None, pattern=r"^(bull|bear):[1-5]$")

class FailureMode(BaseModel):
    mode: str = Field(..., min_length=1, max_length=300)
    leading_indicator: str = Field(..., min_length=1, max_length=300)
    probability: Literal["Low", "Medium", "High"]

class PreMortem(BaseModel):
    framing: str = Field(..., min_length=1, max_length=300)
    failure_modes: list[FailureMode] = Field(..., min_length=3, max_length=5)

# ── ThesisOutput: two new fields, both optional for backwards compat ──
class ThesisOutput(BaseModel):
    # unchanged fields...
    catalysts: list[Catalyst] = Field(..., min_length=3, max_length=5)  # same constraint, richer Catalyst
    kill_criteria: list[KillCriterion] = Field(default_factory=list, max_length=5)  # NEW; 0–5
    pre_mortem: PreMortem | None = None                                              # NEW
```

**Field count rationale.** `kill_criteria` is `default_factory=list` (not required `min_length=3`) so old runs and parse-fallback paths don't crash on empty. Sonnet is instructed in the prompt to produce 3–5 criteria, but missing data is treated as a soft signal, not a hard validation error.

**Pillar reference convention.** `linked_pillar` and `kills_pillar` use the string format `"bull:N"` or `"bear:N"` where `N` is 1-indexed into `bull_case` / `bear_case` (which themselves cap at length 5 — hence the regex `^(bull|bear):[1-5]$`). Pydantic rejects malformed values; Sonnet is instructed via the prompt.

## Prompt changes (`THESIS_SYSTEM` in `backend/app/graph/prompts.py:180`)

Extend the existing prompt with:

1. **Updated JSON schema spec** showing the three new fields with field-level guidance.
2. **Catalyst calibration rules:**
   - `type` must use one of the enumerated literals.
   - `signposts` are leading indicators ("what we'd see first") — concrete and observable, 1–3 per catalyst.
   - `linked_pillar` is optional but encouraged when the catalyst directly tests a bull/bear point.
3. **Kill criteria calibration rules:**
   - 3–5 criteria. Each must be falsifiable.
   - `threshold` must specify a numeric/observable trigger, not a feeling. Reject "if competition increases" — require "if market share drops below X% for 2 consecutive quarters."
   - `monitoring_source` must name the document or feed where the trigger is observed (10-Q, transcript, EDGAR XBRL, etc.).
4. **Pre-mortem calibration rules:**
   - Framing is fixed: "Imagine it's 18 months from now and this thesis is dead. What killed it?"
   - 3–5 failure modes. Each `mode` is a concrete cause; each `leading_indicator` is what we'd see first.
   - `probability` reflects today's odds of that specific failure mode materialising.
5. **Pillar-reference instruction:** "Use 'bull:N' or 'bear:N' where N is the 1-indexed position in `bull_case` / `bear_case`. Use null if no specific pillar applies."

`max_tokens` in the `complete()` call increases from 4000 → 6000 to absorb the additional structured output. Current thesis outputs land around 1.5K tokens; the new fields add ~1.5K worst case, leaving comfortable headroom.

## Backend changes summary

- `backend/app/graph/prompts.py` — extend `THESIS_SYSTEM` JSON spec + calibration rules.
- `backend/app/models/phase_schemas.py` — extend the existing `Catalyst` class with `type`, `signposts`, `linked_pillar`; add `KillCriterion`, `FailureMode`, `PreMortem`; add `kill_criteria` and `pre_mortem` to `ThesisOutput`.
- `backend/app/graph/nodes.py:1218` (`node_thesis_construction`) — bump `max_tokens=6000`. No other logic changes.
- `parse_structured_output` continues to handle parse failures the same way (text fallback).

## Frontend changes summary

- `frontend/lib/api.ts` — extend the `ThesisOutput` TypeScript type with the new optional fields and the new catalyst shape.
- `frontend/components/ThesisCard.tsx` — render two collapsible sections below the existing thesis content:
  - **"Kill criteria"** — list of `{condition, threshold, monitoring_source}` rows; if `kills_pillar` set, render a small `kills bull:N` chip.
  - **"Pre-mortem"** — framing line + list of failure modes with probability badge.
  - Use existing `usePersistedCollapse` hook (`components/deep-dive/usePersistedCollapse.ts`) — keys `sr:collapse:thesis-kill-criteria` and `sr:collapse:thesis-pre-mortem`. Default collapsed.
- `frontend/components/CatalystList.tsx`:
  - Render `type` as a small colored chip next to the timeframe.
  - Add an expand-toggle that reveals `signposts` as a bulleted list.
  - If `linked_pillar` is set, render a small chip linking to that pillar.
- `frontend/components/BullBearColumns.tsx` — accept optional `highlightedPillar?: string | null` prop. When set, the matching `bull:N` / `bear:N` card gets a ring/glow class. The chip-hover handler in `ThesisCard` and `CatalystList` lifts state up (likely a small piece of state in the parent that owns both children) to set/clear `highlightedPillar`.

No `sections.ts` changes. No new components. No new icons or libraries.

## Backwards compatibility

- New Pydantic fields all have defaults (`[]` or `None`), so old `phase_outputs["thesis"].structured` payloads parse without error.
- Frontend renders new sections only when fields are present and non-empty. An old run shows the existing `ThesisCard` exactly as today.
- No DB migration; no client-side migration.

## Loop scenario

When `node_risk_stress_test` returns `loop_required=true`, the pipeline routes back through deep_dive and re-runs `node_thesis_construction`. The full `phase_outputs["thesis"]` is overwritten as today, including the new fields. Pre-mortem and kill criteria regenerate against the updated evidence. No special handling needed.

## Definition of done

1. New thesis runs include `catalysts[].type`, `catalysts[].signposts`, `kill_criteria`, and `pre_mortem` populated by Sonnet.
2. `ThesisCard` renders kill criteria and pre-mortem as collapsible sections; both default collapsed; toggling persists per-section across reloads.
3. `CatalystList` shows the type badge inline and reveals signposts on expand.
4. Hovering a `kills bull:2` or `linked bull:1` chip highlights the corresponding card in `BullBearColumns`.
5. An old run (no new fields) renders without runtime errors and without empty placeholders.
6. `parse_structured_output` succeeds on a sample new payload; the existing fallback path still handles parse failures.
7. `frontend/lib/api.ts` types match the backend Pydantic shapes; `npm run lint` passes.

## Out of scope

- **Risk node consumption** of kill criteria (later refinement of `node_risk_stress_test` to reference them).
- **Programmatic kill-criteria evaluation** against incoming 10-Qs/transcripts (Tier 2.5 earnings navigator + Tier 2.6 status board).
- **Status board** surfacing kill-criteria health and catalyst proximity (Tier 2.6).
- **Catalyst calendar / timeline view** (Tier 1.3).
- **Linking catalysts to actual FMP earnings dates** (Tier 1.3).
- **Tests.** No test framework is configured for the backend per `CLAUDE.md`. Verification is manual: run a thesis on a known ticker, inspect the structured output, view the report page.

## Open questions / risks

- **Sonnet calibration on `kill_criteria.threshold`.** First runs may produce vague thresholds despite the calibration rules; if so, tighten the prompt with a one-shot example. Track during implementation.
- **Pillar-reference index correctness.** Sonnet must keep its own bull/bear ordering in mind when emitting `"bull:2"`. Verify on first runs; if it drifts, add a post-parse validation step that checks `N` is in range.
- **`max_tokens=6000` headroom.** If outputs occasionally hit the cap, bump to 8000.
