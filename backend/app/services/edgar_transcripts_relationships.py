"""Extract business relationships from earnings call transcripts using Haiku.

Mirrors `edgar_relationships.py` shape but operates on FMP transcript data
instead of `FilingSection` rows. Reuses `_call_haiku_on_section` from the
filing extractor — the prompt is shared (with the transcript-aware rules
added in the prompt edit task).

Idempotent on (ticker, year, quarter) via the `transcript_extractions`
table. Zero-relationship transcripts are still tombstoned. To force
re-extraction, pass `force=True` — the corresponding rows in `relationships`
(WHERE filing_id IS NULL AND transcript_year=... AND transcript_quarter=...)
are deleted along with the tombstone row.

Token cost: ≤4 Haiku calls per ticker per fan-out at ~3.5K input + ~500
output tokens each → roughly $0.02 per ticker.

NOTE on FMP coverage: the `earning-call-transcript-latest` endpoint
ignores the symbol parameter, so we walk back from the current quarter
calling the explicit `(year, quarter)` endpoint until we have `limit`
entries or we've tried 8 quarters. The API response also returns
`quarter: None` even when explicitly requested, so we stamp the requested
(year, quarter) onto each entry rather than trusting the response.
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
# Cap on quarters to walk back when populating the limit. Keeps us from
# looping forever on tickers with no transcripts (e.g., recent IPOs).
TRANSCRIPT_LOOKBACK_CAP = 8


async def _fetch_recent_transcripts(
    fmp: FMPClient, ticker: str, limit: int = TRANSCRIPT_QUARTER_LIMIT
) -> list[dict]:
    """Walk back from the current quarter calling FMP's explicit
    `(year, quarter)` endpoint until we have `limit` transcripts or we've
    tried `TRANSCRIPT_LOOKBACK_CAP` quarters.

    The "latest" endpoint ignores the symbol parameter, so we cannot rely
    on it. The explicit endpoint also returns `quarter: None` even when
    requested, so each result is stamped with the requested (year, quarter).
    """
    out: list[dict] = []
    now = datetime.utcnow()
    y, q = now.year, ((now.month - 1) // 3) + 1
    tried = 0
    while len(out) < limit and tried < TRANSCRIPT_LOOKBACK_CAP:
        try:
            data, _ = await fmp.get_earnings_transcript(ticker, year=y, quarter=q)
        except Exception as exc:
            logger.warning(
                "FMP transcript fetch failed for %s %dQ%d: %r", ticker, y, q, exc
            )
            data = []
        if data:
            entries = data if isinstance(data, list) else [data]
            for e in entries:
                # The API echoes year but not quarter — stamp our requested
                # values to make downstream persistence reliable.
                e["year"] = y
                e["quarter"] = q
                out.append(e)
        # Walk back one quarter.
        q -= 1
        if q == 0:
            q = 4
            y -= 1
        tried += 1
    return out[:limit]


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

    transcripts = await _fetch_recent_transcripts(fmp, ticker, limit=TRANSCRIPT_QUARTER_LIMIT)
    if not transcripts:
        summary["errors"].append(f"no transcripts available for {ticker}")
        return summary

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

        # Reject malformed entries so we don't pollute the tombstone table.
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
