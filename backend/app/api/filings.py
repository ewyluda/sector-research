"""Filing sections API — ingest and read narrative sections from SEC EDGAR.

Manual on-demand ingest only. No scheduler / auto-fanout. Called from the
frontend filings page or ad-hoc scripts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.db import get_db
from backend.app.models.filing import Filing, FilingSection, Relationship
from backend.app.services.edgar_relationships import (
    extract_batch_relationships,
    extract_ticker_relationships,
)
from backend.app.services.edgar_sections_ingest import (
    ingest_batch_sections,
    ingest_ticker_sections,
)

router = APIRouter(tags=["filings"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class IngestBatchRequest(BaseModel):
    tickers: list[str]


class FilingSectionSummary(BaseModel):
    section_key: str
    heading: str | None
    char_count: int
    extraction_method: str


class FilingRecord(BaseModel):
    id: str
    accession_number: str
    ticker: str
    form_type: str
    filing_date: str
    period_of_report: str | None
    primary_document_url: str | None
    sections: list[FilingSectionSummary]


class FilingSectionText(BaseModel):
    section_key: str
    heading: str | None
    text: str
    char_count: int
    extraction_method: str
    extracted_at: str


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/filings/ingest/{ticker}")
async def ingest_ticker(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Manually trigger section ingest for a single ticker.

    Fetches the latest 10-K, 10-Q, and DEF 14A, extracts narrative sections,
    and persists them. Idempotent — existing (filing_id, section_key) rows
    are skipped.
    """
    edgar = EdgarClient()
    try:
        summary = await ingest_ticker_sections(ticker, db=db, edgar=edgar)
    finally:
        await edgar.close()
    await db.commit()
    return summary


@router.post("/filings/ingest/batch")
async def ingest_batch(
    body: IngestBatchRequest, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Manually trigger section ingest for a list of tickers.

    Runs sequentially to stay under SEC's 10 req/s rate limit. One failed
    ticker does not abort the batch.
    """
    if not body.tickers:
        raise HTTPException(status_code=400, detail="tickers list is empty")
    edgar = EdgarClient()
    try:
        results = await ingest_batch_sections(body.tickers, db=db, edgar=edgar)
    finally:
        await edgar.close()
    await db.commit()
    return results


@router.get("/filings/{ticker}")
async def list_filings_for_ticker(
    ticker: str, db: AsyncSession = Depends(get_db)
) -> list[FilingRecord]:
    """List filings with ingested sections for a ticker."""
    ticker = ticker.upper()
    rows = await db.execute(
        select(Filing)
        .where(Filing.ticker == ticker)
        .order_by(Filing.filing_date.desc())
    )
    filings = rows.scalars().all()
    if not filings:
        return []

    filing_ids = [f.id for f in filings]
    sect_rows = await db.execute(
        select(FilingSection).where(FilingSection.filing_id.in_(filing_ids))
    )
    sections_by_filing: dict[str, list[FilingSection]] = {}
    for s in sect_rows.scalars().all():
        sections_by_filing.setdefault(s.filing_id, []).append(s)

    out: list[FilingRecord] = []
    for f in filings:
        out.append(FilingRecord(
            id=f.id,
            accession_number=f.accession_number,
            ticker=f.ticker,
            form_type=f.form_type,
            filing_date=f.filing_date.isoformat(),
            period_of_report=f.period_of_report.isoformat() if f.period_of_report else None,
            primary_document_url=f.primary_document_url,
            sections=[
                FilingSectionSummary(
                    section_key=s.section_key,
                    heading=s.heading,
                    char_count=s.char_count,
                    extraction_method=s.extraction_method,
                )
                for s in sections_by_filing.get(f.id, [])
            ],
        ))
    return out


@router.post("/filings/extract-relationships/{ticker}")
async def extract_relationships_for_ticker(
    ticker: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run Haiku relationship extraction on every ingested section for the ticker.

    Idempotent: (filing_id, section_key) pairs with existing extractions are
    skipped. Pass `?force=true` to delete and re-run.
    """
    summary = await extract_ticker_relationships(ticker, db=db, force=force)
    await db.commit()
    return summary


@router.post("/filings/extract-relationships/batch")
async def extract_relationships_batch(
    body: IngestBatchRequest,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if not body.tickers:
        raise HTTPException(status_code=400, detail="tickers list is empty")
    results = await extract_batch_relationships(body.tickers, db=db, force=force)
    await db.commit()
    return results


class RelationshipRecord(BaseModel):
    id: str
    accession_number: str
    form_type: str
    filing_date: str
    section_key: str
    counterparty_name: str
    relationship_type: str
    magnitude_pct: float | None
    unnamed: bool
    verbatim_quote: str | None
    confirmed_bilateral: bool
    extracted_at: str


@router.get("/filings/{ticker}/relationships")
async def list_relationships_for_ticker(
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> list[RelationshipRecord]:
    """Return all extracted relationships for a ticker, joined with filing metadata."""
    rows = await db.execute(
        select(Relationship, Filing)
        .join(Filing, Filing.id == Relationship.filing_id)
        .where(Filing.ticker == ticker.upper())
        .order_by(Filing.filing_date.desc(), Relationship.counterparty_name)
    )
    out: list[RelationshipRecord] = []
    for rel, filing in rows.all():
        out.append(RelationshipRecord(
            id=rel.id,
            accession_number=filing.accession_number,
            form_type=filing.form_type,
            filing_date=filing.filing_date.isoformat(),
            section_key=rel.section_key,
            counterparty_name=rel.counterparty_name,
            relationship_type=rel.relationship_type,
            magnitude_pct=float(rel.magnitude_pct) if rel.magnitude_pct is not None else None,
            unnamed=rel.unnamed,
            verbatim_quote=rel.verbatim_quote,
            confirmed_bilateral=rel.confirmed_bilateral,
            extracted_at=rel.extracted_at.isoformat(),
        ))
    return out


@router.get("/filings/{ticker}/{accession_number}/sections/{section_key}")
async def get_filing_section(
    ticker: str,
    accession_number: str,
    section_key: str,
    db: AsyncSession = Depends(get_db),
) -> FilingSectionText:
    """Fetch the full text of a single section."""
    row = await db.execute(
        select(FilingSection, Filing)
        .join(Filing, Filing.id == FilingSection.filing_id)
        .where(
            Filing.ticker == ticker.upper(),
            Filing.accession_number == accession_number,
            FilingSection.section_key == section_key,
        )
    )
    hit = row.first()
    if not hit:
        raise HTTPException(status_code=404, detail="section not found")
    section, _ = hit
    return FilingSectionText(
        section_key=section.section_key,
        heading=section.heading,
        text=section.text,
        char_count=section.char_count,
        extraction_method=section.extraction_method,
        extracted_at=section.extracted_at.isoformat(),
    )
