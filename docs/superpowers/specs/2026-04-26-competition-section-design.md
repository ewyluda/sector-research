# Competition Section — Design

**Date:** 2026-04-26
**Status:** Approved (pending implementation plan)
**Owner:** ericwyluda

## Summary

Add a **Competition** section to the deep-dive dashboard that reconstructs the structured competition disclosure from a 10-K's Item 1 — `Segment → Area of Competition → [Competitors]` — plus a short narrative per segment that gives "is this segment material/growing?" context. Extraction is opt-in per ticker via a button on the Filings page; it runs one Haiku call per ticker against the latest 10-K's `item_1_business` filing section. Competitors are resolved to tickers via the existing counterparty resolver. Existing `relationship_type='competitor'` rows are removed from `relationships`, and the `SupplyChainEcosystem` card stops rendering its competitor bucket — the new section owns competition entirely.

## Background

The current pipeline already extracts business relationships (customer/supplier/partner/**competitor**/etc.) from filing sections (`services/edgar_relationships.py`), persists them as flat `(counterparty_name, relationship_type, magnitude_pct, verbatim_quote)` rows in the `relationships` table, and renders them in the `SupplyChainEcosystem` card grouped by relationship type. That flat shape loses the segment / area-of-competition structure that 10-Ks typically present in their Competition subsection (see screenshot reference: IIVI's 10-K has a clear two-segment table — Photonic Solutions and Compound Semiconductors — with named areas of competition under each segment, and ~30 named competitors total).

The motivating insight: **segment context determines competitive impact.** A competitor in a small/declining segment is a different kind of signal from a competitor in a large/growing one. The extraction needs to preserve segment scope, not just names.

## Goals

- Faithful reconstruction of the Competition table as it appears in Item 1 of the 10-K — segment, area-of-competition, list of named competitors.
- Per-segment narrative summary (2–3 sentences) covering segment scale, end markets, and growth direction, drawn only from Item 1 text.
- Resolved competitors get clickable tickers that route to `/pipeline/new?ticker=…` when the competitor is tracked in any theme.
- Cleanly separate "supply chain" (who you depend on / who depends on you) from "competition" (who you fight).

## Non-goals

- Quantitative segment financials (segment revenue, growth %). Punted — XBRL segment reporting is messy enough to double scope; narrative-only is sufficient for v1.
- Wiring competition data into deep-dive prompts (`RELATIONSHIP_ROUTING`-style routing). Opt-in extraction means data may be missing; prompt routing currently relies on data being present. Defer.
- Fan-out integration. Competition extraction is per-ticker, button-triggered. Fan-out stays unchanged.
- Backfill across all already-ingested 10-Ks. On-demand only.
- Side-by-side competitor metric comparison (PE/market-cap chips next to each name). That's a Discovery-page-shaped feature.

## Architecture

```
[Trigger]                                  [Pipeline]                                              [Storage]

POST /api/filings/extract-              edgar_competition.py
competition/{ticker}                      └─ Load latest 10-K's item_1_business section
                              ───────►    └─ Truncate to 25 000 chars                    ───────►   filing_segments
"Extract competition" button              └─ One Haiku call (structured output via                  competitor_landscape
on Filings page (per ticker)                 assistant_prefill='{"segments":')                      filing_sections.competition_extracted_at
                                          └─ Persist segments + landscape rows
                                          └─ Stamp tombstone (even on zero-result)

                                          counterparty_resolver (existing, extended)
                                            └─ Walk competitor_landscape.competitors[] JSONB
                                            └─ Write resolved_to_cik / _ticker back into JSONB
                                            └─ Triggered automatically as last step of extract,
                                               and via existing POST /api/relationships/resolve/{ticker}

GET /api/competition/{ticker}             Deep-dive dashboard
                              ◄───────    └─ <Competition ticker={ticker} /> mounted between
                                             BusinessQuality and SupplyChainEcosystem
```

### Invariants

- **Idempotent.** `filing_sections.competition_extracted_at` tombstone is set on every attempt (including zero-segment results). Re-runs are no-ops unless caller passes `force=true`.
- **Single filing per ticker.** Only the most recent 10-K is consulted. 10-Q and DEF 14A are skipped (Competition lives in 10-K Item 1).
- **One Haiku call per re-run.** No fan-out integration in v1.
- **Section state.** Component fetches on mount via `competition.get(ticker)`. No streaming, no SSE.

## Data Model

### Migration: `<rev>_add_competition_tables.py`

Forward steps:
1. `CREATE TABLE filing_segments (...)`
2. `CREATE TABLE competitor_landscape (...)`
3. `ALTER TABLE filing_sections ADD COLUMN competition_extracted_at TIMESTAMPTZ NULL;`
4. `DELETE FROM relationships WHERE relationship_type = 'competitor';`

Backward steps reverse 1–3. Step 4 is **not** restored on downgrade — competitor rows that were extracted-then-deleted aren't recoverable from the down-migration. Acceptable: re-running `POST /api/filings/extract-relationships/{ticker}` against the same filings restores them, and the data is derivable.

### `filing_segments`

| column         | type            | constraints                            | notes                                                                                  |
| -------------- | --------------- | -------------------------------------- | -------------------------------------------------------------------------------------- |
| `id`           | uuid PK         |                                        |                                                                                        |
| `filing_id`    | uuid FK         | `filings.id` ON DELETE CASCADE         |                                                                                        |
| `ticker`       | varchar(16)     | NOT NULL                               | denormalized                                                                           |
| `segment_name` | varchar(256)    | NOT NULL                               | exact casing from filing                                                               |
| `narrative`    | text            | NOT NULL                               | LLM-extracted 2–3 sentence summary: end markets, growth/decline cues, scale signals   |
| `extracted_at` | timestamptz     | NOT NULL DEFAULT now()                 |                                                                                        |
| **unique**     |                 | (filing_id, segment_name)              |                                                                                        |
| **index**      |                 | (ticker)                               |                                                                                        |

### `competitor_landscape`

| column                | type            | constraints                                         | notes                                                            |
| --------------------- | --------------- | --------------------------------------------------- | ---------------------------------------------------------------- |
| `id`                  | uuid PK         |                                                     |                                                                  |
| `filing_id`           | uuid FK         | `filings.id` ON DELETE CASCADE                      |                                                                  |
| `ticker`              | varchar(16)     | NOT NULL                                            | denormalized                                                     |
| `segment_name`        | varchar(256)    | NOT NULL                                            | matches `filing_segments.segment_name` for join (no FK)          |
| `area_of_competition` | text            | NOT NULL                                            | left column from filing's competition table                      |
| `competitors`         | jsonb           | NOT NULL DEFAULT '[]'::jsonb                        | element shape below                                              |
| `extracted_at`        | timestamptz     | NOT NULL DEFAULT now()                              |                                                                  |
| **unique**            |                 | (filing_id, segment_name, area_of_competition)      |                                                                  |
| **index**             |                 | (ticker)                                            |                                                                  |

`competitors` JSONB element:

```json
{
  "name": "Lumentum Operations LLC",
  "name_normalized": "lumentum operations",
  "magnitude_pct": null,
  "verbatim_quote": "...optional sentence from the filing...",
  "resolved_to_cik": "0001633978",
  "resolved_to_ticker": "LITE"
}
```

`name_normalized` mirrors the existing `counterparty_resolver.normalize_name()` output and is precomputed at extraction time so resolver passes don't have to re-normalize. `resolved_to_cik` / `resolved_to_ticker` are `null` until the resolver runs.

### `filing_sections.competition_extracted_at`

`TIMESTAMPTZ NULL`. Mirrors the existing `relationships_extracted_at` pattern. Set on every extraction attempt — even when zero segments are extracted — so re-runs short-circuit without another Haiku call.

### Why two tables, not one

`filing_segments` is *per-segment* (1:N relationship to areas), `competitor_landscape` is *per-(segment, area)*. Flattening into one table would either:
- duplicate the narrative across rows, or
- move it to a column that's null on most rows.

Both are worse than the join. The frontend's render shape mirrors the storage shape (segment block → area sub-blocks → competitor chips), so reads are natural.

## Backend

### New service: `backend/app/services/edgar_competition.py`

```python
async def extract_ticker_competition(
    ticker: str,
    db: AsyncSession,
    *,
    force: bool = False,
) -> ExtractionSummary: ...
```

Returns:

```python
@dataclass
class ExtractionSummary:
    ticker: str
    filing_id: str | None
    segments_extracted: int
    areas_extracted: int
    competitors_extracted: int
    skipped: bool          # True when tombstone short-circuited
    errors: list[str]
```

Behavior:
1. Resolve latest 10-K: `SELECT * FROM filings WHERE ticker = :t AND form_type = '10-K' ORDER BY filing_date DESC LIMIT 1`. If none → `errors.append("no 10-K filed for {ticker}")`, return.
2. Look up `filing_sections` row with `(filing_id, section_key='item_1_business')`. If missing → `errors.append("item_1_business section not ingested")`, return.
3. If `competition_extracted_at IS NOT NULL` and `force=False` → return with `skipped=True`, no Haiku call.
4. Truncate section text to **25 000 chars** (Item 1 averages 30–60K; the Competition subsection is reliably in the first half).
5. One Haiku call (`HAIKU` model from `graph/llm.py`) with structured output via `assistant_prefill='{"segments":'` and `parse_structured_output(..., ExtractionResult)`. Mirrors the pattern in `edgar_relationships.py`.
6. For each `CompetitionSegment`: insert into `filing_segments` (skip on `(filing_id, segment_name)` conflict).
7. For each `(segment, area)`: insert into `competitor_landscape` with the `competitors[]` JSONB array. Each competitor gets `name_normalized` precomputed; `resolved_to_*` left null.
8. Stamp `filing_sections.competition_extracted_at = now()` regardless of segment count.
9. Call `resolve_competition_for_ticker(ticker, db)` (see resolver section).
10. Commit.

### Pydantic schema (LLM output contract)

```python
class CompetitorRef(BaseModel):
    name: str = Field(..., description="Exact casing from the filing.")
    magnitude_pct: float | None = None
    verbatim_quote: str | None = Field(
        None,
        description="Optional anchoring sentence from the filing (≤200 chars).",
    )

class CompetitionArea(BaseModel):
    area_of_competition: str = Field(
        ...,
        description="Left-column text from the competition table (e.g., 'Optical components for laser systems').",
    )
    competitors: list[CompetitorRef]

class CompetitionSegment(BaseModel):
    segment_name: str = Field(
        ...,
        description="Segment name as the filer uses it. Use 'Overall' for single-segment companies that don't name a segment.",
    )
    narrative: str = Field(
        ...,
        description="2–3 sentence summary of segment scope, end markets, and growth direction. From Item 1 text only — do not invent numbers.",
    )
    areas: list[CompetitionArea]

class ExtractionResult(BaseModel):
    segments: list[CompetitionSegment] = Field(default_factory=list)
```

### Prompt (system) — high-level rules

- Extract the Competition disclosure from Item 1 of a 10-K.
- Capture every Segment / Area / Competitor as written in the filing — **do not** infer from background knowledge.
- Single-segment companies → return one segment with `segment_name="Overall"` (or the filer's own framing).
- Skip generic competitive language ("we face competition from numerous companies"); only extract when the filer names competitors *or* names a competitive arena (area of competition).
- For `narrative`: pull cues from Item 1 about segment scale, end markets, and growth direction. 2–3 sentences. No invented numbers.
- Output strict JSON matching the schema. Empty `segments` array if no Competition disclosure is present.

### Resolver extension — `services/counterparty_resolver.py`

Add:

```python
async def resolve_competition_for_ticker(
    ticker: str, db: AsyncSession
) -> ResolutionSummary:
    """Walk all competitor_landscape rows for ticker, attempt to resolve each
    unresolved competitor name in the JSONB array, write resolved_to_cik /
    _ticker back into the array, persist."""
```

Behavior:
- For each `competitor_landscape` row where any element has `resolved_to_cik IS NULL`:
  - For each unresolved element, call existing `_match_to_canonical(name_normalized) -> (cik, ticker, score) | None`.
  - On exact match or RapidFuzz `token_set_ratio ≥ 95`, write `resolved_to_cik` / `resolved_to_ticker` into the JSONB element. Auto-resolve threshold matches existing relationship resolver.
  - Score 80–94 → leave unresolved (existing resolver behavior is to queue, but `competitor_landscape` doesn't have a curation queue in v1; we just leave it `null`).
- `UPDATE competitor_landscape SET competitors = :new_competitors WHERE id = :id` for any row where ≥1 element changed.

The existing `POST /api/relationships/resolve/{ticker}` endpoint is extended to call `resolve_competition_for_ticker` after the existing relationship resolution pass, so a single resolve action covers both surfaces.

### API endpoints

| Method | Path                                                | Behavior                                                                                          |
| ------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `POST` | `/api/filings/extract-competition/{ticker}?force=false` | Triggers extraction. Returns `ExtractionSummary` JSON. 404 if no 10-K. 409 if no Item 1 section ingested. |
| `GET`  | `/api/competition/{ticker}`                         | Returns the read shape (below). 404 if extraction never run.                                      |

### Read shape (`GET /api/competition/{ticker}`)

```ts
{
  ticker: string,
  filing: {
    accession_number: string,
    form_type: "10-K",
    filing_date: string,            // ISO date
    sec_filing_url: string | null,  // EDGAR URL for the filing index
  } | null,
  extracted_at: string | null,      // ISO datetime, null if never extracted
  segments: Array<{
    segment_name: string,
    narrative: string,
    areas: Array<{
      area_of_competition: string,
      competitors: Array<{
        name: string,
        ticker: string | null,        // resolved ticker, or null
        magnitude_pct: number | null,
        verbatim_quote: string | null,
        tracked: boolean,             // true if ticker is in any theme.seed_tickers
      }>,
    }>,
  }>,
}
```

`tracked` is computed on read by joining the resolved tickers against the seed_tickers union across all themes (single query). Powers the click-through affordance in the UI.

### Existing code touched

- `services/supply_chain.py`:
  - Drop `"competitor"` from `_reciprocal_types_for` so reconciliation passes don't try to find reciprocal "competitor↔competitor" pairs (those rows no longer exist in `relationships`).
  - Drop competitor handling from `summarize_for_card`. Existing `select` filter by `relationship_type` already excludes deleted rows; the type-list rendering needs a one-line update to no longer include competitor in display order.
- `frontend/components/deep-dive/sections/SupplyChainEcosystem.tsx`:
  - Drop `"competitor"` from `TYPE_ORDER` and `TYPE_LABEL`. Section header copy unchanged.

### Other touched code

- `services/edgar_relationships.py` — drop `"competitor"` from the relationship_type list in both the system prompt and the Pydantic field description. Without this, future `extract_ticker_relationships` passes would re-create competitor rows in the `relationships` table after we deleted them, defeating the migration cleanup.

### Not touched (intentionally)

- `services/fanout.py` — competition extraction is opt-in per ticker, not part of fan-out.
- `graph/nodes.py` — `RELATIONSHIP_ROUTING` and the deep-dive prompts still receive the existing counterparty payload (now without competitors). Wiring competition data into prompts is deferred to a follow-up because the data may be missing.

## Frontend

### New section component: `frontend/components/deep-dive/sections/Competition.tsx`

Pattern mirrors `SupplyChainEcosystem`:
- Client component (`"use client"`).
- Fetch on mount via `competition.get(ticker)` from `lib/api.ts`.
- `usePersistedCollapse("competition")` for top-level header collapse.
- Per-segment cards collapsible independently (default: first segment expanded, rest collapsed).
- Surface tokens identical to existing sections (`var(--color-border)`, `var(--color-surface)`, `var(--color-bg)`).

### Layout sketch

```
┌─ Competition ───────────────── 3 segments · 14 competitors · 10-K 2025-09-12 ▾
│
│  ┌─ Photonic Solutions ────────────────────────────────────────────── ▾
│  │  Optical components for datacenter and telecom optical communications;
│  │  largest segment by revenue, growing on AI-driven datacenter capex.
│  │
│  │  Optical components, modules, subsystems for optical comms
│  │    [Cisco $CSCO ↗] [Lumentum $LITE ↗] [Molex] [Accelink] [InnoLight]
│  │    [Eoptolink] [InLC] [Intel Data Platforms] [O-Net]
│  │
│  │  Optical and crystal components for lasers and metrology
│  │    [IDEX $IEX ↗] [On Semi $ON ↗] [CASTECH] [Casix] [Optowide] [REO]
│  └────────────────────────────────────────────────────────────────────
│
│  ┌─ Compound Semiconductors ───────────────────────────────────────── ▸
│  ┌─ … ─────────────────────────────────────────────────────────────── ▸
└──────────────────────────────────────────────────────────────────────
```

### Competitor chip rendering

| State                     | Render                              | Behavior                                          |
| ------------------------- | ----------------------------------- | ------------------------------------------------- |
| Resolved + tracked        | `[Lumentum $LITE ↗]`                | name → `<Link>` to `/pipeline/new?ticker=LITE`   |
| Resolved, not tracked     | `[Cisco $CSCO]`                     | ticker shown, no link                             |
| Unresolved                | `[Accelink]`                        | name only                                         |
| Has `verbatim_quote`      | tooltip via `title` attr            | hover shows the anchor sentence                   |

### States

| State               | Render                                                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| `extracted_at=null` | "No competition extracted yet. Visit the [Filings page] to ingest 10-K and extract competition." (link)   |
| `segments=[]`       | "Latest 10-K disclosed no structured competition information."                                              |
| Loading             | `Loading…` placeholder                                                                                     |
| Network error       | Muted error text in section shell                                                                          |

### Filings page changes

- `components/filings/TickerFilingsCard.tsx`: new "Extract competition" button alongside existing actions ("Ingest", "Extract relationships", "Resolve", "Fan out").
- Button states: `idle` → "Extract competition" / `running` → spinner / `done` → "Re-extract" + `extracted YYYY-MM-DD` badge.
- `force=true` when re-extracting; `force=false` first time.
- Inline summary on completion (`3 segments, 14 competitors`).

### Section registry

`frontend/components/deep-dive/sections.ts` — insert into `Context` group between `business_quality` and `supply_chain`:

```ts
{ id: "competition", label: "Competition" },
```

SectionNav and Cmd-K palette pick it up automatically (single-source registry contract documented in CLAUDE.md).

### Dashboard mount

`frontend/components/deep-dive/DeepDiveDashboard.tsx` — render `<Competition ticker={ticker} />` between `<BusinessQuality />` and `<SupplyChainEcosystem />`.

### API client additions

`frontend/lib/api.ts`:

```ts
export interface CompetitorChip {
  name: string;
  ticker: string | null;
  magnitude_pct: number | null;
  verbatim_quote: string | null;
  tracked: boolean;
}
export interface CompetitionArea {
  area_of_competition: string;
  competitors: CompetitorChip[];
}
export interface CompetitionSegment {
  segment_name: string;
  narrative: string;
  areas: CompetitionArea[];
}
export interface CompetitionData {
  ticker: string;
  filing: { accession_number: string; form_type: "10-K"; filing_date: string; sec_filing_url: string | null } | null;
  extracted_at: string | null;
  segments: CompetitionSegment[];
}
export interface CompetitionExtractionSummary {
  ticker: string;
  filing_id: string | null;
  segments_extracted: number;
  areas_extracted: number;
  competitors_extracted: number;
  skipped: boolean;
  errors: string[];
}

export const competition = {
  get: (ticker: string) => apiClient<CompetitionData>(`/api/competition/${ticker}`),
  extract: (ticker: string, force = false) =>
    apiClient<CompetitionExtractionSummary>(
      `/api/filings/extract-competition/${ticker}?force=${force}`,
      { method: "POST" }
    ),
};
```

### Print + a11y

- Section included in print output by default; collapse toggles tagged `data-print-hide="true"` so PDFs render fully expanded.
- Segment-card collapse triggers are `<button>` with `aria-expanded` / `aria-controls`.
- Competitor chips use sufficient gap and text-size for tap targets on mobile.

### Not in v1

- Compare metrics (PE / market-cap chips next to competitor names) — Discovery-shaped feature.
- Competitor-to-competitor graph view — supply chain already shows the 1-hop graph.

## Risks

| Risk                                                   | Likelihood | Mitigation                                                                                                                                    |
| ------------------------------------------------------ | ---------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 10-K has no structured competition table               | Medium     | Extractor returns single `segment_name="Overall"` with one area; narrative carries the load. Empty-state UI handles fully zero case.          |
| 25K-char truncation cuts off Competition subsection    | Low        | If `segments==[]` is common, log section length + heading anchor positions; v2 fix is to anchor-extract just the Competition subsection.      |
| Counterparty resolver false-positive on short names    | Medium     | Existing `≥95` threshold inherited. If false-positives appear in practice (e.g. "Apple" matching the wrong CIK), raise threshold per surface. |
| No 10-K filed (recent IPO)                             | Low        | Empty-state UI states "No 10-K filed yet" via the `filing=null` field on the read shape.                                                       |
| Stale data after new 10-K is ingested                  | Low        | "Re-extract" button (force=true) is documented in the label. Manual workflow acceptable for v1.                                               |
| Future `extract_ticker_relationships` re-creates competitor rows | High if not addressed | Update `edgar_relationships.py` prompt + Pydantic enum to drop `"competitor"` from valid types.                                                |

## Implementation Order

Each step independently shippable; manual smoke check between each.

1. **Schema + migration.** Alembic revision creating `filing_segments`, `competitor_landscape`, adding `filing_sections.competition_extracted_at`, deleting `relationship_type='competitor'` rows. Verify forward + back on a freshly-restored DB.
2. **Pydantic models + extractor service.** `services/edgar_competition.py`. Smoke against one ingested 10-K (IIVI as worked example).
3. **Resolver extension.** `resolve_competition_for_ticker` in `services/counterparty_resolver.py`. Verify resolution rate on the IIVI test case.
4. **API endpoints.** `POST /api/filings/extract-competition/{ticker}` + `GET /api/competition/{ticker}`. Smoke with curl.
5. **Frontend section component.** `Competition.tsx` + `sections.ts` entry + `DeepDiveDashboard` mount + `lib/api.ts` types. Verify in browser against IIVI.
6. **Filings page button.** "Extract competition" per ticker card with status badge.
7. **Cleanup.** Remove `competitor` from `SupplyChainEcosystem` `TYPE_ORDER` / `TYPE_LABEL` and from `_reciprocal_types_for` in `supply_chain.py`. Drop `"competitor"` from `edgar_relationships.py` prompt + Pydantic enum so future extractions don't re-create the rows. Verify Supply Chain card renders cleanly.

## Success Criteria

- [ ] Migration runs forward and back cleanly on a freshly-restored DB.
- [ ] `extract_ticker_competition("IIVI", force=True)` produces ≥2 segments matching the screenshot's structure (Photonic Solutions + Compound Semiconductors).
- [ ] `GET /api/competition/IIVI` returns data with at least 5 competitors having non-null `ticker` (resolver hit rate sanity check on a known-good case).
- [ ] Deep-dive dashboard for IIVI renders the Competition section between Business Quality and Supply Chain; clicking a tracked competitor chip navigates to `/pipeline/new?ticker=…`.
- [ ] `SupplyChainEcosystem` no longer renders a "Competitors" bucket (visual diff against current state).
- [ ] Re-running extraction with `force=false` is a no-op (returns summary with `skipped=true`, no Haiku call).
- [ ] Re-running `extract_ticker_relationships` for any ticker does not produce new `relationship_type='competitor'` rows.

## Out of scope (follow-ups)

- Wiring competition data into deep-dive prompts (`RELATIONSHIP_ROUTING`-style routing for the Competition payload).
- Quantitative segment financials (XBRL `us-gaap:SegmentReporting*` extraction).
- Backfill across all already-ingested 10-Ks.
- Fan-out integration.
- Side-by-side competitor metric comparison surface.
