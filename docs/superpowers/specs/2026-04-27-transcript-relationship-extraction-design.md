# Transcript Relationship Extraction — Design

**Date:** 2026-04-27
**Status:** Design approved; awaiting implementation plan
**Author:** Eric (with Claude)

## Problem

Earnings call transcripts often disclose counterparty announcements (new partnerships, customer wins, supplier issues) 1–2 quarters before they appear in a 10-K. Today these transcripts are fetched on-demand inside `node_deep_dive`, run through 6 Haiku transcript-analysis passes, and only the analysis output lands in `ResearchState.transcript_analysis`. The structured `relationships` graph that powers counterparty resolution (Phase C), the supply-chain ecosystem UI (Phase D), and the deep-dive prompt counterparty context (Phase E) sees none of that signal.

Goal: surface transcript-disclosed counterparties into the existing `relationships` table so they automatically participate in resolution, the graph, and prompt context — without persisting raw transcript text.

## Goals / Non-goals

**Goals**

- Extract counterparty mentions from the last 4 quarters of earnings call transcripts per ticker.
- Persist them in the existing `relationships` table with full provenance (year, quarter).
- Wire the new extractor into `FanoutService` so theme/ticker fan-out runs filings + transcripts in one pass.
- Idempotent re-runs (no Haiku spend on already-extracted transcript-quarters, including zero-result ones).
- Force flag for re-extraction.

**Non-goals**

- Persist raw transcript text. (Future option — see Future-compat section.)
- Split prepared remarks vs Q&A. Treat each transcript as one section, truncated to 15K chars; analyst Q&A is filtered at the prompt level via a single new rule.
- Net-new ad-hoc inspection endpoint beyond the per-ticker extractor.
- Frontend changes beyond surfacing the new error type in the existing fanout status panel.

## Architecture

### Data model

**`relationships` table — additive change**

```
filing_id           CHANGE TO NULLABLE                       -- existing
source_type         VARCHAR(16)  NOT NULL DEFAULT 'filing'   -- 'filing' | 'transcript'
transcript_year     INTEGER      NULL
transcript_quarter  SMALLINT     NULL
```

CHECK constraint:

```sql
(source_type = 'filing' AND filing_id IS NOT NULL)
OR (source_type = 'transcript'
    AND filing_id IS NULL
    AND transcript_year IS NOT NULL
    AND transcript_quarter IS NOT NULL)
```

**Unique constraint replacement.** Postgres treats NULLs as distinct in unique constraints, so the existing `uq_relationships_filing_section_counterparty_type` collapses for transcript rows (every NULL `filing_id` is "different"). Replace with two partial unique indexes:

```sql
CREATE UNIQUE INDEX uq_relationships_filing
  ON relationships (filing_id, section_key, counterparty_name, relationship_type)
  WHERE filing_id IS NOT NULL;

CREATE UNIQUE INDEX uq_relationships_transcript
  ON relationships (ticker, transcript_year, transcript_quarter, counterparty_name, relationship_type)
  WHERE filing_id IS NULL;
```

Drop the existing `uq_relationships_filing_section_counterparty_type` constraint.

**`section_key` convention** for transcript rows: `transcript_{YYYY}_q{N}` (e.g. `transcript_2026_q1`). Fits in existing `String(64)`.

**New `transcript_extractions` table** (idempotency tombstone):

```python
class TranscriptExtraction(Base):
    __tablename__ = "transcript_extractions"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    quarter: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )
    relationships_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

`force=True` deletes the row before re-running. Zero-relationship transcripts still get a row stamped (matches Phase B `filing_sections.relationships_extracted_at` semantics).

### Extractor: `services/edgar_transcripts_relationships.py`

Mirrors `services/edgar_relationships.py`. New module to keep transcript-specific orchestration separate from filing orchestration; the prompt and Haiku call helper are reused from the filing module.

Public entry point:

```python
async def extract_ticker_transcript_relationships(
    ticker: str,
    fmp: FMPClient,
    db: AsyncSession,
    *,
    force: bool = False,
) -> dict:
    """Returns a summary dict with the same shape as
    edgar_relationships.extract_ticker_relationships:
      {
        "ticker": str,
        "transcripts_considered": int,
        "transcripts_extracted": int,
        "transcripts_skipped_existing": int,
        "relationships_added": int,
        "relationships_dropped": int,
        "per_transcript": [...],
        "errors": [str, ...],
      }
    """
```

Per-quarter flow:

1. Fetch transcripts via `fmp.get_earnings_transcript(ticker)`. The existing transcript-analysis path slices `transcripts[:4]`, so we adopt the same convention: take whatever FMP returns and process the first 4. Open question for the implementation plan: confirm via a real call (BWXT or ORCL) whether FMP's `earning-call-transcript-latest` endpoint actually returns 4+ entries — if not, fall back to N enumerated `(year, quarter)` calls. Either way the extractor's contract is "extract from the last 4 quarters available."
2. For each `(ticker, year, quarter)`:
   - Look up `transcript_extractions` row. If present and not `force`, skip.
   - If `force`, `DELETE FROM transcript_extractions WHERE …` and `DELETE FROM relationships WHERE ticker=… AND filing_id IS NULL AND transcript_year=… AND transcript_quarter=…` first.
   - Truncate the transcript `content` field to 15K chars.
   - Call `_call_haiku_on_section` from `edgar_relationships.py` with:
     - `ticker=ticker.upper()`
     - `form_type="Earnings Call Q{q} {y}"`
     - `filing_date=transcript.date` (FMP returns ISO date)
     - `section_key="transcript_{y}_q{q}"`
     - `heading="{TICKER} Q{q} {y} Earnings Call"`
     - `text=truncated_content`
   - On Haiku error: append to `summary['errors']`, do NOT stamp the tombstone (so the next run retries). Match Phase B semantics.
   - On success: dedupe by `(counterparty_name, relationship_type)` (set-based, matches Phase B). Insert `Relationship` rows with `source_type='transcript'`, `filing_id=None`, `transcript_year`, `transcript_quarter`, populated.
   - Stamp `transcript_extractions(ticker, year, quarter, extracted_at, relationships_added)`.
3. `await db.flush()` at the end. Caller commits (matches existing pattern in `api/filings.py` and `services/fanout.py`).

Empty FMP response → return early with `summary['errors'].append(f"no transcripts available for {ticker}")`. No DB writes.

### Prompt edits in `edgar_relationships.py`

Two surgical changes to the existing `_SYSTEM_PROMPT`:

1. Opening line: `"from SEC filing sections"` → `"from SEC filing sections or earnings call transcripts"`.
2. Add one bullet to the Rules block:
   > `- Skip analysts and brokerage firm participants in earnings call Q&A — they ask questions but are not counterparties.`

The user template (`_USER_TEMPLATE`) is unchanged. The transcript caller passes a transcript-flavored `form_type` so the prompt context surfaces the source naturally.

### API endpoint

`POST /api/transcripts/extract-relationships/{ticker}?force=false`

- Returns the summary dict from the extractor.
- Response shape mirrors the filing extractor (callers can switch on `transcripts_*` keys vs `sections_*` keys to tell them apart).
- Implementation: thin wrapper in `api/filings.py` (or a new `api/transcripts.py` if `filings.py` is getting heavy — implementation plan to decide).

### FanoutService integration

Per-ticker stage list grows from 3 to 4:

```
ingest filings → extract-filings → extract-transcripts → resolve
```

- Each stage runs in its own `async_session()` with an explicit `await db.commit()` (matches existing `services/fanout.py` pattern; `async_session` is `expire_on_commit=False` but does NOT autocommit).
- The new `extract-transcripts` stage calls `extract_ticker_transcript_relationships(ticker, fmp, db, force=force)`.
- Per-quarter errors append to `FanoutStatus.errors[]`. They do NOT abort the per-ticker loop or the outer ticker-list loop.
- Single `force` flag (the existing `?force=` query param on the fan-out endpoints) applies to both extract stages.
- Resolver runs once at the end and reads `Relationship.ticker` rows where `resolved_to_cik IS NULL` — picks up transcript-sourced rows automatically.
- `FanoutStatus` schema is unchanged. The `errors[]` list is already a flat string array.

### Read-side ripple effects

None of the existing read paths change.

- `relationship_context.py` reads `Relationship` by the denormalized `ticker` column — transcript rows participate naturally. The `_build_counterparty_context` closure in `node_deep_dive` will render transcript-sourced counterparties identically to filing-sourced ones (same buckets, same `$TICKER` resolved-notation, same magnitude rendering).
- `supply_chain.py` graph endpoint reads by ticker — transcript-sourced edges appear with the same `verbatim_quote`, `magnitude_pct`, `unnamed`, `confirmed_bilateral` fields.
- `counterparty_resolver.py` `resolve_ticker_relationships` reads `Relationship.ticker` rows where `resolved_to_cik IS NULL`. Write-through populates all matching rows for a given alias — applies uniformly to transcript and filing rows.
- `Relationship` model's `__table_args__` updated to drop the old `UniqueConstraint` and rely on the partial indexes (defined in the migration; not all index types are expressible in SQLAlchemy `__table_args__`, so this is migration-only).

### Frontend

No structural changes for v1.

- The fan-out status panel renders `FanoutStatus.errors[]` as a flat list — new transcript errors surface automatically.
- The `/filings` page tracks per-ticker extraction status today; it will continue to work because the existing `GET /api/filings/{ticker}/relationships` endpoint reads from `Relationship` and will return both filing and transcript rows.
- Optional v1.5 polish (out of scope here): badge transcript-sourced rows in `SupplyChainEcosystem` with a small "Earnings call Q1 2026" tooltip annotation. Requires plumbing `source_type` + `transcript_year/quarter` through the supply-chain graph response.

## Verification

Pick BWXT or ORCL — recent earnings call should mention partners not yet in the latest 10-K.

1. Empty DB → run extractor (`POST /api/transcripts/extract-relationships/{ticker}`) → assert 4 rows in `transcript_extractions`, multiple `relationships` rows with `source_type='transcript'`, `filing_id IS NULL`, `transcript_year` and `transcript_quarter` populated.
2. At least one transcript-sourced counterparty does NOT appear in any filing-sourced row (the whole point — partnerships announced on a call but not yet in the next 10-K).
3. Re-run with `force=False` → assert zero new rows, all 4 transcripts skipped via tombstone.
4. Re-run with `force=True` → assert old transcript-sourced rows deleted, new ones inserted, tombstones updated.
5. Run `POST /api/relationships/resolve/{ticker}` → assert transcript rows get `resolved_to_cik` populated for known counterparties (e.g. "Microsoft Azure" → MSFT, "AWS" → AMZN if alias exists).
6. `GET /api/relationships/graph/{ticker}` → assert transcript-sourced edges appear in `nodes[]` and `edges[]` with the same shape as filing-sourced edges.
7. Run a deep-dive on the same ticker → inspect the prompt context (via DEBUG-level log of the constructed prompt) and confirm transcript-sourced names appear alongside filing ones in the `RESOLVED COUNTERPARTIES` block.
8. Edge case — ticker with no transcripts available (recent IPO, foreign ADR FMP doesn't cover): assert `summary['errors']` contains `"no transcripts available for …"`, no DB writes, no exceptions.
9. Edge case — Haiku transient error mid-extraction: assert tombstone is NOT written for the failed quarter (so next run retries), but tombstones for successful quarters in the same run ARE written.
10. 2-ticker theme fan-out via the existing UI button → assert both `extract-filings` and `extract-transcripts` errors surface in `FanoutStatus.errors[]` independently per stage.

## Migration

One Alembic revision. Order matters:

1. Make `relationships.filing_id` nullable.
2. Add columns: `source_type VARCHAR(16) NOT NULL DEFAULT 'filing'`, `transcript_year INTEGER NULL`, `transcript_quarter SMALLINT NULL`.
3. Backfill existing rows: `UPDATE relationships SET source_type = 'filing'` (already covered by DEFAULT but be explicit for any race).
4. Add CHECK constraint named `ck_relationships_source_consistency`.
5. Drop existing `uq_relationships_filing_section_counterparty_type`.
6. Create the two partial unique indexes (`uq_relationships_filing`, `uq_relationships_transcript`).
7. Create `transcript_extractions` table.

Downgrade should be the reverse, with the caveat that any transcript-sourced rows must be deleted before reverting `filing_id` to NOT NULL.

## Future-compat with option C

If we later want to persist raw transcript text (option C from the brainstorm — useful for debugging extractions, custom downstream prompts, or training data):

1. Add a `transcripts` table parallel to `filings` with `(id, ticker, year, quarter, fetched_at, content TEXT, citation_url)`.
2. Add `relationships.transcript_id` FK.
3. Backfill `transcript_id` by matching `(ticker, transcript_year, transcript_quarter)` against the new `transcripts` rows.
4. Drop `transcript_year`, `transcript_quarter` scalar columns.

No data loss. No breaking change to consumers — `Relationship.ticker`, `relationship_type`, `counterparty_name` etc. all stay put.

## Cost estimate

Per ticker, per fan-out:

- 4 Haiku calls × ~3.5K input tokens (15K chars) × ~500 output tokens
- ≈ 14K input + 2K output tokens per ticker
- At Haiku 4.5 pricing (~$0.80/MTok input, $4/MTok output): ~$0.02/ticker/fan-out

A theme fan-out of 10 tickers ≈ $0.20. Idempotency means daily re-runs only re-spend on new transcripts (one new transcript per quarter per ticker on average → trivial steady-state cost).
