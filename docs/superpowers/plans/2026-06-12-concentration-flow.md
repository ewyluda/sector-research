# Concentration Flow Diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-hiding two-sided concentration flow diagram (suppliers → company → customers) inside the deep-dive `SupplyChainEcosystem` card, fed by `magnitude_pct` edges (including unnamed concentration disclosures), with latest-filing dedup.

**Architecture:** Pure adapter `frontend/lib/concentrationFlow.ts` (node-tested) + presentational `ConcentrationFlow.tsx` (hand-rolled SVG ribbons — NO d3-sankey dep) mounted above the type buckets in `SupplyChainEcosystem`, consuming the graph the card already fetched. Frontend-only.

**Spec:** `docs/superpowers/specs/2026-06-12-v3-graph-pack-design.md` item 3 (revised 2026-06-12). Live fixture: CRWV has 3 unnamed supplier bands (23/20/17%) duplicated across its 10-K and 10-Q — the dedup test case; NOK has 2.

---

### Task 1: Pure adapter (TDD)

**Files:** Create `frontend/lib/concentrationFlow.ts` + `frontend/lib/concentrationFlow.test.mts`.

Contract:

```ts
import type { SupplyChainGraphEdge, SupplyChainGraphNode } from "./api/filings.ts";

export interface FlowBand {
  label: string;            // counterparty ticker/name, or "Undisclosed supplier|customer", or "Other / undisclosed"
  pct: number;
  side: "supplier" | "customer";
  isOther: boolean;
  isUnnamed: boolean;
  quote: string | null;     // verbatim_quote (null for Other)
  filingDate: string | null; // null for Other
}

export interface ConcentrationFlowData {
  suppliers: FlowBand[];    // sorted pct desc, Other last
  customers: FlowBand[];
  eligible: boolean;        // ≥2 non-Other bands total across both sides
}

export function buildConcentrationFlow(
  nodes: SupplyChainGraphNode[],
  edges: SupplyChainGraphEdge[],
): ConcentrationFlowData
```

Rules (each pinned by a test):
1. Only edges with `direction === "out"`, `relationship_type ∈ {"supplier","customer"}`, `magnitude_pct != null` participate.
2. **Latest-filing dedup per side:** keep only edges whose `filing_date` equals the max `filing_date` among that side's participating edges. (CRWV case: 10-Q 2026-05-08 wins over 10-K 2026-03-02 → exactly 3 bands.)
3. Label: `unnamed` edge → `Undisclosed supplier|customer`; named → counterparty node's ticker (preferred) or name via `to_id` lookup in `nodes`.
4. Sort bands pct desc. If Σ(pct) < 100 on a non-empty side, append `Other / undisclosed` band with `100 − Σ` (isOther, no quote/date). If Σ ≥ 100, no Other band (and never negative).
5. `eligible` = total non-Other bands ≥ 2 (sides combined). Empty side = empty array (component renders single-sided).

Tests: CRWV-shaped dedup fixture (6 unnamed supplier edges across two filing dates → 3 bands + Other 40), named+unnamed mixed labeling, customer/supplier side split, direction-in excluded, non-supplier/customer types excluded, Σ>100 no-Other, Σ=100 exact no-Other, eligibility below-threshold (1 band → eligible false), empty input.

Run: `cd frontend && npm test && npm run typecheck`. Commit: `feat(frontend): concentration-flow adapter with latest-filing dedup`.

### Task 2: Component + mount

**Files:** Create `frontend/components/deep-dive/sections/ConcentrationFlow.tsx`; modify `frontend/components/deep-dive/sections/SupplyChainEcosystem.tsx` (mount above the type buckets, pass the fetched `graph`).

- `ConcentrationFlow({ graph }: { graph: SupplyChainGraph })` — `useMemo(buildConcentrationFlow)`; `if (!data.eligible) return null;` (self-hide, RPOTrend prior art).
- Hand-rolled SVG: three columns — supplier band rects (left), company node (center, labeled with the root ticker), customer band rects (right). Ribbon per band: cubic bezier filled path from band rect to the center node, thickness ∝ pct (suppliers flow left→center, customers center→right). Single-sided when one array is empty (company node shifts to the edge or stays center — implementer's choice, keep it simple).
- Colors: import `REL_TYPE_COLORS` from `@/lib/themeGraph` (supplier/customer entries); `Other` bands muted (`--color-text-muted`-ish fill at low opacity). Band label + pct% text; `<title>` tooltip with quote + filing date for non-Other bands.
- Heading inside the sub-section: "Disclosed concentration" + a one-line caption ("% of cost (suppliers) / revenue (customers) from the latest filing that quantifies concentration").
- Match the card's existing dark-token classes (`--color-*` namespace — copy from SupplyChainEcosystem).
- Gates: `npm run typecheck && npm run lint && npm test && npm run build`. Commit: `feat(frontend): concentration flow diagram in supply-chain card`.

### Task 3: Live verify + docs + PR

- Test DB: find a completed CRWV run (`SELECT id FROM research_runs WHERE ticker='CRWV' AND status IN ('completed','watchlist') ORDER BY created_at DESC LIMIT 1;` on `sector_research_test`), open `/pipeline/<run_id>`, scroll to Supply Chain — verify three supplier ribbons (23/20/17) + Other (40), tooltips, and that a no-magnitude ticker (e.g. NVDA run) hides the section.
- CLAUDE.md (deep-dive components list + Phase D consumer note) + TODO.md Done entry; PR; CI; merge.
