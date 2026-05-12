# Other Design Options Considered

This document records alternatives evaluated during the Quick Screen phase-output formatting brainstorm (2026-04-11) but not selected. Kept for future reference if we want to revisit these decisions or migrate to them later.

Every decision below has a chosen direction documented in the matching spec at `docs/superpowers/specs/2026-04-11-phase-output-formatting-design.md`. This file only records what we deliberately left on the table.

---

## Q1 · Scope

**Chose:** B — Quick Screen + establish reusable pattern (solve Quick Screen, build the parse → validate → store → render infrastructure so Deep Dive / Thesis / Risk / Position can migrate later).

### Alternatives not selected

- **A. Just Quick Screen (point fix)** — Ship the narrowest possible change for the one phase on screen. Rejected because the problem is structurally identical across all six non-streaming phases; a point fix is throwaway work once we're ready to improve the others.
- **C. All six phases at once (big bang)** — Redesign every phase's output contract and renderer in one plan. Rejected as too large a design surface, too many unknowns, too much risk of patterns propagating before they've been validated on a single phase.

---

## Q2 · Output Contract

**Chose:** B — Structured JSON schema + dedicated React components (Haiku emits JSON, backend validates via Pydantic, frontend renders with purpose-built components).

### Alternatives not selected

- **A. Keep prose, render as markdown.** Lowest-effort path — change the prompt to request explicit markdown, install `react-markdown` + `remark-gfm`, render it. Rejected because LLM formatting discipline is fragile: any drift in Haiku's output breaks the UI silently, and you can't get real tables/charts without hacking markdown. Worth remembering as a fallback rendering path if the structured parser fails.
- **C. Hybrid — prose body + structured sidecar.** LLM emits structured JSON for dimension scores and the verdict, but keeps prose for the thesis paragraph and key risk note. Two contracts instead of one. Rejected as a false economy — you can put prose fields (`thesis: str`, `key_risk: str`) inside a structured JSON without losing anything, so the "prose helps here" argument doesn't survive scrutiny. The complexity of two parsers is never worth it.

---

## Q3 · Visual Direction

**Chose:** A — Dashboard layout with score ring + inline-bar data table + thesis/risk callout boxes side-by-side.

### Alternatives not selected

- **B. Card Grid — dimension tiles.** Five dimension cards in a horizontal grid with big numeric scores and truncated rationales. Scannable and modern-SaaS-feeling, but loses the wider rationale text and doesn't compare dimensions as cleanly as a table. **Keep in mind for:** a future mobile view, or a compact Library-level preview of Quick Screen results where detail matters less.
- **C. Executive Brief — TL;DR block + horizontal bars.** Narrative memo layout: verdict + thesis at the top in a callout, dimensions as stacked horizontal bars, risk at the bottom. Reads like a human analyst's note. **Keep in mind for:** the Thesis Construction and Position Plan phases where prose is more central to the output — the executive-brief framing may fit those better than a dashboard.

Mockups for all three options live in `.superpowers/brainstorm/53616-1775930468/content/quick-screen-layouts.html` (persisted in the repo for future reference).

---

## Q4 · Citations Placement

**Chose:** A — Footer row of tier-badged chips, matching the existing report page pattern.

### Alternatives not selected

- **B. Inline per-dimension footnote marks.** Each dimension table row gets a superscript footnote reference (`[¹]`) next to its rationale, with the full citation list rendered in a footer. Academically correct and highly discoverable. Rejected for this iteration because the backend doesn't currently track which FMP data source (income / balance / cash-flow / profile) contributed to which scoring dimension — the 5 dimensions are LLM-synthesised from a pooled data blob. Implementing this cleanly requires either the LLM emitting per-dimension source IDs in its JSON output, or the data-fetch layer tagging calls with dimension intent. **Revisit when:** users start asking "which source backs this specific claim?" frequently, or when we need auditable citations for compliance/review workflows. The chosen JSON schema should reserve space for a future optional `sources: [citation_id]` field on each dimension so this is a non-breaking upgrade.
- **C. Hover tooltips on score cells.** Source chips appear in a tooltip when hovering a dimension's score. Visually tidy but hostile to keyboard-only users and screen readers, and still requires the same dimension↔source mapping as option B. Rejected on accessibility grounds alone; the mapping issue is a second strike.

---

## Deferred — ideas worth remembering but explicitly out of scope

- **Dimension score sparklines.** Show the 5 dimension scores with a small trend line comparing to prior research runs for the same ticker. Needs historical run comparison — not wired up today.
- **Approve-with-edit.** Let the user inline-edit the thesis text at the interrupt before continuing. Would require the advance endpoint to accept a thesis override and the JSON contract to treat `thesis` as mutable.
- **Raw LLM output toggle.** A "show raw" toggle for debugging that reveals the unparsed Haiku response. Useful during development; not worth wiring into the stable UX.
- **Per-dimension citation mapping.** The backend change that would unlock option B in Q4. Requires either LLM-emitted source IDs per dimension or explicit tagging in the data-fetch layer.
- **Streaming partial JSON.** Current Quick Screen uses `complete()` (non-streaming). Streaming partial JSON is possible but doesn't render usefully — UI can't show half a dimension. Not worth pursuing for this phase.
