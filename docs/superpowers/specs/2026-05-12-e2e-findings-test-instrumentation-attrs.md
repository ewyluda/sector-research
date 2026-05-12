# Add: Test-instrumentation `data-*` attributes to deep-dive & model components

**Source:** Meta-finding from 2026-05-12 e2e run. Eight of the 18 e2e findings turned out to be selector mismatches, not application bugs. Components render correctly but expose no stable selectors for tests.

**Status:** Not a bug — an architectural decision the project has been quietly deferring.

## Problem

The Playwright e2e suite ships a healthy set of assertions (score chips, AICompanionPanel pairs, ForecastGrid drivers, ReverseDcfPanel, SensitivityHeatmap, ThesisVsPricedTable, SupplyChainEcosystem explore link, company cards on theme pages), but the components it asserts against have **no `data-*` attributes**. The tests fall back to brittle CSS heuristics like `[class*="AICompanionPanel"]` — which never matches because Tailwind utility classes don't include component names.

Result: every component listed above showed up in the 2026-05-12 findings as a "bug" even though all of them render correctly in the live app. Of the 8 BUG-tagged items in `docs/e2e-findings-2026-05-12/`, exactly 2 were real (outcomes 500, AI-baseline driver-key mismatch); the other 6 were the test failing to *find* a working component.

This is a process bug, not a component bug — but it makes the e2e suite an unreliable gate. Either we trust the suite (and chase ghosts every run), or we ignore the suite (and lose the real signal when it does find a regression).

## Proposed instrumentation

Add a thin, stable `data-*` layer to the components the e2e suite already targets. Naming convention: `data-testid="<component-kebab>"` for component-root selectors; `data-section="<id>"` mirroring `sections.ts` ids for the deep-dive section shells (so a single selector finds them).

### Deep-dive section shell

`frontend/components/deep-dive/sections/DataRichSection.tsx:22` and `MixedSection.tsx:22`:

```tsx
<section
  id={id}
  data-section={id}                       // new
  data-section-kind="data-rich"           // new (one of: data-rich | mixed | qualitative)
  className="..."
>
```

Effect: `[data-section]` returns every deep-dive section; `[data-section-kind="data-rich"]` returns the subset that should have 2 AICompanionPanels.

### AICompanionPanel

`frontend/components/deep-dive/panels/AICompanionPanel.tsx:50` (fallback root) and `:86` (structured root):

```tsx
<div data-testid="ai-companion" data-companion-section={section}>
```

Effect: `[data-testid="ai-companion"]` returns every render; `[data-companion-section="summary"]` and `[data-companion-section="analysis"]` distinguish the two-panel-per-section contract.

### Score chip

The chip lives in `DataRichSection.tsx:29` (and the matching place in `MixedSection`). Add:

```tsx
<span data-testid="score-chip" data-section-id={id} className={...}>
  {score != null ? `${score}/100` : "—"}
</span>
```

Effect: `[data-testid="score-chip"]` is the count the test was reaching for; `[data-section-id]` lets the test assert the per-section value.

### ForecastGrid driver cells

`frontend/components/model/CellRenderer.tsx:26` `<td>` — the e2e test explicitly looked for `[data-cell-path]`:

```tsx
<td
  data-cell-path={cellPath}
  data-cell-source={source}
  onClick={...}
  ...
>
```

This is the highest-value attribute on the list — `cellPath` is already a stable string and the test depends on it.

### Reverse-DCF panel roots

`frontend/components/model/ReverseDcfPanel.tsx`, `SensitivityHeatmap.tsx`, `ThesisVsPricedTable.tsx`, `WhatIfScratchPanel.tsx`: add `data-testid` on the outer container:

```tsx
<section data-testid="reverse-dcf-panel">...
<section data-testid="sensitivity-heatmap">...
<section data-testid="thesis-vs-priced-table">...
<section data-testid="whatif-scratch-panel">...
```

### SupplyChainEcosystem "Explore 2-hop" link

`frontend/components/deep-dive/sections/SupplyChainEcosystem.tsx`: add `data-testid="explore-2hop-link"` on the `<a>` whose text starts with "Explore 2-hop graph".

### Theme detail company cards

The `/theme/[id]` page renders `CompanySignalCard`s for each ranked company. Whatever component owns that card needs `data-testid="company-card" data-ticker={ticker}` on the root. (The e2e test was reaching for exactly `[data-company-card], [data-ticker]`.)

## What this is NOT

- Not styling. No visual change.
- Not API. No backend change.
- Not new behavior. Components already render correctly; this is purely making them *findable*.
- Not a test framework choice. Same Playwright suite, same selectors — it just stops grepping for class-name substrings.

## Verification

1. Re-run the e2e suite end-to-end against this branch. The "no score chips," "0 AICompanionPanel," "ForecastGrid empty," "ReverseDcfPanel not visible," "SensitivityHeatmap not visible," "ThesisVsPricedTable not visible," "SupplyChainEcosystem has no Explore link," and "Neo-clouds rendered no company cards" findings should all flip green.
2. The two real bugs (`/api/outcomes` 500 and AI-baseline driver-key mismatch — see the sibling specs) should remain red until their own fixes land. That's the test gate working as intended.

## Out of scope

- Adding a sweeping `data-testid` to every component in the codebase. Stay surgical: only what the existing e2e suite already asserts on.
- Making the e2e suite stricter. Once the suite reliably distinguishes "component missing" from "component present but selector failed," we can talk about adding more assertions. Not now.
- Replacing the e2e suite framework. Playwright is fine; the issue is the selectors, not the runner.
