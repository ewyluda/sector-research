# Earnings Call Transcript Delta Analysis — Design

**Date:** 2026-05-11
**Status:** Approved, ready for implementation plan
**Effort:** ~1–1.5 days

## Purpose

Detect quarter-over-quarter shifts in management's language across the most
recent 4 earnings calls, organized by the same 9 deep-dive categories used
elsewhere in the app. Produces a signal that is anchored to the user's own
thesis taxonomy and is not available from any off-the-shelf data vendor.

Reuses the existing transcript-ingest infrastructure built for
Phase B-T relationship extraction (see
`docs/superpowers/specs/2026-04-27-transcript-relationship-extraction-design.md`).

## Out of scope

- Multi-ticker comparison ("compare NVDA vs AMD")
- Sentiment-score numerical extraction
- Cross-quarter chart visualization
- Auto-trigger cron when a new transcript appears (deferred to v2)
- Integration into discovery ranking

## Comparison axes

The 9 deep-dive categories, used as a **nullable** set:

`business_quality`, `risk_assessment`, `growth_earnings`,
`sentiment_narrative`, `management_governance`, `future_durability`,
`macro_regime`, `financial_health`, `valuation_stage`.

The Haiku prompt is instructed to return `null` for any axis the transcript
does not materially address. This keeps the vocabulary consistent with the
rest of the app while preventing the model from inventing deltas on axes
that earnings calls don't typically cover (Macro & Regime, Financial
Health, Valuation & Stage are sparse by nature).

## Quarter window

Latest 4 transcripts via the existing `fetch_recent_transcripts(ticker, limit=4)`
helper in `backend/app/services/edgar_transcripts_relationships.py`. No new
FMP coverage required.

If FMP returns fewer than 2 transcripts (recent IPO, coverage gap), the
endpoint returns 404 — there is no delta to compute from a single call.

## Output shape

```python
class QuoteRef(BaseModel):
    year: int
    quarter: int            # 1-4
    role: str               # CEO / CFO / IR / analyst
    text: str               # verbatim, <=300 chars

class AxisDelta(BaseModel):
    direction: Literal["softening", "strengthening", "stable"]
    magnitude: Literal["minor", "material", "regime_change"]
    summary: str            # 1-2 sentences
    quotes: list[QuoteRef]  # 1-3 anchoring quotes

class AxesDelta(BaseModel):
    business_quality: AxisDelta | None = None
    risk_assessment: AxisDelta | None = None
    growth_earnings: AxisDelta | None = None
    sentiment_narrative: AxisDelta | None = None
    management_governance: AxisDelta | None = None
    future_durability: AxisDelta | None = None
    macro_regime: AxisDelta | None = None
    financial_health: AxisDelta | None = None
    valuation_stage: AxisDelta | None = None
```

Stored in JSONB as `{category_key: {direction, magnitude, summary, quotes: [...]} | null}`.

## Storage

New table `transcript_deltas` (migration to be authored):

```
id                       uuid pk
ticker                   text not null
transcripts_window       jsonb not null   -- [{year:2025,quarter:4}, ...]
transcripts_fingerprint  text not null    -- sha1 of sorted (year,quarter) tuples
axes                     jsonb not null   -- AxesDelta.model_dump()
computed_at              timestamptz not null default now()

unique constraint        (ticker, transcripts_fingerprint)
index                    (ticker, computed_at desc)
```

The fingerprint design gives free idempotency: re-running with the same 4
transcripts is a SELECT, not a Haiku call. When a new transcript drops,
the fingerprint changes and a new row is inserted alongside the old one
(history preserved — useful for retrospective "what was the delta picture
last quarter?" queries). Latest-by-ticker is one `ORDER BY computed_at DESC`
away.

History is capped at 8 rows per ticker via a delete-oldest sweep at write
time (small fixed bound, no scheduler needed).

## Service

`backend/app/services/transcript_delta.py`:

```python
async def compute_delta(
    *, ticker: str, db: AsyncSession, fmp: FMPClient, force: bool = False
) -> TranscriptDelta:
    """
    1. Fetch last 4 transcripts via fetch_recent_transcripts.
    2. If <2 transcripts available, raise InsufficientTranscriptsError.
    3. Compute fingerprint = sha1(sorted (year,quarter) tuples).
    4. SELECT existing row by (ticker, fingerprint); return early unless force.
    5. Haiku call with structured output (AxesDelta).
    6. Persist new row, trim history if >8 rows for this ticker.
    7. Return the new row.
    """
```

Prompt structure (single Haiku call, ~4-6K tokens in, ~2-3K out):

- **System:** anchors the 9 deep-dive categories by name + key, explicit
  "return null when transcript doesn't materially address this axis,
  prefer null over filler", verbatim-quote requirement, direction/magnitude
  enums fully enumerated.
- **User:** 4 transcripts concatenated with explicit `=== Q4 2025 ===`
  separators and speaker labels preserved, ordered **newest first**.
- **Output:** structured via `assistant_prefill='{"axes":'` (same
  pattern as `edgar_relationships.py` / `model_baseline_node.py`).

Citations: the FMP transcript fetch citations from `fetch_recent_transcripts`
are surfaced in the response (not persisted on the delta row — the
fingerprint plus `transcripts_window` is sufficient for traceability).

## API

```
POST /api/transcripts/delta/{ticker}?force=false
  -> 200  TranscriptDeltaRead   (computed or cached)
  -> 404  if FMP returns <2 transcripts

GET  /api/transcripts/delta/{ticker}/latest
  -> 200  TranscriptDeltaRead
  -> 204  if no delta has been computed yet for this ticker

GET  /api/transcripts/delta/{ticker}/history
  -> 200  list[TranscriptDeltaRead]   (oldest → newest, capped at 8)
```

Ticker is normalized via the existing `TickerPath` FastAPI dependency.
POST is intentionally non-idempotent at the HTTP layer (cache vs recompute
distinction is meaningful) but idempotent at the data layer via the
unique constraint.

Router prefix: `/api/transcripts`. Mounted in `main.py` alongside the
existing routers.

## Frontend

New component `frontend/components/deep-dive/sections/WhatChangedPanel.tsx`:

- Slot: deep-dive page, **immediately above Management & Governance**.
- Mount: calls `transcriptDeltaApi.getLatest(ticker)`.
- 204 → renders a "Compute transcript delta" CTA button that calls
  `transcriptDeltaApi.compute(ticker)` and re-renders on response.
- 200 → renders a compact axis grid: only non-null categories, each card
  with a direction chip (softening = red, strengthening = green,
  stable = neutral), magnitude badge, summary, and expandable quote list.
- "Recompute" button in the panel header for `?force=true`.
- Registers in `frontend/components/deep-dive/sections.ts` so SectionNav
  and CommandPalette pick it up automatically.
- Print-view friendly: no sticky elements, no fetches on render once
  hydrated. `data-print-hide="true"` on action buttons only.

Typed client additions in `frontend/lib/api.ts`:

```ts
type AxisDirection = "softening" | "strengthening" | "stable";
type AxisMagnitude = "minor" | "material" | "regime_change";

interface QuoteRef { year: number; quarter: 1|2|3|4; role: string; text: string; }
interface AxisDelta { direction: AxisDirection; magnitude: AxisMagnitude;
                       summary: string; quotes: QuoteRef[]; }
interface AxesDelta { business_quality: AxisDelta | null;
                       risk_assessment:  AxisDelta | null;
                       /* ... all 9 categories ... */ }
interface TranscriptDeltaRead {
  id: string;
  ticker: string;
  transcripts_window: { year: number; quarter: number }[];
  axes: AxesDelta;
  computed_at: string;
}

export const transcriptDeltaApi = {
  compute(ticker: string, opts?: { force?: boolean }): Promise<TranscriptDeltaRead>;
  getLatest(ticker: string): Promise<TranscriptDeltaRead | null>;
  getHistory(ticker: string): Promise<TranscriptDeltaRead[]>;
};
```

## Workspace integration

`step_research` (Workspace Step 2) gains a single call before composing
its prompt:

```python
try:
    delta = await transcript_delta.compute_delta(
        ticker=ticker, db=db, fmp=fmp, force=False,
    )
except InsufficientTranscriptsError:
    delta = None
```

If `delta` is not None, the research prompt receives an additional
`{transcript_delta}` slot framed as: *"Recent transcript-language deltas,
organized by deep-dive category. Use as priors when researching — these
are language shifts the company itself has signaled."*

`force=False` means the workspace reuses the cache when transcripts
haven't changed; the delta is recomputed only when a new earnings call
has been ingested since the last workspace run.

## Tests

- `backend/tests/test_transcript_delta.py`:
  - Fingerprint determinism (same window → same hash)
  - Idempotency on repeat call (no second Haiku call, no second row)
  - Force-recompute path (Haiku called, new row inserted)
  - Insufficient-transcripts → `InsufficientTranscriptsError`
  - History cap (writing the 9th row evicts the oldest)
  - JSONB round-trip (axes dict → ORM → API → dict)
- `backend/tests/test_transcripts_delta_api.py`:
  - POST 200 happy path
  - POST 404 when transcripts empty
  - GET latest 204 when none
  - GET history ordering + cap
  - `?force=true` triggers recompute
- Haiku call mocked at the `complete()` / `complete_structured()` boundary;
  no live LLM in CI.

Target: 33+ → ~45 total backend tests after this lands.

## Migration

Single Alembic revision adding the `transcript_deltas` table + indexes +
unique constraint. Hand-written downgrade fully reverses (drops indexes,
constraint, then table) following the pattern established by recent
migrations (`12f874fd1d02`, `0b7ff9421fa5`).

## Files touched (estimate)

**Backend (new):**
- `backend/migrations/versions/<rev>_transcript_deltas.py`
- `backend/app/models/transcript_delta.py`
- `backend/app/models/transcript_delta_schemas.py`
- `backend/app/services/transcript_delta.py`
- `backend/app/api/transcripts_delta.py`
- `backend/tests/test_transcript_delta.py`
- `backend/tests/test_transcripts_delta_api.py`

**Backend (modified):**
- `backend/app/main.py` (register router)
- `backend/app/services/workspace_steps.py` (Step 2 wiring)
- `backend/app/models/workspace_schemas.py` (research-step prompt input shape)

**Frontend (new):**
- `frontend/components/deep-dive/sections/WhatChangedPanel.tsx`

**Frontend (modified):**
- `frontend/lib/api.ts` (typed client + types)
- `frontend/components/deep-dive/DeepDiveDashboard.tsx` (slot above Management & Governance)
- `frontend/components/deep-dive/sections.ts` (registry entry)
