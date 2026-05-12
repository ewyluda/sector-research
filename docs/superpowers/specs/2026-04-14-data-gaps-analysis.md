# Data Gaps Analysis — Pipeline Runs in Library

_Date: 2026-04-14_

## Context

The Library page shows a `gap_count` badge per run and a "Data Gaps" filter view that aggregates gaps across runs via `/api/runs/data-gaps`. Gap detection lives in `backend/app/services/data_gaps.py` and scans `ResearchState` JSONB for three sources: `CategoryError` entries (hard), `CuratedFinancials` null/empty fields (soft), and LLM-reported `data_gaps` arrays inside each `DeepDiveCategoryOutput` (soft).

This doc captures the state of that system as of 2026-04-14 based on live DB inspection of completed runs.

## Top finding — LLM-reported gaps are silently dropped

`backend/app/services/data_gaps.py:10-14` iterates category keys as snake_case (`business_quality`, `financial_health`, …). Real `phase_outputs` keys are title-cased with spaces:

```
"Business Quality", "Financial Health", "Growth & Earnings",
"Management & Governance", "Technical & Market Structure",
"Macro & Regime", "Sentiment & Narrative", "Risk Assessment",
"Future Durability"
```

The lookup never matches, so the `structured.data_gaps[]` arrays the LLM produces are never surfaced. DB inspection found ~160 entries across completed runs that are invisible to the Library UI.

## Bucketed gap counts (167 real entries across runs)

| Bucket                          | Count | Source needed                                      |
|---------------------------------|-------|----------------------------------------------------|
| RPO / backlog                   | 38    | 10-Q/10-K footnotes (EDGAR)                        |
| Debt maturity schedule          | 29    | 10-K footnotes (EDGAR)                             |
| Customer concentration          | 28    | 10-K Item 1 / segment notes (EDGAR)                |
| Sentiment / social              | 16    | **Already have** — X signals not routed into prompts |
| Institutional ownership / 13F   | 15    | FMP has it; not fetched                            |
| Segment revenue/margin breakdown| 15    | 10-K segment notes (EDGAR)                         |
| Proxy / governance / comp       | 13    | DEF 14A (EDGAR)                                    |
| Options / IV term structure     | 6     | New vendor                                         |
| Technicals (RSI/MA/VWAP)        | 5     | **Already computed** — likely not in prompt payload |
| Credit ratings                  | ~3    | Vendor                                             |
| Other                           | 9     | mixed                                              |

## Silent failures not tracked as gaps

- **Transcripts missing** — `backend/app/graph/nodes.py:712-718` sets `transcript_analysis = None`; 6 transcript-routed categories run blind; no gap logged.
- **FRED unavailable** — `nodes.py:721-733` skips silently; 3 of 5 runs in DB have empty `macro_indicators`; no gap logged.
- **FMP partial fetch** — `nodes.py:735-739` catches the block; LLM receives a "data fetch partially failed" note; no gap logged.
- **JSON parse fallback** — `nodes.py:393-406, 864, 930, 1019` — regex extracts score/findings but `structured` is None, so that run's LLM-reported gaps are unrecoverable.

## Historic hard errors

Majority of `CategoryError` entries in DB are:

```
Error code: 400 - invalid_request_error:
"This model does not support assistant message prefill.
 The conversation must end with a user message."
```

— an API-usage bug from older runs. Recent runs should be re-checked to confirm the fix stuck; aggregation should probably not weight these anymore.

## Solvability tiers

### Tier 1 — Free wins (hours)
- Fix snake_case vs title-case key lookup in `data_gaps.py`.
- Add explicit soft-gap entries when transcripts/FRED/partial-FMP fail in `nodes.py`.
- Route X sentiment and computed technicals into the prompts whose LLM keeps reporting those as gaps.
- Backfill `gap_count` on existing `research_runs` rows after the fix.

### Tier 2 — FMP endpoints not yet used (~1 day) — status: done (2026-04-14)
- Institutional holders, insider transactions, analyst grades/upgrades, rating changes.
- Covers ~15 / 167 gaps.
- **Shipped:**
  - `FMPClient.get_analyst_grades` / `get_analyst_grades_historical` / `get_analyst_grades_consensus` / `get_price_target_consensus` / `get_ratings_snapshot` / `get_insider_trading` (uses `insider-trading/search` since `/latest` ignores symbol filter).
  - `node_deep_dive` fetches the six new endpoints in a second `asyncio.gather` with `return_exceptions=True` — any single 404/rate-limit degrades only that field, rest of Tier 2 survives.
  - `_fmt_fundamentals` renders three new blocks into every deep-dive prompt:
    - **Analyst Consensus & Ratings** — consensus label + analyst counts, price target (avg/median/range/implied upside vs current), FMP rating letter + overall score.
    - **Recent Analyst Actions** — last 8 grade changes (firm, prev → new, action).
    - **Analyst Consensus Trend** — 4-month monthly SB/B/H/S/SS counts.
    - **Insider Transactions** — aggregate buy/sell summary + last 6 market-priced Form 4 filings (zero-price option/gift rows filtered out).
- **Deferred:** institutional ownership — FMP's ticker-side endpoints return 404 on this plan; only CIK-keyed endpoints are available. Would require maintaining a ticker → holder mapping from daily polling of `institutional-ownership/latest`. Parked.

### Tier 3 — SEC EDGAR integration (~1 week)
- Targeted extraction of RPO/backlog, debt maturity schedule, customer concentration, segment breakdowns, DEF 14A governance.
- Covers ~95 / 167 gaps (57% of the surfaced gap volume).

### Tier 4 — New vendors
- Options IV term structure, credit ratings.
- Smaller tail (~10 gaps).

## Plan of record

Pursue **A (Tier 1)** first, then **B (Tier 3 — EDGAR)**. Tier 2 deferred; Tier 4 parked.

## Tier 3 v1 — SEC EDGAR XBRL (plan)

**Scope for v1 — XBRL only.** We query SEC's structured XBRL facts for each ticker and persist a curated subset. HTML/PDF section extraction for prose-heavy gaps (customer concentration descriptions, debt maturity narrative tables) is parked for **v2**.

**Storage — new tables (scales better as more filings data is added):**

- `filings` — one row per SEC filing we've seen (accession number, form type, filing date, period_of_report, ticker/cik, URL). Dedup by `accession_number`.
- `xbrl_facts` — one row per (filing, concept, unit, period) tuple. Stores the XBRL concept name (e.g. `us-gaap:RevenueRemainingPerformanceObligation`), the numeric value, the context period (instant or start/end dates), and units (USD, shares, pure).

This keeps raw structured facts queryable and composable — downstream categories can select the series they want without us pre-flattening into curated_financials. We can later add `filing_sections` for v2 HTML extraction without schema churn.

**Client — `backend/app/clients/edgar.py`:**

- Uses SEC's `data.sec.gov/submissions/CIK{cik}.json` (filings index) and `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` (all XBRL facts for a CIK). Both are free, rate-limited to 10 req/s, require a `User-Agent` with contact email.
- Ticker → CIK mapping via `www.sec.gov/files/company_tickers.json` (cached in-memory, refreshed daily).
- Returns `(data, Citation)` tuples, matching the convention in `backend/app/clients/fmp.py`.

**Concept whitelist for v1** (focused on the top 3 gap buckets + a few bonuses):

| Gap bucket | XBRL concepts |
|---|---|
| RPO / backlog | `us-gaap:RevenueRemainingPerformanceObligation`, `us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPercentage` (+ start/end date variants) |
| Debt maturity | `us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths`, `…InYearTwo`, `…InYearThree`, `…InYearFour`, `…InYearFive`, `…AfterYearFive` |
| Customer concentration | `us-gaap:ConcentrationRiskPercentage1` (requires segment/customer axis handling — best-effort in v1, logged as data gap if axis unusable) |
| Credit — bonus | `us-gaap:WeightedAverageInterestRate`, `us-gaap:LongTermDebt`, `us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity` |
| Share count — bonus | `dei:EntityCommonStockSharesOutstanding` (useful for segment/valuation cross-checks) |

**Ingestion model:**

- On each deep_dive run, after the FMP block, the pipeline fetches the ticker's CIK and issues **one** `companyfacts` call, filters to the whitelist, and upserts `filings` + `xbrl_facts` rows.
- Subsequent runs for the same ticker skip re-fetching if the newest filing's `accession_number` is already in `filings` (fresh enough).
- Routing: a new `_build_edgar_context(category)` helper reads recent facts for the relevant concepts per category and injects them into the prompt as a new `{edgar_data}` slot alongside `{transcript_data}`, `{macro_data}`, `{technical_data}`, `{sentiment_data}`.
  - `Growth & Earnings` / `Future Durability` → RPO, RPO timing
  - `Financial Health` / `Risk Assessment` → debt maturity schedule, weighted avg interest rate
  - `Business Quality` / `Risk Assessment` → customer concentration
- When a concept is missing for a ticker, the helper emits an explicit note like "RPO not disclosed in XBRL" so the LLM knows it's a true gap (not a routing failure) — and `data_gaps.py` can distinguish unroutable from unavailable.

**v2 backlog:**

- HTML / PDF targeted section extraction for 10-K Item 1, Item 1A (Risk Factors), Item 7 (MD&A), and DEF 14A governance sections. Likely uses `sec-api.io` or direct EDGAR HTML + a light section-header parser.
- `filing_sections` table: `(filing_id, section_name, text, extracted_at)`.
- Governance extraction: board composition, director independence, compensation structure from DEF 14A.
- Customer concentration via XBRL `ConcentrationRiskPercentage1` requires handling the RiskAxis/MajorCustomersAxis dimension; v1 skips dimensional axes entirely.

## Tier 3 v1 — status: done (2026-04-14)

**Schema**

- Migration `d14ab77781f8_add_filings_and_xbrl_facts` creates `filings` and `xbrl_facts` tables with indexes on ticker, accession_number, concept, period_end.
- Models in `backend/app/models/filing.py` (Filing, XBRLFact).

**Client**

- `backend/app/clients/edgar.py` — rate-limited (async lock + 0.11s throttle, ~9 req/s), User-Agent from `settings.sec_user_agent`. Methods: `get_ticker_to_cik`, `get_company_facts`, `get_submissions`. Returns `(data, Citation)` tuples like FMP/FRED.
- `CONCEPT_WHITELIST` covers RPO (2 concepts), debt maturity schedule (6 year-buckets), customer concentration (1, best-effort), credit ratings proxies (3), shares outstanding (1).

**Ingestion**

- `backend/app/services/edgar_ingest.ingest_ticker_facts()` — fetches companyfacts, filters to whitelist, upserts `filings` (dedup by `accession_number`) + `xbrl_facts`. Idempotent: second call for the same ticker skips all facts whose filings already exist.
- `get_recent_facts_by_concept()` — returns `{concept: [fact_dict, ...]}` most recent first, used by the prompt builder.

**Pipeline wiring**

- `backend/app/main.py` instantiates `EdgarClient` in the app lifespan and passes it into `PipelineService`.
- `backend/app/services/pipeline.py::_fetch_edgar_facts` ingests + fetches facts for the ticker before every deep-dive run. Best-effort: any EDGAR failure logs a warning and the pipeline continues with empty facts.
- `backend/app/graph/nodes.py::EDGAR_ROUTING` maps categories → concepts:
  - `Growth & Earnings` + `Future Durability` → RPO
  - `Financial Health` → debt maturity ladder + credit proxies
  - `Risk Assessment` → debt maturity ladder + customer concentration + credit proxies
  - `Business Quality` → customer concentration
- `_build_edgar_context(category)` in `node_deep_dive` emits per-concept most-recent facts and explicit "not disclosed in XBRL" notes for whitelisted concepts the filer doesn't report.
- New `{edgar_data}` slot in `DEEP_DIVE_USER` (`prompts.py`).

**Verified against live data (2026-04-14 ingest):**

| Ticker | Filings | Facts | Sample |
|---|---|---|---|
| ORCL | 67 | 199 | RPO $552.6B (Q3 FY26), debt due 12mo $7.31B |
| RKLB | 19 | 52 | RPO $1.85B (FY25), LongTermDebt 14 points |
| CRWV | 13 | 30 | RPO $312M + full debt ladder |
| NBIS | 6 | 6 | LongTermDebt only |

## SEC citation surfacing — status: done (2026-04-14)

- `clients/edgar.py::EdgarClient.get_company_facts()` now emits a Citation shaped for the Library UI: `value=entityName` (e.g. "Oracle Corporation"), `metric="XBRL filings"`, `source_name="SEC EDGAR"`, `tier=1`, `source_url` pointing at the authoritative companyfacts JSON.
- `services/edgar_ingest.py::ingest_ticker_facts()` signature changed to `(summary, citations)`. It only appends the companyfacts citation when analytically useful data is returned — ticker→CIK lookups stay internal plumbing and don't pollute the citation list.
- `services/pipeline.py::_fetch_edgar_facts()` now returns `(facts, citations)`, and `_run_deep_dive_with_streaming` converts each Citation to a `StateCitation` via `state.add_citation()` so it persists in ResearchState alongside FMP/FRED/X sources.
- CitationList in the frontend requires no changes — the new entry renders as `[n] SEC EDGAR · XBRL filings` linking to `data.sec.gov/api/xbrl/companyfacts/CIK…json`.

## EDGAR UI surfacing — status: done (2026-04-14)

Backend:
- `GET /api/runs/{run_id}/report` now returns `phases.deep_dive.edgar_facts` — `Record<concept, Fact[]>` keyed by XBRL concept, most-recent-first, up to 12 entries per concept.
- `deep_dive_start` SSE event includes the same `edgar_facts` payload so live runs render charts as the phase starts.

Frontend:
- `EdgarFact` / `EdgarFacts` types added to `frontend/lib/api.ts` and threaded through `ReportResponse` + `SSEEvent`.
- New chart components:
  - `components/deep-dive/charts/DebtMaturityLadder.tsx` — 6-bucket bar chart (Next 12mo / Y2 / Y3 / Y4 / Y5 / After Y5) driven by the `LongTermDebtMaturitiesRepaymentsOfPrincipal*` concept family. Shows total + as-of date. Falls back to "not disclosed" when no XBRL data.
  - `components/deep-dive/charts/RPOTrend.tsx` — 8-quarter bar trend with first→latest growth %, using `RevenueRemainingPerformanceObligation`. Falls back to "not disclosed" when empty.
- Wired into `sections/FinancialHealth.tsx` (debt maturity ladder below balance sheet composition) and `sections/GrowthEarnings.tsx` (RPO trend below revenue). Both conditionally render only when `edgarFacts` is present, so pre-EDGAR runs still display unchanged.
- `edgarFacts` state on `/pipeline/[runId]` is populated from both `loadReportData` (completed runs) and the `deep_dive_start` SSE handler (live runs).

## Prefill-error purge — status: done (2026-04-14)

- Added `_STALE_HARD_ERROR_SUBSTRINGS` + `_is_stale_hard_error()` to `services/data_gaps.py`. `compute_data_gaps()` now skips `CategoryError` entries whose reason contains `"does not support assistant message prefill"` — a bug fixed in commits `0ccee3e` / `b26079e`.
- State JSONB untouched — old errors remain recoverable if ever needed, they just don't skew aggregation.
- Hard errors across all 20 runs drop from 10 → 0. Library's `gap_count` / `data-gaps` aggregation now reflects the real current state.

## Verification run — 2026-04-14 (CRWV, post-fix)

Run `6a88853e-ccf1-4a72-a02a-a45f2fe55112` completed through risk_stress_test. Deep-dive analysis:

- **27 total gaps, 0 hard errors, 0 silent-failure flags** (FMP + FRED + transcript all succeeded).
- **Technical & Market Structure** no longer flags RSI / moving averages. Now flags volume, IPO/lockup, options IV. Minor regression — our technical payload stripped volume; patched to include it.
- **Sentiment & Narrative** no longer flags "no social/media sentiment signal". Now flags short interest + transcript depth.
- **Financial Health + Risk Assessment** no longer flag debt maturity ladder. New gaps are covenants / cross-default / collateral coverage (HTML-only, parked for v2).
- **Growth & Earnings + Future Durability** no longer flag RPO absolute value. The LLM now cites the exact whitelist concept by name (`RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPercentage not disclosed`), confirming EDGAR context is reaching the prompt and being interpreted correctly.
- **Business Quality + Risk Assessment** still flag customer concentration — expected, v1 does not handle `ConcentrationRiskPercentage1`'s dimensional axis (v2 backlog).

Pre-fix typical run had ~25–30 gaps, dominated by FMP-is-enough / sentiment / technicals / RPO / debt maturity. Post-fix the count is similar but the **content is materially higher quality** — remaining gaps point to real v2 work (HTML extraction, dimensional XBRL, new vendors), not routing bugs.

## Tier 1 — status: done (2026-04-14)

Changes:

- `backend/app/services/data_gaps.py` — fixed `_DEEP_DIVE_CATEGORIES` to match actual title-cased phase_outputs keys (`"Business Quality"`, `"Financial Health"`, `"Growth & Earnings"`, `"Management & Governance"`, `"Technical & Market Structure"`, `"Macro & Regime"`, `"Sentiment & Narrative"`, `"Risk Assessment"`, `"Future Durability"`). Verified against DB: gap surfacing went from ~9 to 215 across 20 runs.
- `backend/app/services/data_gaps.py` — added silent-failure detection: logs a soft gap when `curated_financials is None` but deep-dive ran (FMP fetch failed), when `curated_financials.macro_indicators` is empty (FRED unavailable), and when `transcript_analysis` is None / `{"error": ...}` with deep-dive having run (transcripts unavailable).
- `backend/app/graph/prompts.py` — added `{technical_data}` and `{sentiment_data}` slots to `DEEP_DIVE_USER`.
- `backend/app/graph/nodes.py` — `node_deep_dive()` now accepts an optional `signals` dict. Added `_build_technical_context(category)` (latest 20 sessions of close/SMA/RSI for `Technical & Market Structure`) and `_build_sentiment_context(category)` (velocity/narrative/discovery signal for `Sentiment & Narrative`). `_run_one_category()` threads both.
- `backend/app/services/pipeline.py` — added `_fetch_signals(ticker, theme_id, db)` that reads the `signals` table and returns `{signal_type: value}`. `_run_deep_dive_with_streaming` now fetches signals and passes them to `node_deep_dive`.

`gap_count` is computed on every `GET /api/runs` call, so no backfill is needed — existing rows will self-heal in the Library as soon as the backend restarts.

Not yet done in Tier 1:

- Purge / re-weight the historic `"This model does not support assistant message prefill"` CategoryError rows in the aggregation (they dominate hard_error counts from older runs).
- Verify in a live run that Technical and Sentiment categories stop self-reporting those buckets as gaps.

## File references

- `backend/app/services/data_gaps.py:10-14` — category key list (bug)
- `backend/app/services/data_gaps.py:27-77` — gap computation
- `backend/app/graph/nodes.py:44` — 90s timeout per category
- `backend/app/graph/nodes.py:413-418` — CategoryError construction
- `backend/app/graph/nodes.py:712-718` — transcript silent skip
- `backend/app/graph/nodes.py:721-733` — FRED silent skip
- `backend/app/graph/nodes.py:735-739` — FMP partial-fetch swallow
- `backend/app/graph/state.py:15-50` — CategoryResult/CategoryError
- `backend/app/graph/state.py:111-260` — CuratedFinancials
- `backend/app/models/phase_schemas.py:162` — DeepDiveCategoryOutput.data_gaps
- `backend/app/api/pipeline.py:76` — gap_count emission
- `backend/app/api/pipeline.py:158-179` — /api/runs/data-gaps aggregation
- `frontend/app/library/page.tsx:43-60, 118-122, 170-262` — UI consumption
