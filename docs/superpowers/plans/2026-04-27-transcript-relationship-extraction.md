# Transcript Relationship Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract counterparty mentions from the last 4 quarters of earnings call transcripts per ticker into the existing `relationships` table so they participate in counterparty resolution, the supply-chain graph, and the deep-dive prompt counterparty context — without persisting raw transcript text.

**Architecture:** New service `services/edgar_transcripts_relationships.py` reuses `_call_haiku_on_section` from `services/edgar_relationships.py`. Transcript-sourced rows live in the same `relationships` table with `source_type='transcript'`, `filing_id=NULL`, `transcript_year`, `transcript_quarter`. Idempotency is tracked in a new `transcript_extractions` table (PK `(ticker, year, quarter)`). New API endpoint `POST /api/transcripts/extract-relationships/{ticker}`. `FanoutService` grows a 4th stage between `extract` and `resolve`.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + Pydantic v2 + Anthropic Haiku (claude-haiku-4-5-20251001) + FMP earnings-call transcript endpoint on the backend. Next.js 16 App Router + TypeScript on the frontend (types only — no UI changes for v1). No test framework is configured (per `CLAUDE.md`) — verification uses curl probes, psql inspection, and a manual end-to-end smoke against a real ticker.

**Spec:** `docs/superpowers/specs/2026-04-27-transcript-relationship-extraction-design.md`

---

## File Plan

### New files
- `backend/migrations/versions/<auto-rev>_transcript_relationships.py` — Alembic migration (nullable filing_id, 3 new columns on `relationships`, partial unique indexes, new `transcript_extractions` table)
- `backend/app/services/edgar_transcripts_relationships.py` — extractor service mirroring `edgar_relationships.py` shape

### Modified files (backend)
- `backend/app/models/filing.py` — add nullable + 3 new columns to `Relationship`, drop existing `UniqueConstraint`, add new `TranscriptExtraction` model
- `backend/app/services/edgar_relationships.py` — two surgical prompt edits in `_SYSTEM_PROMPT`
- `backend/app/api/filings.py` — add `POST /api/transcripts/extract-relationships/{ticker}` endpoint
- `backend/app/services/fanout.py` — add `extract_transcripts` stage between `extract` and `resolve`; thread FMP client into `FanoutService`
- `backend/app/main.py` — pass `fmp=app.state.fmp` into `FanoutService` constructor

### Modified files (frontend)
- `frontend/lib/api.ts` — add `extractTranscriptRelationships(ticker, force)` typed client + `TranscriptExtractionSummary` type, extend `FanoutStage` union with `"extract_transcripts"`

### Modified files (docs/state)
- `TODO.md` — move backlog item to "Done (recent)"

---

## Pre-flight

- [ ] **Step 0.1: Confirm dev environment is up**

Run from project root:
```bash
source backend/venv/bin/activate
pip install -r backend/requirements.txt
```

In a separate terminal:
```bash
uvicorn backend.app.main:app --reload
```

In a third terminal:
```bash
cd frontend && npm install && npm run dev
```

Expected: backend on `:8000`, frontend on `:3000`. Hit `http://localhost:8000/health` and confirm 200 OK before continuing.

- [ ] **Step 0.2: Probe FMP transcript coverage for the worked example (BWXT)**

The plan uses **BWXT** as the worked example (consistent with the Competition feature's verification ticker). The spec calls out an open question: does `fmp.get_earnings_transcript(ticker)` returning the `earning-call-transcript-latest` endpoint actually return 4+ entries, or only 1? Probe it:

```bash
source backend/venv/bin/activate
python -c "
import asyncio
from backend.app.clients.fmp import FMPClient

async def probe():
    fmp = FMPClient()
    try:
        data, _ = await fmp.get_earnings_transcript('BWXT')
        print(f'count: {len(data)}')
        for t in data[:6]:
            print({k: t.get(k) for k in ('symbol', 'year', 'quarter', 'date')})
    finally:
        await fmp.close()

asyncio.run(probe())
"
```

Expected: a count ≥ 4, each entry with `year` (int), `quarter` (int 1–4), and `date` (ISO string). The first entry should be the most recent.

**If count < 4:** fall back to enumerating recent (year, quarter) pairs explicitly. Insert this helper into `edgar_transcripts_relationships.py` Task 4 in place of the single `get_earnings_transcript(ticker)` call:

```python
async def _fetch_recent_transcripts(fmp, ticker: str, limit: int = 4) -> list[dict]:
    """FMP's `latest` endpoint sometimes returns only one transcript.
    Walk back from the current quarter calling `get_earnings_transcript`
    with explicit (year, quarter) until we have `limit` entries or we've
    tried 8 quarters.
    """
    from datetime import datetime
    out: list[dict] = []
    now = datetime.utcnow()
    y, q = now.year, ((now.month - 1) // 3) + 1
    tried = 0
    while len(out) < limit and tried < 8:
        data, _ = await fmp.get_earnings_transcript(ticker, year=y, quarter=q)
        if data:
            out.extend(data if isinstance(data, list) else [data])
        # walk back one quarter
        q -= 1
        if q == 0:
            q = 4
            y -= 1
        tried += 1
    return out[:limit]
```

Otherwise (count ≥ 4), keep the simpler `transcripts[:4]` slice. **Make a note** of which path applies before proceeding to Task 4.

- [ ] **Step 0.3: Confirm BWXT has filings already ingested (so the existing extract → resolve stages have something to compare against in the verification step)**

```bash
curl -s http://localhost:8000/api/filings/BWXT | python -m json.tool | head -40
```

If `item_1_business` is missing, ingest first:
```bash
curl -s -X POST http://localhost:8000/api/filings/ingest/BWXT | python -m json.tool
curl -s -X POST http://localhost:8000/api/filings/extract-relationships/BWXT | python -m json.tool
```

---

## Task 1: Alembic migration — schema changes

**Files:**
- Create: `backend/migrations/versions/<auto-rev>_transcript_relationships.py`

- [ ] **Step 1.1: Generate the migration**

```bash
cd backend && alembic revision -m "transcript relationships: nullable filing_id, source columns, partial indexes, transcript_extractions table"
```

This creates a file like `backend/migrations/versions/<rev>_transcript_relationships.py` with `revision` and `down_revision` auto-generated. Leave those alone.

- [ ] **Step 1.2: Replace the upgrade/downgrade body**

Replace the `def upgrade()` and `def downgrade()` bodies (keep imports/header) with:

```python
def upgrade() -> None:
    # 1. Make relationships.filing_id nullable.
    op.alter_column(
        "relationships",
        "filing_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )

    # 2. Add discriminator + transcript provenance columns.
    op.add_column(
        "relationships",
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
            server_default="filing",
        ),
    )
    op.add_column(
        "relationships",
        sa.Column("transcript_year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "relationships",
        sa.Column("transcript_quarter", sa.SmallInteger(), nullable=True),
    )

    # 3. Belt-and-suspenders backfill (DEFAULT covers new rows, this covers
    # any existing rows in case server_default isn't applied retroactively).
    op.execute("UPDATE relationships SET source_type = 'filing' WHERE source_type IS NULL")

    # 4. Source-consistency CHECK.
    op.create_check_constraint(
        "ck_relationships_source_consistency",
        "relationships",
        "(source_type = 'filing' AND filing_id IS NOT NULL) "
        "OR (source_type = 'transcript' "
        "AND filing_id IS NULL "
        "AND transcript_year IS NOT NULL "
        "AND transcript_quarter IS NOT NULL)",
    )

    # 5. Drop the existing unique constraint (NULL filing_id breaks it).
    op.drop_constraint(
        "uq_relationships_filing_section_counterparty_type",
        "relationships",
        type_="unique",
    )

    # 6. Two partial unique indexes — one per source_type flavor.
    op.create_index(
        "uq_relationships_filing",
        "relationships",
        ["filing_id", "section_key", "counterparty_name", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("filing_id IS NOT NULL"),
    )
    op.create_index(
        "uq_relationships_transcript",
        "relationships",
        ["ticker", "transcript_year", "transcript_quarter", "counterparty_name", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("filing_id IS NULL"),
    )

    # 7. transcript_extractions tombstone table.
    op.create_table(
        "transcript_extractions",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.SmallInteger(), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "relationships_added",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "ticker", "year", "quarter", name="pk_transcript_extractions"
        ),
    )


def downgrade() -> None:
    op.drop_table("transcript_extractions")
    op.drop_index("uq_relationships_transcript", table_name="relationships")
    op.drop_index("uq_relationships_filing", table_name="relationships")
    op.create_unique_constraint(
        "uq_relationships_filing_section_counterparty_type",
        "relationships",
        ["filing_id", "section_key", "counterparty_name", "relationship_type"],
    )
    op.drop_constraint("ck_relationships_source_consistency", "relationships", type_="check")
    op.drop_column("relationships", "transcript_quarter")
    op.drop_column("relationships", "transcript_year")
    op.drop_column("relationships", "source_type")
    # Caller must ensure no transcript-sourced rows exist before downgrading.
    op.alter_column(
        "relationships",
        "filing_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
```

Confirm the imports section already has `from alembic import op` and `import sqlalchemy as sa`. Add `from sqlalchemy.dialects import postgresql` if missing.

- [ ] **Step 1.3: Run the migration**

```bash
cd backend && alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, transcript relationships ...`

- [ ] **Step 1.4: Verify schema in psql**

```bash
psql "$DATABASE_URL_SYNC" -c "\d relationships" | head -30
psql "$DATABASE_URL_SYNC" -c "\d transcript_extractions"
```

Expected:
- `relationships.filing_id` shows `| | |` for the Nullable column (nullable).
- Three new columns: `source_type`, `transcript_year`, `transcript_quarter`.
- Indexes include `uq_relationships_filing` (partial WHERE filing_id IS NOT NULL) and `uq_relationships_transcript` (partial WHERE filing_id IS NULL).
- CHECK constraint `ck_relationships_source_consistency` is present.
- `transcript_extractions` table exists with PK `(ticker, year, quarter)`.

- [ ] **Step 1.5: Smoke the existing extractor still works (no regression)**

```bash
curl -s -X POST http://localhost:8000/api/filings/extract-relationships/BWXT | python -m json.tool | head -10
```

Expected: same shape as before — the migration shouldn't have broken anything.

- [ ] **Step 1.6: Commit**

```bash
git add backend/migrations/versions/
git commit -m "feat(db): add transcript relationship columns + transcript_extractions table"
```

---

## Task 2: ORM model updates

**Files:**
- Modify: `backend/app/models/filing.py`

- [ ] **Step 2.1: Add the new columns + drop the existing UniqueConstraint on `Relationship`**

In `backend/app/models/filing.py`, find the `Relationship` class. Make these surgical changes:

a) Find the line:
```python
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True
    )
```
Change `nullable=False` → `nullable=True` and update the doc comment one line above to mention transcript-sourced rows have NULL `filing_id`.

b) Right before the `relationship_type` Mapped column (which is currently around line 156), add:
```python
    # 'filing' (default) or 'transcript'. CHECK constraint enforces that
    # filing rows have filing_id NOT NULL and transcript rows have
    # transcript_year/quarter NOT NULL.
    source_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="filing", server_default="filing"
    )
    # Populated only when source_type='transcript'. Year/quarter of the
    # earnings call. (filing_id stays NULL for transcript rows.)
    transcript_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_quarter: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
```

c) Update `__table_args__` — drop the existing `UniqueConstraint`. The two partial unique indexes are migration-only (SQLAlchemy can't express partial unique indexes cleanly in `__table_args__`). The new `__table_args__` should be:

```python
    __table_args__ = (
        Index("ix_relationships_ticker_type", "ticker", "relationship_type"),
        Index("ix_relationships_counterparty_name", "counterparty_name"),
    )
```

d) Update imports at top of file — ensure `Integer` and `SmallInteger` are imported from `sqlalchemy`. The file already imports `String`, `Text`, `DateTime`, `ForeignKey`, etc. Add:
```python
from sqlalchemy import (
    # ... existing imports ...
    Integer,
    SmallInteger,
)
```

- [ ] **Step 2.2: Add the `TranscriptExtraction` model**

At the end of `backend/app/models/filing.py` (after `CompetitorLandscape`, the current last class), add:

```python
class TranscriptExtraction(Base):
    """Idempotency tombstone for transcript relationship extraction.

    One row per (ticker, year, quarter). A row's existence means the
    extractor has run for that transcript — including the zero-relationship
    case. `force=True` deletes the row before re-running.
    """

    __tablename__ = "transcript_extractions"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    quarter: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.utcnow(),
    )
    relationships_added: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2.3: Verify the model loads cleanly**

```bash
source backend/venv/bin/activate
python -c "from backend.app.models.filing import Relationship, TranscriptExtraction; print(Relationship.__table__.columns.keys()); print(TranscriptExtraction.__table__.columns.keys())"
```

Expected output includes `source_type`, `transcript_year`, `transcript_quarter` in the first list and `ticker`, `year`, `quarter`, `extracted_at`, `relationships_added`, `error` in the second.

- [ ] **Step 2.4: Restart the dev server and confirm boot**

The reload should already have caught the model change. Confirm no startup errors in the uvicorn log. Hit:
```bash
curl -s http://localhost:8000/health
```
Expected: 200 OK.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/models/filing.py
git commit -m "feat(models): nullable filing_id + transcript provenance + TranscriptExtraction model"
```

---

## Task 3: Prompt edits in edgar_relationships.py

**Files:**
- Modify: `backend/app/services/edgar_relationships.py`

- [ ] **Step 3.1: Edit `_SYSTEM_PROMPT` — two surgical changes**

Find `_SYSTEM_PROMPT = """You extract business-relationship disclosures from SEC filing sections.` (around line 105).

Change line 1 to:
```
You extract business-relationship disclosures from SEC filing sections or earnings call transcripts.
```

Find the bullet list under "Rules:". Add this rule immediately after the existing `- Skip generic mentions of "customers" or "suppliers"` bullet:
```
- Skip analysts and brokerage firm participants in earnings call Q&A — they ask questions but are not counterparties.
```

Leave everything else (schema, output format, deduplication rule) untouched.

- [ ] **Step 3.2: Verify the prompt compiles and the existing extractor still works**

```bash
python -c "from backend.app.services.edgar_relationships import _SYSTEM_PROMPT; print('OK' if 'earnings call' in _SYSTEM_PROMPT and 'analysts' in _SYSTEM_PROMPT else 'FAIL')"
```
Expected: `OK`.

```bash
curl -s -X POST 'http://localhost:8000/api/filings/extract-relationships/BWXT?force=true' | python -m json.tool | head -20
```
Expected: same summary shape as before, similar relationship count to a prior run (the prompt wording change is surgical — output should be substantially unchanged for filing sections).

- [ ] **Step 3.3: Commit**

```bash
git add backend/app/services/edgar_relationships.py
git commit -m "feat(prompts): broaden relationship extractor to cover transcripts"
```

---

## Task 4: New extractor service

**Files:**
- Create: `backend/app/services/edgar_transcripts_relationships.py`

- [ ] **Step 4.1: Create the file with the full extractor body**

```python
"""Extract business relationships from earnings call transcripts using Haiku.

Mirrors `edgar_relationships.py` shape but operates on FMP transcript data
instead of `FilingSection` rows. Reuses `_call_haiku_on_section` from the
filing extractor — the prompt is shared (with the transcript-aware rules
added in Task 3).

Idempotent on (ticker, year, quarter) via the `transcript_extractions`
table. Zero-relationship transcripts are still tombstoned. To force
re-extraction, pass `force=True` — the corresponding rows in `relationships`
(WHERE filing_id IS NULL AND transcript_year=... AND transcript_quarter=...)
are deleted along with the tombstone row.

Token cost: ≤4 Haiku calls per ticker per fan-out at ~3.5K input + ~500
output tokens each → roughly $0.02 per ticker.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.filing import Relationship, TranscriptExtraction
from backend.app.services.edgar_relationships import (
    SECTION_CHAR_BUDGET,
    _call_haiku_on_section,
    _normalize_relationship,
)

logger = logging.getLogger(__name__)

# Number of most-recent transcripts to extract per ticker.
TRANSCRIPT_QUARTER_LIMIT = 4


async def extract_ticker_transcript_relationships(
    ticker: str,
    fmp: FMPClient,
    db: AsyncSession,
    *,
    force: bool = False,
) -> dict:
    """Run Haiku relationship extraction on the last 4 quarters of earnings
    call transcripts for `ticker`. Persists rows in `relationships` with
    `source_type='transcript'`, `filing_id=NULL`, `transcript_year/quarter`
    populated. Tombstones in `transcript_extractions`.

    Caller is responsible for `await db.commit()` (matches the convention
    in `edgar_relationships.extract_ticker_relationships`).
    """
    ticker = ticker.upper()
    summary: dict[str, Any] = {
        "ticker": ticker,
        "transcripts_considered": 0,
        "transcripts_extracted": 0,
        "transcripts_skipped_existing": 0,
        "relationships_added": 0,
        "relationships_dropped": 0,
        "per_transcript": [],
        "errors": [],
    }

    try:
        raw, _ = await fmp.get_earnings_transcript(ticker)
    except Exception as exc:
        summary["errors"].append(f"FMP transcript fetch failed: {exc}")
        return summary

    transcripts = raw if isinstance(raw, list) else ([raw] if raw else [])
    if not transcripts:
        summary["errors"].append(f"no transcripts available for {ticker}")
        return summary

    # FMP returns most-recent first. Cap at TRANSCRIPT_QUARTER_LIMIT.
    transcripts = transcripts[:TRANSCRIPT_QUARTER_LIMIT]

    for t in transcripts:
        summary["transcripts_considered"] += 1
        year = t.get("year")
        quarter = t.get("quarter")
        date = t.get("date") or ""
        content = t.get("content") or t.get("transcript") or ""

        per: dict = {
            "year": year,
            "quarter": quarter,
            "date": date,
            "relationships_added": 0,
            "relationships_dropped": 0,
            "skipped": None,
            "error": None,
        }
        summary["per_transcript"].append(per)

        # Reject malformed FMP rows so we don't pollute the tombstone table.
        if not isinstance(year, int) or not isinstance(quarter, int) or quarter < 1 or quarter > 4:
            per["error"] = "missing or invalid year/quarter"
            summary["errors"].append(
                f"transcript missing year/quarter for {ticker}: year={year!r} quarter={quarter!r}"
            )
            continue
        if not content or not isinstance(content, str):
            per["error"] = "empty content"
            summary["errors"].append(
                f"transcript empty content for {ticker} {year}Q{quarter}"
            )
            continue

        # Idempotency check.
        existing = await db.execute(
            select(TranscriptExtraction).where(
                TranscriptExtraction.ticker == ticker,
                TranscriptExtraction.year == year,
                TranscriptExtraction.quarter == quarter,
            )
        )
        existing_row = existing.scalar_one_or_none()

        if existing_row is not None and not force:
            per["skipped"] = "existing_extraction"
            summary["transcripts_skipped_existing"] += 1
            continue

        if existing_row is not None and force:
            # Drop prior transcript-sourced rows for this quarter and the
            # tombstone — clean slate.
            await db.execute(
                Relationship.__table__.delete().where(
                    Relationship.ticker == ticker,
                    Relationship.filing_id.is_(None),
                    Relationship.transcript_year == year,
                    Relationship.transcript_quarter == quarter,
                )
            )
            await db.delete(existing_row)
            await db.flush()

        truncated = content[:SECTION_CHAR_BUDGET]
        section_key = f"transcript_{year}_q{quarter}"
        relationships, err = await _call_haiku_on_section(
            ticker=ticker,
            form_type=f"Earnings Call Q{quarter} {year}",
            filing_date=str(date),
            section_key=section_key,
            heading=f"{ticker} Q{quarter} {year} Earnings Call",
            text=truncated,
        )

        if err is not None:
            per["error"] = err
            summary["errors"].append(f"{section_key}: {err}")
            # Don't tombstone on transient errors — retry next run.
            continue

        # Dedupe by (counterparty_name, relationship_type) within a single
        # transcript (Haiku occasionally repeats).
        seen: set[tuple[str, str]] = set()
        added_for_transcript = 0
        for raw_rel in relationships:
            normalized = _normalize_relationship(raw_rel)
            if normalized is None:
                per["relationships_dropped"] += 1
                summary["relationships_dropped"] += 1
                continue
            key = (normalized.counterparty_name, normalized.relationship_type)
            if key in seen:
                per["relationships_dropped"] += 1
                summary["relationships_dropped"] += 1
                continue
            seen.add(key)
            db.add(Relationship(
                filing_id=None,
                ticker=ticker,
                section_key=section_key,
                source_type="transcript",
                transcript_year=year,
                transcript_quarter=quarter,
                counterparty_name=normalized.counterparty_name,
                relationship_type=normalized.relationship_type,
                magnitude_pct=normalized.magnitude_pct,
                unnamed=normalized.unnamed,
                verbatim_quote=normalized.verbatim_quote,
            ))
            added_for_transcript += 1

        per["relationships_added"] = added_for_transcript
        summary["relationships_added"] += added_for_transcript
        summary["transcripts_extracted"] += 1

        # Tombstone the (ticker, year, quarter) regardless of relationship
        # count — zero-relationship transcripts are still "done".
        db.add(TranscriptExtraction(
            ticker=ticker,
            year=year,
            quarter=quarter,
            extracted_at=datetime.utcnow(),
            relationships_added=added_for_transcript,
        ))

    await db.flush()
    logger.info(
        "transcript relationships: %s — %d transcripts extracted, %d relationships added",
        ticker, summary["transcripts_extracted"], summary["relationships_added"],
    )
    return summary
```

**If pre-flight Step 0.2 indicated the FMP `latest` endpoint returns < 4 transcripts**, replace the `raw, _ = await fmp.get_earnings_transcript(ticker)` block with a call to the `_fetch_recent_transcripts` helper from Step 0.2 and inline the helper at module scope.

- [ ] **Step 4.2: Verify imports resolve and the function is callable**

```bash
python -c "from backend.app.services.edgar_transcripts_relationships import extract_ticker_transcript_relationships; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4.3: Commit**

```bash
git add backend/app/services/edgar_transcripts_relationships.py
git commit -m "feat(transcripts): extract counterparty relationships from earnings calls"
```

---

## Task 5: API endpoint

**Files:**
- Modify: `backend/app/api/filings.py`

- [ ] **Step 5.1: Add the import**

Near the existing `from backend.app.services.edgar_relationships import (...)` block at the top of `backend/app/api/filings.py`, add:

```python
from backend.app.services.edgar_transcripts_relationships import (
    extract_ticker_transcript_relationships,
)
```

Also confirm `from fastapi import Request` is already imported (other endpoints in the file use it). If not, add `Request` to the existing FastAPI import line.

- [ ] **Step 5.2: Add the endpoint**

Add this route immediately after the existing `extract_relationships_batch` block (around line 230, before `extract-competition`):

```python
@router.post("/transcripts/extract-relationships/{ticker}")
async def extract_transcript_relationships_for_ticker(
    ticker: str,
    request: Request,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run Haiku relationship extraction over the last 4 quarters of
    earnings call transcripts for `ticker`. Persists rows in `relationships`
    with `source_type='transcript'`. Idempotent via `transcript_extractions`
    — pass `?force=true` to delete and re-run.
    """
    fmp = request.app.state.fmp
    summary = await extract_ticker_transcript_relationships(
        ticker, fmp=fmp, db=db, force=force
    )
    await db.commit()
    return summary
```

- [ ] **Step 5.3: Smoke the new endpoint**

```bash
curl -s -X POST http://localhost:8000/api/transcripts/extract-relationships/BWXT | python -m json.tool | head -40
```

Expected: a summary dict with `transcripts_considered`, `transcripts_extracted` ≥ 1, `relationships_added` (likely > 0 for BWXT), `per_transcript` array.

- [ ] **Step 5.4: Verify rows landed in DB**

```bash
psql "$DATABASE_URL_SYNC" -c "SELECT ticker, source_type, transcript_year, transcript_quarter, count(*) FROM relationships WHERE source_type='transcript' AND ticker='BWXT' GROUP BY 1,2,3,4 ORDER BY 3 DESC, 4 DESC;"
psql "$DATABASE_URL_SYNC" -c "SELECT * FROM transcript_extractions WHERE ticker='BWXT' ORDER BY year DESC, quarter DESC;"
```

Expected: ≤ 4 grouped rows in `relationships` (one per quarter that had relationships), 4 rows in `transcript_extractions` (including any zero-relationship quarters).

- [ ] **Step 5.5: Smoke idempotency**

```bash
curl -s -X POST http://localhost:8000/api/transcripts/extract-relationships/BWXT | python -m json.tool | head -10
```

Expected: `transcripts_skipped_existing: 4`, `relationships_added: 0`.

```bash
curl -s -X POST 'http://localhost:8000/api/transcripts/extract-relationships/BWXT?force=true' | python -m json.tool | head -10
```

Expected: `transcripts_extracted: 4`, `relationships_added` matches the original count (give or take Haiku non-determinism).

- [ ] **Step 5.6: Commit**

```bash
git add backend/app/api/filings.py
git commit -m "feat(api): POST /api/transcripts/extract-relationships/{ticker}"
```

---

## Task 6: FanoutService — add 4th stage

**Files:**
- Modify: `backend/app/services/fanout.py`
- Modify: `backend/app/main.py`

- [ ] **Step 6.1: Thread FMP into FanoutService**

In `backend/app/services/fanout.py`, find the imports and add:

```python
from backend.app.clients.fmp import FMPClient
from backend.app.services import edgar_transcripts_relationships
```

Find the existing `FanoutStageLiteral` definition and update:

```python
FanoutStageLiteral = Literal["ingest", "extract", "extract_transcripts", "resolve"]
```

Find `class FanoutService` and update the `__init__`. Today it's `def __init__(self, *, edgar: EdgarClient) -> None:`. Change to:

```python
def __init__(self, *, edgar: EdgarClient, fmp: FMPClient) -> None:
    self._edgar = edgar
    self._fmp = fmp
    self._statuses: dict[str, FanoutStatus] = {}
    self._lock = asyncio.Lock()
```

(Match the existing body — only the `fmp` line and parameter are new. If the existing `__init__` has additional state, preserve it.)

- [ ] **Step 6.2: Add the new stage to `_run_one_ticker`**

In `_run_one_ticker`, find the existing `# Stage 3: resolve` block. Insert this new stage **before** it (between the extract block and the resolve block):

```python
        # Stage 3: extract transcripts. New in 2026-04-27 — earnings call
        # transcripts go through the same Haiku extractor, write to the
        # same `relationships` table with source_type='transcript'.
        status.current_stage = "extract_transcripts"
        try:
            async with async_session() as db:
                await edgar_transcripts_relationships.extract_ticker_transcript_relationships(
                    ticker, fmp=self._fmp, db=db, force=force
                )
                await db.commit()
        except Exception as exc:
            logger.warning("Fanout extract_transcripts failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="extract_transcripts", message=str(exc))
            )
            # Continue to resolve — filing-sourced relationships from Stage 2
            # still benefit from resolution.
```

The existing resolve block is renumbered to "Stage 4" in its comment for clarity.

Also update the `except Exception` in `_run` near line 197 — it has `stage=status.current_stage or "ingest"`. The fallback string remains valid; no change needed.

- [ ] **Step 6.3: Pass `fmp` into FanoutService at construction**

In `backend/app/main.py`, find the line:
```python
    app.state.fanout = FanoutService(edgar=app.state.edgar)
```

Change to:
```python
    app.state.fanout = FanoutService(edgar=app.state.edgar, fmp=app.state.fmp)
```

(`app.state.fmp` is initialized earlier in lifespan — confirm by grepping `app.state.fmp = FMPClient()` is above the FanoutService line.)

- [ ] **Step 6.4: Smoke fan-out for a single ticker**

Hit the existing per-ticker fan-out endpoint (which now runs all 4 stages):

```bash
curl -s -X POST 'http://localhost:8000/api/tickers/BWXT/relationships/fanout?force=true' | python -m json.tool
```

Expected: 202 with a `fanout_id`. Then poll:

```bash
curl -s http://localhost:8000/api/fanouts/<fanout_id> | python -m json.tool
```

Expected: `current_stage` cycles through `ingest` → `extract` → `extract_transcripts` → `resolve` → `null`. Status ends `completed`. `errors[]` may have entries if individual transcript quarters had issues — they should all carry `stage="extract_transcripts"`.

- [ ] **Step 6.5: Verify the resolver picked up transcript-sourced rows**

```bash
psql "$DATABASE_URL_SYNC" -c "SELECT ticker, source_type, count(*) AS total, count(*) FILTER (WHERE resolved_to_cik IS NOT NULL) AS resolved FROM relationships WHERE ticker='BWXT' GROUP BY 1,2;"
```

Expected: separate rows for `filing` and `transcript`. Both should show some `resolved` count > 0 if BWXT's counterparties match known EDGAR entities.

- [ ] **Step 6.6: Commit**

```bash
git add backend/app/services/fanout.py backend/app/main.py
git commit -m "feat(fanout): add extract_transcripts stage between extract and resolve"
```

---

## Task 7: Frontend types

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 7.1: Update the `FanoutStage` union**

Open `frontend/lib/api.ts`. Find (around line 289):
```typescript
export type FanoutStage = "ingest" | "extract" | "resolve";
```
Change to:
```typescript
export type FanoutStage = "ingest" | "extract" | "extract_transcripts" | "resolve";
```

- [ ] **Step 7.2: Add the `TranscriptExtractionSummary` type**

Find the section just above the `relationships` namespace (around line 314, after the `FanoutStatus`/`FanoutError` types). Add this new type:

```typescript
export type TranscriptExtractionSummary = {
  ticker: string;
  transcripts_considered: number;
  transcripts_extracted: number;
  transcripts_skipped_existing: number;
  relationships_added: number;
  relationships_dropped: number;
  per_transcript: Array<{
    year: number | null;
    quarter: number | null;
    date: string;
    relationships_added: number;
    relationships_dropped: number;
    skipped: string | null;
    error: string | null;
  }>;
  errors: string[];
};
```

- [ ] **Step 7.3: Add a `transcripts` namespace with the extract method**

Add this new namespace right after the existing `competition` namespace (which sits between `relationships` and `fanouts`):

```typescript
export const transcripts = {
  extract: (ticker: string, force = false) =>
    apiFetch<TranscriptExtractionSummary>(
      `/api/transcripts/extract-relationships/${encodeURIComponent(ticker)}${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
};
```

The pattern matches `competition.extract` — same `apiFetch<T>` helper (defined elsewhere in this file), same query-string convention.

- [ ] **Step 7.4: Verify TS compiles**

```bash
cd frontend && npm run build 2>&1 | tail -30
```

Expected: build succeeds. If a downstream component does an exhaustive switch on `FanoutStage` (e.g., a `switch (status.current_stage)` rendering a label per stage), the new `"extract_transcripts"` variant will surface as a TS error. Add a `case "extract_transcripts":` arm with a sensible label (e.g. `"Extracting transcripts"`).

- [ ] **Step 7.3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(types): TranscriptExtractionSummary + FanoutStage extension"
```

---

## Task 8: End-to-end manual verification

This task runs the full verification matrix from the spec on a real ticker. No code changes — purely a checkpoint to confirm everything works together before merging.

- [ ] **Step 8.1: Pick a ticker whose recent earnings call should mention partners not in the latest 10-K**

BWXT is the worked example. Confirm the latest 10-K for BWXT was filed before the most recent earnings call (typical case — calls happen every quarter, 10-Ks annually):

```bash
psql "$DATABASE_URL_SYNC" -c "SELECT form_type, filing_date FROM filings WHERE ticker='BWXT' ORDER BY filing_date DESC LIMIT 5;"
psql "$DATABASE_URL_SYNC" -c "SELECT ticker, year, quarter, extracted_at FROM transcript_extractions WHERE ticker='BWXT' ORDER BY year DESC, quarter DESC;"
```

- [ ] **Step 8.2: Find a transcript-only counterparty**

```bash
psql "$DATABASE_URL_SYNC" -c "
SELECT counterparty_name, relationship_type, transcript_year, transcript_quarter
FROM relationships
WHERE ticker='BWXT' AND source_type='transcript'
  AND counterparty_name NOT IN (
    SELECT counterparty_name FROM relationships WHERE ticker='BWXT' AND source_type='filing'
  )
ORDER BY transcript_year DESC, transcript_quarter DESC;"
```

Expected: at least one row. This is the whole point of the feature — counterparties announced on a call but not yet in the latest 10-K.

- [ ] **Step 8.3: Verify the supply-chain graph picks them up**

```bash
curl -s 'http://localhost:8000/api/relationships/graph/BWXT' | python -m json.tool | grep -E '"name"|"relationship_type"' | head -30
```

Expected: counterparty names from both `filing` and `transcript` rows appear. (The endpoint doesn't currently surface `source_type` — that's the optional v1.5 polish.)

- [ ] **Step 8.4: Run a deep-dive and inspect the prompt context**

Bump the `node_deep_dive` log level to DEBUG temporarily, or add a `logger.info(prompt[:8000])` line just before the deep-dive `complete()` call (revert before commit). Then trigger:

```bash
curl -s -X POST http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"ticker": "BWXT", "theme_id": null}' | python -m json.tool
```

Watch the uvicorn log. In the `RESOLVED COUNTERPARTIES` block of the deep-dive prompt, confirm transcript-sourced names appear alongside filing-sourced ones.

Revert the temporary log line.

- [ ] **Step 8.5: Edge case — ticker with no transcripts**

Pick a ticker FMP doesn't cover (a recent IPO without 4 quarters of calls — try `RDDT` or a foreign ADR). Run:

```bash
curl -s -X POST http://localhost:8000/api/transcripts/extract-relationships/<ticker> | python -m json.tool
```

Expected: `errors[]` contains `"no transcripts available for <TICKER>"`. No DB writes. No 500 response.

- [ ] **Step 8.6: Edge case — fan-out with at least one transcript-failing ticker**

```bash
curl -s -X POST 'http://localhost:8000/api/themes/<theme_id>/relationships/fanout?force=true' | python -m json.tool
```

Then poll the status endpoint. Expected: `completed`, with `errors[]` carrying entries for `stage="extract_transcripts"` for tickers that had no coverage. Other tickers complete normally.

---

## Task 9: Update TODO.md

**Files:**
- Modify: `TODO.md`

- [ ] **Step 9.1: Move the backlog item to Done**

Open `TODO.md`. Find:
```markdown
- **Relationship extraction from earnings-call transcripts** (already ingested) — catches partnership announcements not yet in 10-Ks.
```

Delete that line from the "Backlog / polish" section. Also remove the duplicate appearance under "Backlog / v3" (same wording exists there).

In the "Done (recent)" section, just below the existing transcript-cleanup line you added at the start of this session, prepend:

```markdown
- **Transcript relationship extraction (Phase B-T)**. Last 4 quarters of earnings call transcripts run through the existing Haiku relationship extractor. Rows persist into `relationships` with `source_type='transcript'`, `filing_id=NULL`, `transcript_year/quarter` populated; idempotency tombstoned in new `transcript_extractions` table. New endpoint `POST /api/transcripts/extract-relationships/{ticker}`. `FanoutService` grew a 4th stage (`extract_transcripts`) between extract and resolve. Prompt edits in `edgar_relationships.py`: opening line broadened to "filings or earnings call transcripts" and one new rule to skip Q&A analysts. Resolver and supply-chain graph pick up transcript rows automatically via the denormalized `Relationship.ticker` column. Verified on BWXT: <count> transcripts extracted, <count> relationships added, at least one transcript-only counterparty surfaced. Migration replaces `uq_relationships_filing_section_counterparty_type` with two partial unique indexes (`uq_relationships_filing` WHERE filing_id IS NOT NULL; `uq_relationships_transcript` WHERE filing_id IS NULL).
```

Replace `<count>` placeholders with the actual numbers from Task 8 verification.

- [ ] **Step 9.2: Commit**

```bash
git add TODO.md
git commit -m "docs(todo): record transcript relationship extraction completion"
```

---

## Done

After Task 9, the feature is shipped. Optional follow-ups (not part of this plan):

- v1.5 polish: badge transcript-sourced rows in `SupplyChainEcosystem` UI with the year/quarter as a tooltip annotation. Requires plumbing `source_type` + `transcript_year/quarter` through the supply-chain graph response and into the React component's `EdgeRow`.
- Future option C migration: add a `transcripts` table that mirrors `filings` and persist raw content. Backfill `relationships.transcript_id` from `(ticker, transcript_year, transcript_quarter)`. Drop the two scalar columns. No breaking change to consumers.
