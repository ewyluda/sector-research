# E2E Findings 2026-05-12 — Triage & Spec Index

**Context:** The 2026-05-12 Playwright e2e run produced 8 BUG, 2 IMPROVEMENT, 8 POLISH findings in `docs/e2e-findings-2026-05-12/`. Each was validated against the live app (backend + frontend running locally) on 2026-05-12 evening. This file is the triage outcome.

## Real bugs → specs

| Finding | Severity | Spec |
|---|---|---|
| `GET /api/outcomes` returns 500 | high | [fix-outcomes-schema](2026-05-12-e2e-findings-fix-outcomes-schema.md) |
| Forecast model + reverse-DCF broken end-to-end | high | [fix-model-baseline-driver-keys](2026-05-12-e2e-findings-fix-model-baseline-driver-keys.md) |
| CORS rejects `http://127.0.0.1:3000` | med | [fix-cors-127001](2026-05-12-e2e-findings-fix-cors-127001.md) |

The driver-key fix subsumes 4 of the 8 BUG-tagged e2e items (ForecastGrid empty, ReverseDcfPanel missing, SensitivityHeatmap missing, ThesisVsPricedTable missing) — the panels render, but the data inside them is null because the model state has no usable forecast cells. Fixing the upstream LLM-prompt issue lights up all four panels in one move.

## Selector-mismatch findings (NOT bugs)

The following findings reproduced as "not visible" / "not found" against test selectors but rendered correctly in the live browser session. Root cause: components have no `data-*` instrumentation, so the e2e suite fell back to brittle `[class*="ComponentName"]` heuristics that never match Tailwind class lists.

- (deep-dive-sections) No score chips found — scores render as `92/100`, `88/100`, `72/100` etc.
- (deep-dive-sections × 6) Section X has 0 AICompanionPanel — every `DataRichSection` renders both `section="summary"` and `section="analysis"` panels per the CLAUDE.md contract.
- (deep-dive-sections) SupplyChainEcosystem has no "Explore 2-hop graph" link — link is present at `/filings/graph?root=NVDA`.
- (themes-discovery) Neo-clouds rendered no company cards — all 7 tickers (CRWV, IREN, ORCL, NBIS, CIFR, APLD, WYFI) render.
- (financial-model) No driver cells found on ForecastGrid — cells render; `data-cell-path` attribute is absent.
- (reverse-dcf × 3) ReverseDcfPanel / SensitivityHeatmap / ThesisVsPricedTable not visible — all render; they're empty because of the driver-key bug above, but visible.
- (reverse-dcf) No price-override input — input *is* present.
- (pipeline-existing-run) SectionNav pill did not appear active — IntersectionObserver scroll-spy works; "Risk" pill goes active when `#risk_assessment` enters view.
- (global-shell) Console error on 404 — browser's native diagnostic for the page's 404 response; not an app issue.

Fix: add `data-*` attributes — see [test-instrumentation-attrs](2026-05-12-e2e-findings-test-instrumentation-attrs.md).

## Notes & deferrals

- (filings-graph) No ticker filing cards — expected; run `POST /api/filings/ingest/{ticker}` for at least one ticker before this test. The e2e suite itself should bootstrap this fixture rather than report it.
- (deep-dive-sections) WhatChangedPanel not on this run — expected; the run pre-dates the transcript-delta feature. Not a bug.
- (secondary-surfaces) No read-through CTA — possibly empty fixture, possibly missing CTA. Re-test once the status board has a queued read-through; otherwise no action.

## Execution order

If only one thing ships: **fix the driver-key bug**. It blocks the entire financial-model workflow for every ticker. The outcomes 500 only blocks `/performance` (one page). The CORS issue only bites users on `127.0.0.1:3000` (a workaround exists). The instrumentation work is a force-multiplier for future e2e runs but doesn't change current behavior.

Suggested PR sequence:
1. `fix-outcomes-schema` — smallest blast radius, unblocks `/performance`.
2. `fix-cors-127001` — one-line config change.
3. `fix-model-baseline-driver-keys` — invasive prompt + Pydantic change + data backfill, plus the most upside.
4. `test-instrumentation-attrs` — quality-of-life for the next e2e run; can land alongside or after the bug fixes.
