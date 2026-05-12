# Framework Improvements Roadmap

**Date:** 2026-05-03
**Status:** Strategic decomposition — each tier item is its own spec
**Source:** `docs/13-step-exoskeleton.md`

---

## Context

This is a strategic audit of the current `sector-research` framework against the institutional equity research process described in `docs/13-step-exoskeleton.md`. The exoskeleton has 13 steps split into a thesis-development arc (1–8) and active position management (9–13), plus two AI-framing slides: Slide 23 (push-button workflows, accretion/dilution example) and Slide 46 (5-step model workspace from *Fundamental Edge*).

The output is a prioritized 3–6 month roadmap, decomposed into independent sub-projects. Each Tier item gets its own brainstorm → spec → implementation cycle.

The earlier `docs/2026-05-03-model-workspace-plan.md` is absorbed into Tier 3 of this roadmap, not deleted — it remains the canonical implementation reference for items 7–9 below.

## Strategic decisions

- **Primary focus: A + B** — DD pipeline excellence (steps 1–8) plus post-thesis fleet management (steps 9–13). The 6-month vision is "thesis-grade write-up faster than I could do manually" *and* "10–20 names with live theses, system tells me when to revisit."
- **Step 4 (Financial Model Build) is committed**, not deferred. Originally bucketed as "nice to have" (push-button modeling, slide 23), but Step 4 is the keystone for both A's reverse DCF and B's workspace loop. Building it lights up Tier 3.
- **Time horizon: 3–6 months.** Bigger swings allowed in later tiers; no quick-wins-only constraint.
- **Idea origination upgrades (Step 1) and news/event navigation (Step 12) are deferred** — they fit bucket D and lower-priority parts of B, respectively, and are not on the critical path for the 6-month vision.

## Coverage audit

Current implementation coverage scored against each step's sub-actions in the exoskeleton. Impact is scored separately for the A bucket (DD pipeline excellence) and B bucket (post-thesis fleet).

| Step | Current % | Gap | A impact | B impact | Effort |
|---|---|---|---|---|---|
| 1. Idea Origination | ~50% | Read-throughs, 13F overlap, short ID, alt data | M | M | M |
| 2. Triage | ~60% | Explicit kill criteria, crowding/ownership | M | M | S |
| 3. Foundational DD | ~65% | **Question log**, sell-side, ownership | **H** | M | M |
| 4. Financial Model Build | ~10% | **Editable model — P&L/BS/CF/drivers** | **H** | **H** | L |
| 5. Key Driver Deep Dive | ~30% | Hypothesis-driven targeted second pass | **H** | M | M |
| 6. Insight Formation | ~70% | Confidence + info gaps schema | M | M | S |
| 7. Expectations & Valuation | ~30% | **Reverse DCF, what's priced in, peer comps** | **H** | M | M (after model) |
| 8. Thesis Construction | ~70% | **Pre-mortem, kill criteria, catalyst map** | **H** | **H** | S |
| 9. Catalyst Path | ~5% | **Catalyst calendar + signposts** | L | **H** | M |
| 10. Earnings Navigation | ~10% | Full quarterly cycle UX | L | **H** | L |
| 11. Mgmt Touchpoints | ~25% | Credibility tracker, red flags | L | M | M |
| 12. News/Event Nav | ~20% | News ingest, materiality, peer alerts | L | M | L |
| 13. Position Management | ~20% | R/R recalc, exits, post-mortem, **status board** | L | **H** | M (after model) |
| Slide 23 push-button | 0% | Accretion/dilution, reverse DCF, sensitivity templates | M | M | L per template |
| Slide 46 workspace loop | 0% | 5-step recurring loop | M | **H** | XL |

## Step 4 keystone rationale

Step 4 (Financial Model Build) was originally low priority in the user's bucket framing (C "nice to have"). The audit surfaces a tension: Step 4 is the gating dependency for the deepest expressions of *both* A and B.

- **A's "thesis-grade write-up"** — the punchline of a real institutional thesis is reverse DCF and "what's priced in" (Step 7). Both require a model. Without one, A produces strong qualitative analysis but cannot decompose price into expectations.
- **B's "stress-test conviction quarterly"** — the workspace 5-step loop, position-level R/R recalc (Step 13), and the post-earnings re-value (Step 10) all assume an editable model with audit-trail cells.

The decision: **build the model.** Tier 3 is committed. The "minimum viable model" for unlocking Steps 7 and 13 is narrower than the full workspace plan (e.g., P&L forecast + driver inputs may be enough for reverse DCF without full BS/CF/SUM). Scope of the minimum model is settled in Tier 3's own spec.

## Prioritized roadmap

### Tier 1 — Quick wins, no model dependency *(weeks)*

1. **Step 8 thesis enrichment** *(this is the next sub-project — see below)*
   Add pre-mortem, kill criteria, catalyst map fields to thesis output.
   *Effort: S. Foundation for Tier 2 status board (kill criteria + catalyst become health signals).*

2. **Question log + targeted second-pass deep dive** (Steps 3 + 5)
   LLM extracts open questions during deep dive; a second targeted pass addresses the highest-priority unknowns.
   *Effort: M. Biggest A-bucket impact for the effort.*

3. **Catalyst calendar + signposts** (Step 9)
   First-class `Catalyst` object with date, type, signposts, source. Surfaced per-ticker and aggregated across the fleet.
   *Effort: M. Foundation for B; standalone of Tier 1.1.*

4. **Read-through engine on supply-chain graph** (Steps 1 + 9)
   When peer ticker reports / news drops, flag held theses with a graph-edge to that peer. Re-uses existing relationship + supply-chain infra.
   *Effort: M. Free leverage from infra already shipped.*

### Tier 2 — Bigger swings, light model dependency *(months)*

5. **Earnings cycle navigator** (Step 10)
   Pre-earnings expectations cluster (consensus, key metrics, scenarios) → post-print parser → thesis-check verdict (does the print confirm/threaten the thesis?). Doesn't strictly need a model — a diff vs. consensus is enough for v1.
   *Effort: L. B's flagship feature.*

6. **Live thesis status board** (Step 13)
   Aggregate view of all theses with health status, kill-criteria flags, catalyst proximity, last-updated freshness. Consumes outputs from Tier 1.1 (kill criteria, catalysts) and Tier 1.3 (calendar).
   *Effort: M. B's "fleet view."*

### Tier 3 — The keystone *(quarter)*

7. **Editable financial model** (Step 4)
   Minimum viable: P&L forecast + driver inputs with audit-trail cells (`ModelCell` per the workspace plan). Full BS/CF/SUM is scope-decided in this item's own spec.
   *Effort: L. Gates 8 and 9 below.*

8. **Reverse DCF + what's priced in** (Step 7)
   Solver decomposes current price into implied growth/margin/multiple assumptions; presents alongside thesis baseline.
   *Effort: M (after model). Punchline of A's thesis-grade write-up.*

9. **Workspace 5-step loop** (Slide 46)
   Update/Refresh → Research → Validation/Sensitivity → Challenge/Sharpen → Differentiation, as drafted in `docs/2026-05-03-model-workspace-plan.md`.
   *Effort: XL (after model). The full B-bucket experience.*

### Tier 4 — Deferred

- Step 11 management credibility tracker (red flags, delivery vs. promises) — moderate value, not on critical path.
- Step 12 news + event navigation — gated on news source quality/cost.
- Step 1 short ID, alt data, idea sourcing upgrades — D-bucket, not in current focus.
- Step 3 sell-side / investor deck integrations — costly to source.

Revisit Tier 4 if scope expands or a higher-priority dependency emerges.

## Dependency sequencing

```
Tier 1.1 (thesis enrichment) ──┐
                                ├──> Tier 2.6 (status board)
Tier 1.3 (catalyst calendar) ──┘

Tier 1.2 (question log) ──────────> independent of Tier 2

Tier 1.4 (read-through engine) ──> independent of Tier 2 (informs status board if shipped before)

Tier 3.7 (model) ──┬──> Tier 3.8 (reverse DCF)
                   └──> Tier 3.9 (workspace loop)

Tier 2.5 (earnings navigator) ───> can ship without model; deepens after Tier 3.7
Tier 2.6 (status board) ─────────> deepens with Tier 3.8 (R/R recalc) and Tier 3.9 (workspace)
```

Tier 1 items are independent of each other and can ship in any order or in parallel. Tier 2 items depend on Tier 1.1 and 1.3. Tier 3.8 and 3.9 depend on Tier 3.7. Tier 2 features are usable without Tier 3 but become more powerful once the model exists.

## Definition of done per tier

- **Tier 1 done:** Thesis output is richer (pre-mortem, kill criteria, catalysts), gaps are explicit (question log + targeted second pass), catalysts are tracked per ticker, peer signals propagate via supply-chain edges.
- **Tier 2 done:** Post-thesis fleet of 10–20 names is observable and quarterly-updated. Earnings cycle has a real workflow per ticker. Status board is the daily home view.
- **Tier 3 done:** Full A and B coverage with model-backed analytical depth. Reverse DCF on every thesis. Workspace 5-step loop is the recurring post-earnings ritual.

## Next steps

1. **Tier 1.1 — Thesis enrichment** is the first sub-project. After this roadmap doc commits, re-enter the brainstorming flow scoped to that item: define the pre-mortem prompt structure, kill criteria schema, catalyst map schema, prompt deduplication, and any frontend surfaces.
2. Each subsequent Tier item enters the same flow: brainstorming → spec in `docs/superpowers/specs/` → writing-plans → execution.
3. Tier 4 items revisit if scope expands or a dependency emerges.
4. The model-workspace-plan (`docs/2026-05-03-model-workspace-plan.md`) remains the implementation reference for Tier 3 items 7–9; its 8 open questions get answered when those specs are written, not now.
