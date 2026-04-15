"""Ingest SEC EDGAR XBRL company facts into filings + xbrl_facts tables.

Called from the deep_dive phase in the pipeline. Fetches one companyfacts
payload per ticker, filters to CONCEPT_WHITELIST, and upserts rows.

Idempotent: re-running for the same ticker skips facts whose accession_number
already has rows (keyed off filings.accession_number).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient, EdgarClientError, iter_whitelisted_facts
from backend.app.models.citation import Citation
from backend.app.models.filing import Filing, XBRLFact

logger = logging.getLogger(__name__)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


async def ingest_ticker_facts(
    ticker: str, db: AsyncSession, edgar: EdgarClient
) -> tuple[dict, list[Citation]]:
    """Fetch and persist XBRL facts for a ticker.

    Returns (summary, citations).
    - summary: {cik, filings_added, facts_added, skipped_existing}.
    - citations: list of Citation objects identifying the SEC endpoints used.
      The caller persists them onto ResearchState so the Library citations
      panel lists SEC sources alongside FMP/FRED/X.
    Raises on network / API errors so the caller can log and continue.
    """
    # Citations are emitted only when the ingest yields analytically useful
    # data — the ticker→CIK lookup is plumbing, not a research source.
    citations: list[Citation] = []

    cik, _ = await edgar.get_ticker_to_cik(ticker)
    if not cik:
        logger.info("EDGAR: no CIK for %s, skipping", ticker)
        return (
            {"cik": None, "filings_added": 0, "facts_added": 0, "skipped_existing": 0},
            citations,
        )

    try:
        companyfacts, facts_cit = await edgar.get_company_facts(cik)
    except EdgarClientError as e:
        logger.warning("EDGAR: companyfacts fetch failed for %s (%s): %s", ticker, cik, e)
        return (
            {"cik": cik, "filings_added": 0, "facts_added": 0, "skipped_existing": 0},
            citations,
        )

    raw_facts = iter_whitelisted_facts(companyfacts)
    if not raw_facts:
        logger.info("EDGAR: no whitelisted facts for %s", ticker)
        return (
            {"cik": cik, "filings_added": 0, "facts_added": 0, "skipped_existing": 0},
            citations,
        )

    # Success path: persist the companyfacts citation so the Library UI
    # surfaces SEC as a Tier-1 source.
    citations.append(facts_cit)

    # ── 1. Upsert filings ────────────────────────────────────────────────
    accessions = {f["accession_number"] for f in raw_facts if f.get("accession_number")}
    existing = await db.execute(
        select(Filing).where(Filing.accession_number.in_(accessions))
    )
    existing_by_accn: dict[str, Filing] = {f.accession_number: f for f in existing.scalars().all()}

    filings_added = 0
    new_filings: dict[str, Filing] = {}
    for f in raw_facts:
        accn = f.get("accession_number")
        if not accn or accn in existing_by_accn or accn in new_filings:
            continue
        filing = Filing(
            accession_number=accn,
            cik=cik,
            ticker=ticker.upper(),
            form_type=(f.get("form") or "")[:16],
            filing_date=_parse_date(f.get("filed")) or _parse_date(f.get("period_end")) or date.today(),
            period_of_report=_parse_date(f.get("period_end")),
            primary_document_url=None,
        )
        db.add(filing)
        new_filings[accn] = filing
        filings_added += 1

    if new_filings:
        await db.flush()  # populate filing.id

    filing_by_accn = {**{a: f for a, f in existing_by_accn.items()}, **new_filings}

    # ── 2. Skip facts whose filing rows already had facts ingested ───────
    # Simplification: treat "filing existed before this call" as "already ingested"
    # for that filing. v1 compromise — avoids a per-fact existence check.
    facts_added = 0
    skipped_existing = 0
    for f in raw_facts:
        accn = f.get("accession_number")
        filing = filing_by_accn.get(accn) if accn else None
        if not filing:
            continue
        if accn in existing_by_accn:
            skipped_existing += 1
            continue
        period_end = _parse_date(f.get("period_end"))
        period_start = _parse_date(f.get("period_start")) or period_end
        value = f.get("value")
        if period_end is None or period_start is None or value is None:
            continue
        db.add(XBRLFact(
            filing_id=filing.id,
            ticker=ticker.upper(),
            concept=f["concept"],
            unit=(f.get("unit") or "")[:32],
            period_start=period_start,
            period_end=period_end,
            fiscal_year=f.get("fiscal_year"),
            fiscal_period=(f.get("fiscal_period") or None),
            value=float(value),
        ))
        facts_added += 1

    # Flush populates filing IDs in-session. The caller commits (or rolls back)
    # the session it owns — this helper must not manage transaction boundaries.
    # Flush populates filing IDs in-session. The caller commits (or rolls back)
    # the session it owns — this helper must not manage transaction boundaries.
    await db.flush()
    logger.info(
        "EDGAR: %s (cik=%s) — %d filings added, %d facts added, %d skipped",
        ticker, cik, filings_added, facts_added, skipped_existing,
    )
    return (
        {
            "cik": cik,
            "filings_added": filings_added,
            "facts_added": facts_added,
            "skipped_existing": skipped_existing,
        },
        citations,
    )


async def get_recent_facts_by_concept(
    ticker: str, concepts: Iterable[str], db: AsyncSession, limit_per_concept: int = 6
) -> dict[str, list[dict]]:
    """Return {concept: [fact_dict, ...]} — most recent first, limited per concept."""
    concepts = list(concepts)
    if not concepts:
        return {}
    result = await db.execute(
        select(XBRLFact)
        .where(XBRLFact.ticker == ticker.upper(), XBRLFact.concept.in_(concepts))
        .order_by(XBRLFact.period_end.desc())
    )
    rows = result.scalars().all()
    out: dict[str, list[dict]] = {}
    for row in rows:
        bucket = out.setdefault(row.concept, [])
        if len(bucket) >= limit_per_concept:
            continue
        bucket.append({
            "value": float(row.value),
            "unit": row.unit,
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "fiscal_year": row.fiscal_year,
            "fiscal_period": row.fiscal_period,
        })
    return out
