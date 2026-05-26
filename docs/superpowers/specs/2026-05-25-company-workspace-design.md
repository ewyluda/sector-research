# Company Workspace — Design Spec

> **Date**: 2026-05-25
> **Status**: Approved design — ready for implementation planning
> **Inspiration**: `docs/fiscal-ai-design-inspo.md`

## Summary

Add a `/company/[ticker]` **unified shell** as a new anchor surface that absorbs
fiscal.ai's persistent-company-workspace patterns, *without* pivoting away from the
existing theme/thesis/fleet spine. Themes/theses become an **active lens** over the
workspace rather than a separate organizing axis.

This is an **absorb, not pivot** move: fiscal.ai is the reference layer; the existing
pipeline is the judgment layer. We borrow fiscal.ai's shell to make the app's judgment
legible against complete company data — we do not replace the judgment to become a
worse reference terminal.

## Locked decisions

1. **Unified shell** — `/company/[ticker]` is the persistent anchor; the existing
   run-report, model, and filings surfaces re-home under it (vs. a parallel surface that
   links out).
2. **Fresh company-snapshot endpoint** — the always-on tabs (Overview / Financials /
   Transcripts) fetch FMP directly through the shared `FMPClient` TTL cache and work for
   *any* ticker, independent of whether a research run exists (vs. reusing a run's
   persisted `CuratedFinancials`).
3. **First implementation slice = shell skeleton + re-home existing.** Overview /
   Financials / Transcripts ship as empty-state placeholders in slice 1; the spec covers
   all seven tabs.
4. **Active lens** — a `Lens: [All ▾]` header selector reframes the workspace through a
   theme (vs. passive cross-reference only). The backend hooks already exist
   (`theme_id` on the relationship graph; per-theme discovery scores).

## Architecture

### Routing & shell

A new App Router route group with a **layout** rendering the persistent shell (header +
tab strip + lens selector); children render in the body.

```
/company/[ticker]                       → Overview
/company/[ticker]/financials/[stmt]     → Financials (income | balance | cash-flow)
/company/[ticker]/transcripts           → Transcripts
/company/[ticker]/research              → latest completed run's deep-dive report
/company/[ticker]/model                 → financial model
/company/[ticker]/filings               → filings for ticker
/company/[ticker]/theses                → lens detail + cross-reference
```

- **Lens state lives in a `?lens=<themeId>` search param** so deep-links carry it;
  absence of the param = "All" (neutral fiscal.ai-style view).
- **Next.js 16 caveat:** verify `searchParams` / layout / route-handler APIs against
  `node_modules/next/dist/docs/` before writing any frontend code (per
  `frontend/AGENTS.md`).

### Reconciling run-scoped vs ticker-scoped surfaces

A company has *many* runs but the workspace is ticker-scoped:

- **Research tab** resolves the latest completed run for the ticker (via existing
  `pipeline.list`), renders `DeepDiveDashboard`, and offers a **run-selector** for older
  runs + an empty-state CTA to `/pipeline/new?ticker=X` when none exists.
- **Model tab** — `/model/[ticker]` is already ticker-scoped. Extract its page body into
  a component the workspace route renders; keep the old `/model/[ticker]` route as a thin
  redirect (or wrapper) so existing deep-links (e.g. `ModelStatusBadge`) still work.
- **Filings tab** — filings for the ticker (existing filings panel, scoped to ticker).

### Backend: company-snapshot surface

New `backend/app/api/company.py` (prefix `/api/company`) + a
`backend/app/services/company_snapshot.py` service. All built on the shared
`app.state.fmp` singleton and the `tuple[data, Citation]` convention. Ticker normalized
to upper-case at entry (matches existing routers).

| Endpoint | Returns | Slice |
| --- | --- | --- |
| `GET /{ticker}/header` | quote (price, Δ, %Δ, 15-min delay flag) + profile (name, logo, exchange) | **1** |
| `GET /{ticker}/overview` | 8-group statistics grid (key-metrics-ttm + profile + financial-growth + estimates), price-chart series, earnings beat/miss series; lens-aware extras (`?theme_id=` → discovery score + theme rank) | 2 |
| `GET /{ticker}/financials/{stmt}?granularity=` | standardized statement rows with absolute + %chg + common-size derivative rows | 3 |
| `GET /{ticker}/transcripts[/{event}]` | event list + speaker-segmented transcript | 4 |

**Statistics grid groups** (from `docs/fiscal-ai-design-inspo.md` §3.1): Profile,
Margins, Returns (5Yr Avg), Valuation (TTM), Valuation (NTM), Financial Health, Growth
(CAGR), Dividends. Most are sourced from FMP `key-metrics-ttm` + `financial-growth` +
`profile` + `analyst-estimates`.

**Bulls / Bears** derive from the latest completed run: `thesis_construction` structured
output → bull bullets; `risk_stress_test` → bear bullets. Empty-state when no run exists.
With a lens active, prefer the run tied to that theme. (Generated from the app's own
pipeline output — *not* licensed Morningstar content.)

### Active lens behavior

With a lens (`?lens=<themeId>`) active:

- **Overview** adds the theme discovery score + theme-relative rank for the ticker.
- **Filings graph** gates hop-2 expansion to the theme's seed tickers (the existing
  `theme_id` param on `GET /api/relationships/graph/{ticker}`).
- **Bulls/Bears** weights to that theme's thesis.
- `Lens: All` = neutral view, no reframing.

The **Theses tab** (always present, slice 1) surfaces, from existing run/theme/status
data: themes this ticker appears in (+ rank/score in each), run history & verdict
timeline, status-board health, kill-criteria state, and open questions.

## Frontend components

- `app/company/[ticker]/layout.tsx` — the shell.
- `components/company/`: `CompanyHeader`, `TabStrip`, `LensSelector`, `PricePill`.
- Per-tab directories added as slices land:
  - `components/company/theses/` — `ThesesTab` (**slice 1**, reads existing data).
  - `components/company/overview/` — `StatisticsGrid`, `PriceChart`, `BullsBears`,
    `EarningsBeatMiss` (slice 2).
  - `components/company/financials/` — `FinancialsTable`, `PeriodSlider`, toolbar toggles
    (slice 3).
  - `components/company/transcripts/` — `TranscriptReader` (slice 4).
- `lib/api.ts` — typed client functions: `getCompanyHeader`, `getCompanyOverview`, etc.,
  mirroring backend shapes.
- **Entry points:** ticker references across the app (theme detail, status board, report
  header) link to `/company/[ticker]`. No new top-nav tab in slice 1 (the workspace is
  ticker-scoped, so there is no single landing). A ticker-jump box in `Nav` is a deferred
  option.

## Slice 1 deliverable (first implementation plan)

- Route group + `layout.tsx` shell + live header (quote/profile) + tab strip + lens
  selector wired to the existing theme list.
- Re-homed **Research** (latest run + run-selector + empty state), **Model** (body
  extracted to a component), **Filings** (ticker filings) tabs.
- **Theses** tab from existing run/theme/status data.
- Overview / Financials / Transcripts = empty-state placeholders.
- Backend: `GET /api/company/{ticker}/header` only (quote + profile).
- Entry links from theme detail + status board.

## Error handling

- Unknown ticker / FMP miss → header shows ticker only; tabs degrade to empty states; the
  shell never crashes.
- Quote fetch failure → price pill shows "—" with no delay label.
- `?lens=` referencing a deleted theme → fall back to "All".
- No completed run → Research / Bulls-Bears / Theses show empty-state CTAs.

## Testing

- **Backend:** stdlib `unittest` for `company_snapshot` (header shape, overview mapping,
  lens branch) with a stubbed `FMPClient`, following the existing `backend/tests/`
  pattern (`python -m unittest backend.tests.<module>` from project root).
- **Frontend:** `tsc` / `npm run lint` + manual smoke. No FE test harness in the repo.

## Phasing

The spec covers all seven tabs; implementation is sliced into separate plans:

| Slice | Scope |
| --- | --- |
| **1** | Shell skeleton + re-home (Research/Model/Filings) + Theses tab + `/header` endpoint |
| **2** | Overview — statistics grid, price chart, Bulls/Bears, beat/miss + `/overview` endpoint |
| **3** | Financials tables — period slider, %chg / common-size toggles, derivative rows + `/financials` endpoint |
| **4** | Transcripts reader + `/transcripts` endpoint |

## Explicitly out of scope (deferred / not feasible today)

Per the fiscal.ai teardown, these require data feeds the app does not have and are **not**
in this design: licensed analyst research (Morningstar), consensus estimate revision
history, 13F institutional ownership, Quartr audio dock, real-time (sub-15-min) quotes,
premium-gating UI (the app is local-only, no auth). The Industry peer-builder tab is also
deferred — the existing relationship graph already covers the "what does my universe see"
need.
