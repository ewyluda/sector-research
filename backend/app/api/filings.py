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
from backend.app.models.filing import (
    CompetitorLandscape,
    CounterpartyAlias,
    Filing,
    FilingSection,
    FilingSegment,
    Relationship,
)
from backend.app.services.counterparty_resolver import (
    list_unresolved_counterparties,
    resolve_batch,
    resolve_competition_for_ticker,
    resolve_ticker_relationships,
    upsert_manual_alias,
)
from backend.app.services.edgar_competition import extract_ticker_competition
from backend.app.services.edgar_relationships import (
    extract_batch_relationships,
    extract_ticker_relationships,
)
from backend.app.services.edgar_sections_ingest import (
    ingest_batch_sections,
    ingest_ticker_sections,
)
from backend.app.services.supply_chain import (
    get_graph,
    reconcile_bilaterals,
    summarize_for_card,
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


# Competition response schemas
class CompetitorChipResponse(BaseModel):
    name: str
    ticker: str | None
    magnitude_pct: float | None
    verbatim_quote: str | None
    tracked: bool


class CompetitionAreaResponse(BaseModel):
    area_of_competition: str
    competitors: list[CompetitorChipResponse]


class CompetitionSegmentResponse(BaseModel):
    segment_name: str
    narrative: str
    areas: list[CompetitionAreaResponse]


class CompetitionFilingResponse(BaseModel):
    accession_number: str
    form_type: str
    filing_date: str
    sec_filing_url: str | None


class CompetitionResponse(BaseModel):
    ticker: str
    filing: CompetitionFilingResponse | None
    extracted_at: str | None
    segments: list[CompetitionSegmentResponse]


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


@router.post("/filings/extract-competition/{ticker}")
async def extract_competition_for_ticker(
    ticker: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run Haiku competition extraction on the latest 10-K for the ticker.

    Idempotent on filing_sections.competition_extracted_at. Pass `?force=true`
    to wipe prior segments/landscape rows and re-extract. After extraction
    runs, the counterparty resolver back-fills resolved_to_ticker / _cik
    into the competitors[] JSONB array.
    """
    summary = await extract_ticker_competition(ticker, db=db, force=force)
    await db.commit()

    # Resolver runs against the freshly-persisted JSONB rows. A second commit
    # picks up the JSONB mutations from flag_modified.
    if summary.filing_id and not summary.skipped:
        resolver_summary = await resolve_competition_for_ticker(ticker, db=db)
        await db.commit()
    else:
        resolver_summary = None

    return {**summary.as_dict(), "resolver": resolver_summary}


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
    resolved_to_cik: str | None
    resolved_to_ticker: str | None
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
            resolved_to_cik=rel.resolved_to_cik,
            resolved_to_ticker=rel.resolved_to_ticker,
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


# ── Counterparty resolution (Phase C) ────────────────────────────────────────


class ResolutionCandidateResponse(BaseModel):
    cik: str
    ticker: str | None
    canonical_name: str
    score: float
    source: str


class UnresolvedCounterpartyResponse(BaseModel):
    counterparty_name: str
    alias_normalized: str
    occurrence_count: int
    tickers: list[str]
    candidates: list[ResolutionCandidateResponse]


class ManualAliasRequest(BaseModel):
    alias_name: str
    canonical_cik: str
    canonical_ticker: str | None = None
    canonical_name: str
    created_by: str | None = None


@router.post("/relationships/resolve/{ticker}")
async def resolve_ticker(
    ticker: str, db: AsyncSession = Depends(get_db),
) -> dict:
    """Resolve unresolved counterparties for a ticker via alias reuse,
    exact match, and ≥95 fuzzy match against EDGAR's company universe."""
    summary = await resolve_ticker_relationships(ticker, db=db)
    await db.commit()
    return summary


@router.post("/relationships/resolve/batch")
async def resolve_tickers(
    body: IngestBatchRequest, db: AsyncSession = Depends(get_db),
) -> list[dict]:
    if not body.tickers:
        raise HTTPException(status_code=400, detail="tickers list is empty")
    results = await resolve_batch(body.tickers, db=db)
    await db.commit()
    return results


@router.get("/relationships/unresolved")
async def list_unresolved(
    limit: int = 50, db: AsyncSession = Depends(get_db),
) -> list[UnresolvedCounterpartyResponse]:
    """Counterparty curation queue. Sorted by occurrence count desc."""
    rows = await list_unresolved_counterparties(db, limit=limit)
    return [
        UnresolvedCounterpartyResponse(
            counterparty_name=r.counterparty_name,
            alias_normalized=r.alias_normalized,
            occurrence_count=r.occurrence_count,
            tickers=r.tickers,
            candidates=[
                ResolutionCandidateResponse(
                    cik=c.cik, ticker=c.ticker, canonical_name=c.canonical_name,
                    score=c.score, source=c.source,
                )
                for c in r.candidates
            ],
        )
        for r in rows
    ]


@router.post("/relationships/alias")
async def create_manual_alias(
    body: ManualAliasRequest, db: AsyncSession = Depends(get_db),
) -> dict:
    """User-driven resolution. Writes a curator_manual alias and
    backfills resolved_to_cik/ticker on every matching Relationship row."""
    try:
        result = await upsert_manual_alias(
            db,
            alias_name=body.alias_name,
            canonical_cik=body.canonical_cik,
            canonical_ticker=body.canonical_ticker,
            canonical_name=body.canonical_name,
            created_by=body.created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


# ── Supply-chain graph (Phase D) ──────────────────────────────────────────────


class GraphNodeResponse(BaseModel):
    id: str
    ticker: str | None
    cik: str | None
    name: str
    is_root: bool
    tracked: bool
    unnamed: bool


class GraphEdgeResponse(BaseModel):
    from_id: str
    to_id: str
    relationship_type: str
    direction: str
    magnitude_pct: float | None
    unnamed: bool
    confirmed_bilateral: bool
    verbatim_quote: str | None
    source_ticker: str
    accession_number: str
    filing_date: str
    section_key: str


class SupplyChainGraphResponse(BaseModel):
    root_ticker: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    # Pre-bucketed view that the dashboard card can render directly.
    summary: dict


@router.get("/relationships/graph/{ticker}")
async def get_ticker_graph(
    ticker: str,
    direction: str = "both",
    db: AsyncSession = Depends(get_db),
) -> SupplyChainGraphResponse:
    """Return a 1-hop supply-chain graph centered on the ticker.

    `direction` = out | in | both.
      - out: the ticker's filings name these counterparties
      - in:  other tickers name this ticker as a counterparty
      - both: union
    """
    if direction not in ("out", "in", "both"):
        raise HTTPException(
            status_code=400, detail="direction must be one of: out, in, both",
        )
    graph = await get_graph(ticker, direction=direction, db=db)  # type: ignore[arg-type]
    summary = summarize_for_card(graph)
    return SupplyChainGraphResponse(
        root_ticker=graph.root_ticker,
        nodes=[
            GraphNodeResponse(
                id=n.id, ticker=n.ticker, cik=n.cik, name=n.name,
                is_root=n.is_root, tracked=n.tracked, unnamed=n.unnamed,
            ) for n in graph.nodes
        ],
        edges=[
            GraphEdgeResponse(
                from_id=e.from_id, to_id=e.to_id,
                relationship_type=e.relationship_type, direction=e.direction,
                magnitude_pct=e.magnitude_pct, unnamed=e.unnamed,
                confirmed_bilateral=e.confirmed_bilateral,
                verbatim_quote=e.verbatim_quote, source_ticker=e.source_ticker,
                accession_number=e.accession_number,
                filing_date=e.filing_date, section_key=e.section_key,
            ) for e in graph.edges
        ],
        summary=summary,
    )


@router.post("/relationships/reconcile")
async def reconcile_all_bilaterals(db: AsyncSession = Depends(get_db)) -> dict:
    """Scan every resolved relationship for a reciprocal pair and flip
    `confirmed_bilateral=true` on both sides. Idempotent — already-flipped
    rows are no-ops."""
    summary = await reconcile_bilaterals(db)
    await db.commit()
    return summary


@router.get("/competition/{ticker}")
async def get_competition(
    ticker: str,
    db: AsyncSession = Depends(get_db),
) -> CompetitionResponse:
    """Return the structured Competition view for a ticker.

    Reads from the latest 10-K's filing_segments + competitor_landscape rows.
    Returns `extracted_at: null` when extraction has never run.
    """
    ticker_upper = ticker.upper()

    filing = (
        await db.execute(
            select(Filing)
            .where(Filing.ticker == ticker_upper, Filing.form_type == "10-K")
            .order_by(Filing.filing_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if filing is None:
        return CompetitionResponse(
            ticker=ticker_upper, filing=None, extracted_at=None, segments=[],
        )

    section = (
        await db.execute(
            select(FilingSection).where(
                FilingSection.filing_id == filing.id,
                FilingSection.section_key == "item_1_business",
            )
        )
    ).scalar_one_or_none()
    extracted_at = (
        section.competition_extracted_at.isoformat()
        if section and section.competition_extracted_at
        else None
    )

    sec_url = (
        f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={filing.cik}"
        f"&type={filing.form_type}&dateb=&owner=include&count=40"
        if filing.cik else None
    )

    filing_response = CompetitionFilingResponse(
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        filing_date=filing.filing_date.isoformat(),
        sec_filing_url=sec_url,
    )

    if extracted_at is None:
        return CompetitionResponse(
            ticker=ticker_upper, filing=filing_response,
            extracted_at=None, segments=[],
        )

    # Pull segments + landscape for this filing
    seg_rows = (
        await db.execute(
            select(FilingSegment).where(FilingSegment.filing_id == filing.id)
        )
    ).scalars().all()
    landscape_rows = (
        await db.execute(
            select(CompetitorLandscape).where(
                CompetitorLandscape.filing_id == filing.id
            )
        )
    ).scalars().all()

    # Build tracked-ticker set from theme.seed_tickers across all themes
    from backend.app.models.theme import Theme
    theme_rows = (await db.execute(select(Theme))).scalars().all()
    tracked: set[str] = set()
    for t in theme_rows:
        for tk in (t.seed_tickers or []):
            tracked.add(tk.upper())

    # Group landscape rows by segment_name → list of areas
    by_segment: dict[str, list[CompetitorLandscape]] = {}
    for row in landscape_rows:
        by_segment.setdefault(row.segment_name, []).append(row)

    segments_out: list[CompetitionSegmentResponse] = []
    for seg in seg_rows:
        areas_out: list[CompetitionAreaResponse] = []
        for area_row in by_segment.get(seg.segment_name, []):
            chips: list[CompetitorChipResponse] = []
            for comp in (area_row.competitors or []):
                resolved_ticker = comp.get("resolved_to_ticker")
                chips.append(CompetitorChipResponse(
                    name=comp.get("name", ""),
                    ticker=resolved_ticker,
                    magnitude_pct=comp.get("magnitude_pct"),
                    verbatim_quote=comp.get("verbatim_quote"),
                    tracked=bool(
                        resolved_ticker and resolved_ticker.upper() in tracked
                    ),
                ))
            areas_out.append(CompetitionAreaResponse(
                area_of_competition=area_row.area_of_competition,
                competitors=chips,
            ))
        segments_out.append(CompetitionSegmentResponse(
            segment_name=seg.segment_name,
            narrative=seg.narrative,
            areas=areas_out,
        ))

    return CompetitionResponse(
        ticker=ticker_upper,
        filing=filing_response,
        extracted_at=extracted_at,
        segments=segments_out,
    )
