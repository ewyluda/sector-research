# E2E Findings — 2026-05-12T21:53:45.411Z

## Counts
- bugs: 8
- polish: 8
- improvements: 2
- notes: 4

## All bugs
- (deep-dive-sections) No score chips found on report
- (financial-model) No driver cells found on ForecastGrid
- (global-shell) Console error: Failed to load resource: the server responded with a status of 404 (Not Found)
- (reverse-dcf) ReverseDcfPanel not visible on /model/NVDA#reverse-dcf
- (reverse-dcf) SensitivityHeatmap not visible on /model/NVDA#reverse-dcf
- (reverse-dcf) ThesisVsPricedTable not visible on /model/NVDA#reverse-dcf
- (secondary-surfaces) GET /api/outcomes → 500: Pydantic response validation fails on `narrative` field
- (themes-discovery) Theme "Neo-clouds" rendered no company cards

## All improvement opportunities
- (deep-dive-sections) SupplyChainEcosystem card has no "Explore 2-hop graph" link
- (reverse-dcf) No price-override input visible on reverse-DCF tab

## All polish notes
- (deep-dive-sections) Section "financial_health" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (deep-dive-sections) Section "growth_earnings" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (deep-dive-sections) Section "technical_market_structure" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (deep-dive-sections) Section "cross_category" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (deep-dive-sections) Section "business_quality" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (deep-dive-sections) Section "macro_regime" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
- (global-shell) Backend CORS allow-list excludes `http://127.0.0.1:3000`
- (pipeline-existing-run) SectionNav pill did not appear active for the scrolled-to section

## Surfaces
- [deep-dive-sections](#deep-dive-sections)
- [filings-graph](#filings-graph)
- [financial-model](#financial-model)
- [global-shell](#global-shell)
- [pipeline-existing-run](#pipeline-existing-run)
- [reverse-dcf](#reverse-dcf)
- [secondary-surfaces](#secondary-surfaces)
- [themes-discovery](#themes-discovery)

---

## deep-dive-sections

- **BUG [med]** — No score chips found on report
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Screenshot: `test-results/05-deep-dive-sections-scor-9e3a2-ic-scores-not-all-em-dashes-chromium/no-chips.png`
  - Check OverviewBanner / DataRichSection rendering. May be a scoreKeys.ts normalize issue.
- **POLISH [med]** — Section "financial_health" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **POLISH [med]** — Section "growth_earnings" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **POLISH [med]** — Section "technical_market_structure" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **POLISH [med]** — Section "cross_category" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **POLISH [med]** — Section "business_quality" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **POLISH [med]** — Section "macro_regime" has charts but only 0 AICompanionPanel — expect 2 (summary + analysis)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.
- **IMPROVEMENT [low]** — SupplyChainEcosystem card has no "Explore 2-hop graph" link
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
- **NOTE** — WhatChangedPanel not on this run (likely no transcript delta yet)
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - New feature — confirm transcript_delta service ran for this ticker.


## filings-graph

- **NOTE** — No ticker filing cards present
  - URL: `http://localhost:3000/filings`
  - Run POST /api/filings/ingest/<TICKER> for at least one ticker before this test.


## financial-model

- **BUG [high]** — No driver cells found on ForecastGrid
  - URL: `http://localhost:3000/model/NVDA#forecast`
  - Check DriverPanel + ForecastGrid wiring of data-cell-path attributes.


## global-shell

- **BUG [med]** — Console error: Failed to load resource: the server responded with a status of 404 (Not Found)
  - URL: `http://localhost:3000/this-route-does-not-exist`
- **POLISH [med]** — Backend CORS allow-list excludes `http://127.0.0.1:3000`
  - URL: `http://127.0.0.1:3000/*`
  - `backend/app/config.py:37` defines `cors_origins: list[str] = ["http://localhost:3000"]`. Browsers treat `127.0.0.1` and `localhost` as different origins, so visiting the frontend at `127.0.0.1:3000` silently breaks every API call (Failed to fetch). Suggest adding `http://127.0.0.1:3000` to the allow-list so both work. NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 (per Docker-IPv6 memory note) is unaffected — the issue is the *frontend* page origin, not the API.


## pipeline-existing-run

- **POLISH [low]** — SectionNav pill did not appear active for the scrolled-to section
  - URL: `http://localhost:3000/pipeline/72beb83b-10c2-4861-bcc8-9af1f4fede31`
  - Verify IntersectionObserver thresholds in SectionNav.tsx.


## reverse-dcf

- **BUG [med]** — ReverseDcfPanel not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-reversedcfpanel.png`
- **BUG [med]** — SensitivityHeatmap not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-sensitivityheatmap.png`
- **BUG [med]** — ThesisVsPricedTable not visible on /model/NVDA#reverse-dcf
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Screenshot: `test-results/10-reverse-dcf-reverse-DCF-tab-renders-all-four-sub-panels-chromium/missing-thesisvspricedtable.png`
- **IMPROVEMENT [low]** — No price-override input visible on reverse-DCF tab
  - URL: `http://localhost:3000/model/NVDA#reverse-dcf`
  - Backend supports ?price=. Consider exposing in WhatIfScratchPanel.


## secondary-surfaces

- **NOTE** — No read-through CTA found on status board (may be expected if none queued)
  - URL: `http://localhost:3000/status`
- **BUG [high]** — GET /api/outcomes → 500: Pydantic response validation fails on `narrative` field
  - URL: `http://localhost:3000/performance`
  - Root cause: response model declares `signal_snapshot.signals_row.narrative` as `float`, but the actual DB row is a dict `{summary, post_count, post_texts, ...}` (X-signal post snapshot). The frontend Performance page calls `outcomesApi.list()` which hits this endpoint — every visit to /performance fails. `outcomes/summary` works fine; only `/api/outcomes` (the list) is broken. Check the `SignalsRow` / outcomes response schema for the narrative typing.


## themes-discovery

- **BUG [high]** — Theme "Neo-clouds" rendered no company cards
  - URL: `http://localhost:3000/theme/ebfa88fa-ed89-4c31-8a1c-10f5d9027490`
  - DiscoveryEngine may not have produced results — check signals table + FMP screener.
- **NOTE** — "No company cards" finding on /theme/.../Neo-clouds is likely a selector mismatch (test used `[data-company-card], [data-ticker]` — confirm what the theme detail page actually emits). Worth checking the screenshot before treating as a real bug.
