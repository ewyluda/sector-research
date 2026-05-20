# S-1 Prospectus Analysis Pipeline

**Status:** Approved design, awaiting implementation plan
**Date:** 2026-05-20
**Trigger:** SpaceX S-1 (https://www.sec.gov/Archives/edgar/data/1181412/000162828026036936/spaceexplorationtechnologi.htm)

## Problem

The existing research pipeline is **ticker-anchored and FMP-driven**. Every node calls `fmp.get_*(state.ticker, …)`; the deep-dive payload (`_fmt_fundamentals` in `backend/app/graph/nodes.py`) is shaped entirely around FMP responses; the nine deep-dive categories assume earnings transcripts, analyst consensus, FRED macro, and a public-trading history exist.

An S-1 violates almost all of that. The issuer has no ticker, no FMP data, no earnings transcripts, no analyst estimates, no daily prices. The only filing artifact is the S-1 itself (plus any S-1/A amendments), and it has a very different section structure from a 10-K — Use of Proceeds, Underwriting, Dilution, Principal Stockholders, Capitalization, Lock-up Agreements — alongside the familiar Business / Risk Factors / MD&A.

The current pipeline cannot run against an S-1 without either lying about its inputs (synthesising fake FMP shapes) or branching every node behind an `if is_s1:` conditional that would risk regressing the working public-company path.

## Goal

Add a separate, smaller analytical pipeline that consumes an S-1 prospectus and produces a per-issuer research report scoped to what an S-1 actually answers. Reuse the EDGAR ingest plumbing, HTML section extractor, relationship extractor, and Sonnet/Haiku prompt scaffolding. Keep the public-company pipeline untouched.

The SpaceX S-1 is the proof point, but the feature is general: any S-1 from any issuer.

## Non-goals (v1)

- Financial model / reverse DCF for the issuer. (No time-series long enough; no analyst consensus to anchor against. Out of scope.)
- LangGraph `ResearchState` reuse. (Forces too many compromises; the prospectus path uses its own state shape.)
- Multi-amendment (S-1/A) diffing. The first cut analyses one filing snapshot per report. Add diffing later if useful.
- Auto-ingest of newly-filed S-1s from an EDGAR sweep. v1 is manual entry only — this is an opportunistic feature, not a fleet capability.
- Comparable-company valuation. The "IPO Mechanics" step covers what the deal *is* (size, dilution, lock-ups, use of proceeds). Whether the offering price is fair is a separate design.
- Surfacing reports on Status / Catalysts / Workspace. Those are keyed on `ticker` + completed `research_run`; a private-issuer prospectus has neither. The bridge is the "post-IPO promotion" seam (see below) — designed-for, not built v1.

## Design

### New domain object: `ProspectusReport`

Parallel to `ResearchRun` / `WorkspaceRun` — its own table, its own service, its own API surface.

```python
# backend/app/models/prospectus_report.py (new)
class ProspectusReport(Base, TimestampMixin):
    __tablename__ = "prospectus_reports"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    accession_number: Mapped[str] = mapped_column(index=True)     # the S-1
    issuer_cik: Mapped[str] = mapped_column(index=True)
    issuer_name: Mapped[str]
    proposed_ticker: Mapped[str | None]                           # e.g. "SPACE" if disclosed
    theme_id: Mapped[str | None] = mapped_column(ForeignKey("themes.id", ondelete="SET NULL"))
    status: Mapped[str]  # ingesting | analyzing | completed | failed
    step_outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None]
```

`step_outputs` follows the `WorkspaceRun.step_outputs` JSONB pattern (one keyed entry per analytical step, each shaped by a Pydantic schema in `models/prospectus_schemas.py`). This keeps the on-disk shape grokable and makes the frontend hydrator the same kind of code as `WorkspaceReport.tsx`.

The S-1 itself reuses the existing `filings` and `filing_sections` tables — adding `S-1` and `S-1/A` to `TARGET_FORMS` is wrong for the existing public-company ingest path (which keys on ticker), so a parallel ingest function for the prospectus path writes its rows there directly without going through `ingest_ticker_sections`. The `filings.ticker` column is `String(16) NOT NULL`. Rather than relaxing it (which would ripple across the public-company query paths), private-issuer ingest writes `proposed_ticker` if disclosed in the S-1, otherwise the first 16 characters of an issuer slug (uppercase, alphanumeric-only — e.g. `SPACEEXPLORATIO`). This satisfies the constraint while keeping the value identifiable; the `issuer_cik` on `ProspectusReport` is the canonical join key, not the synthetic ticker.

### Pipeline — four sequential steps, no loop

The pipeline is run by a new `ProspectusService` (modelled on `WorkspaceService` in `backend/app/services/workspace.py`): in-memory `dict[report_id, asyncio.Queue]` for SSE, a guard against duplicate starts per issuer, each step in its own `async_session()` with explicit `await db.commit()`.

**Step 1 — `ingest_prospectus`**
- Resolve the input (S-1 URL or accession number) to a CIK and primary document URL via `EdgarClient.get_submissions`.
- Add a new section-defs constant `_SECTION_DEFS_S1` to `backend/app/services/edgar_html.py`. Extracted sections (regex-keyed):
  - `s1_business` — Item 1 / Business
  - `s1_risk_factors` — Risk Factors
  - `s1_mda` — MD&A
  - `s1_use_of_proceeds` — Use of Proceeds
  - `s1_capitalization` — Capitalization
  - `s1_dilution` — Dilution
  - `s1_principal_stockholders` — Principal Stockholders
  - `s1_underwriting` — Underwriting (Plan of Distribution)
- Persist the S-1 row to `filings` (form_type `"S-1"` or `"S-1/A"`), sections to `filing_sections` (same idempotency on `(filing_id, section_key)`).
- **Embedded-financials extraction** is its own pass inside this step: a table-aware Sonnet call over the Selected Financial Data / Consolidated Statements regions, output as a `ProspectusFinancials` Pydantic struct (annual revenue / opex / net income / cash for the periods presented, plus interim if shown). Stored on `step_outputs["ingest"]`. Table extraction is the highest-risk part of this step — design-time mitigation is to (a) prefer Sonnet over Haiku, (b) keep the schema small and named-line-item-keyed (`revenue_fy2024`, `revenue_fy2023`, …) so a missing year is an obvious null rather than a corrupted row, and (c) include the verbatim source snippet alongside each extracted figure for citation.

**Step 2 — `extract_relationships`**
- Reuse `backend/app/services/edgar_relationships.py` against `s1_business` + `s1_risk_factors`. The extractor is already filing-section-keyed and doesn't care about form type.
- Resolve counterparties via `services/counterparty_resolver.py` (also already issuer-agnostic at the call boundary; it only needs the resolved CIK to exist for hit-resolution).
- Edges land in the existing `relationships` table. The `relationships.ticker` denormalisation column gets the same synthetic identifier the prospectus ingest wrote to `filings.ticker` (proposed ticker if disclosed, else issuer slug — see above). This keeps the existing `Relationship.ticker → graph traversal` code path identifier-consistent for the prospectus issuer without needing a CIK-keyed alternative path.

**Step 3 — `analyze_categories`**
- Run a **curated subset of seven deep-dive categories** in parallel against the extracted sections + extracted financials + counterparty context + FRED macro.
- New module `backend/app/services/prospectus_categories.py` mirrors the structure of `node_deep_dive` but with a simpler context-build path: no FMP fetch, no transcripts, no analyst grades. Each category gets a `PromptContext` dataclass populated from the prospectus-specific sources.
- Categories and their primary inputs:

  | Category | Inputs |
  |---|---|
  | Business Quality | `s1_business`, counterparty context |
  | Risk Assessment | `s1_risk_factors`, `s1_capitalization`, `s1_dilution`, counterparty context |
  | Growth & Earnings | `s1_mda`, `ProspectusFinancials` (no analyst consensus) |
  | Management & Governance | `s1_principal_stockholders` + management bios extracted from `s1_business` |
  | Future Durability | `s1_business`, `s1_use_of_proceeds`, counterparty context, macro |
  | Macro & Regime | FRED indicators (existing 9 series) |
  | **IPO Mechanics** *(new)* | `s1_underwriting`, `s1_use_of_proceeds`, `s1_dilution`, lock-up clauses extracted from `s1_underwriting` |

- Each category produces a `CategoryResult` shaped like the existing one (`category`, `content` markdown, `score` 0–100, `key_findings`, `structured`). Stored under `step_outputs["categories"]` keyed by category name.
- **Dropped** (no data exists): Financial Health, Technical & Market Structure, Sentiment & Narrative. The report UI does not render skeleton cards for dropped categories — they're absent, not empty.

**Step 4 — `synthesize_thesis`**
- Single Sonnet pass over all category outputs. Produces a `ProspectusThesisOutput` Pydantic struct:
  - `thesis_statement` (markdown)
  - `key_risks` (list of {risk, severity, category_source})
  - `ipo_verdict`: `Literal["participate", "watch_post_lockup", "pass"]`
  - `price_range_commentary` (string; `None` if S-1 hasn't set a range yet)
  - `post_ipo_research_plan`: list of `{question, why_it_matters, expected_data_source}` — the watchlist of things to re-evaluate once the issuer is public and FMP starts serving data.

### API surface

New router `backend/app/api/prospectus.py`, prefix `/api/prospectus`:

- `POST /api/prospectus` — body `{ "url_or_accession": str, "theme_id": str | None }`. Returns `{ "report_id": str }` and kicks off the pipeline as a background task (same pattern as `PipelineService`).
- `GET /api/prospectus/{report_id}` — full report (status + step_outputs).
- `GET /api/prospectus/{report_id}/stream` — SSE.
- `GET /api/prospectus` — list (paginated).
- `DELETE /api/prospectus/{report_id}` — discard.

No `/advance` endpoint — there are no interrupt gates in this pipeline.

Wire `ProspectusService` into `main.py::lifespan` as `app.state.prospectus = ProspectusService(edgar=app.state.edgar)`, reusing the shared EdgarClient (same pattern as `app.state.fanout` and `app.state.workspace`).

### Frontend

New top-level nav entry **Prospectus**. Routes:

- `/prospectus` — list of reports (issuer + status + verdict pill + filing date), modelled on `/workspace` (`frontend/app/workspace/page.tsx`).
- `/prospectus/[reportId]` — report detail. `ProspectusReport.tsx` is the dual-hydrating REST+SSE consumer (mirrors `frontend/components/workspace/WorkspaceReport.tsx`). One card per step output in `frontend/components/prospectus/StepCards/` — `IngestSummaryCard`, `RelationshipsCard`, `CategoryCard` (rendered N times), `ThesisCard` with the IPO verdict badge.
- Entry point also on `/filings` — small "New prospectus report" button that opens a modal with a URL/accession input and an optional theme picker.

All backend calls go through `frontend/lib/api.ts` (new typed methods: `createProspectusReport`, `getProspectusReport`, `streamProspectusReport`, `listProspectusReports`, `deleteProspectusReport`). TypeScript types mirror the Pydantic schemas — same convention as the rest of the app.

### Design seams (not built in v1, but worth designing for)

- **Post-IPO promotion.** Once the issuer lists and FMP serves data, the user should be able to one-click promote a prospectus report into a research run seeded with the prospectus thesis + research plan. The `post_ipo_research_plan` output from step 4 is the payload that bridges. v1 ships the button as a stub that opens `/pipeline/new` with `ticker` and `theme_id` prefilled — full seeding can come later.
- **S-1/A amendment diffing.** The `accession_number` column is per-amendment; a future "diff against prior amendment" view runs the same extractor over the prior S-1/A and renders a section-keyed diff. Out of scope for v1 but the data model supports it.

## Architecture notes

- **Ticker normalisation.** The codebase normalises `ticker = ticker.upper()` at every API entry point (`api/filings.py`, `api/earnings.py`, `api/models_api.py`). The prospectus API normalises `proposed_ticker` the same way; `issuer_cik` is normalised to the 10-digit zero-padded form `EdgarClient` already produces.
- **Service singletons.** `ProspectusService` is constructed once in `main.py::lifespan` and reused. It must NOT instantiate its own `EdgarClient` — that would bypass the shared session pool. Pass `app.state.edgar` in (same as `FanoutService`).
- **Session lifecycle.** Each step runs in its own `async_session()` with explicit `await db.commit()`. The base session factory is `expire_on_commit=False` but does NOT autocommit; forgetting `commit()` means nothing persists. See the `FanoutService` precedent.
- **Citations.** Every extracted figure in `ProspectusFinancials` carries a verbatim source snippet so the frontend can render it as a `Citation`-shaped pill (same pattern as `StateCitation`). The relationships table already carries verbatim quotes.
- **Idempotency.** Re-ingesting the same S-1 (same accession) is a no-op at the `filings` / `filing_sections` layer (existing unique constraints handle this). Re-running a `ProspectusReport` step is *not* automatically idempotent — by default a new run creates a new report row; a `force_refresh` flag is a v1.1 nicety, not v1.

## Open questions

None that block implementation. Resolved at design time:

- ~~Run the existing pipeline with a flag, or build a parallel pipeline?~~ → Parallel pipeline (`ProspectusReport` + `ProspectusService`).
- ~~Which deep-dive categories carry over?~~ → Seven listed above; three dropped; one new (`IPO Mechanics`).
- ~~Where in the UI?~~ → New `/prospectus` top-level workspace.
- ~~v1 scope?~~ → Full design as specified; valuation deferred.

## Success criteria

1. `POST /api/prospectus` with the SpaceX S-1 URL returns a report id within 1 second and begins streaming step events.
2. Step 1 produces non-empty extracts for at least 6 of the 8 defined S-1 sections, and a `ProspectusFinancials` struct with at least two annual periods of revenue / opex / net income.
3. Step 2 produces at least 20 counterparty edges in the `relationships` table for the SpaceX filing.
4. Step 3 returns 7 `CategoryResult` outputs, each with a non-empty `content` and a `score` in [0, 100].
5. Step 4 returns a `ProspectusThesisOutput` with a non-null `ipo_verdict` and a `post_ipo_research_plan` of at least 5 items.
6. `/prospectus/{reportId}` renders progressively as steps complete (SSE), and `/prospectus` lists the report with the verdict pill.
7. The existing public-company pipeline (`/pipeline/new`, `/pipeline/[runId]`, deep-dive dashboard, status board, workspace) is unchanged — same test runs pass, same SSE events emit.
