"""Ingest an S-1 / S-1/A prospectus from EDGAR.

Mirrors edgar_sections_ingest.py but for prospectus filings:
  * Accepts either a primary-document URL or a bare accession number.
  * Resolves issuer (CIK, name) and primary document via EdgarClient.
  * Persists the filing under a synthetic ticker so the existing
    filings/filing_sections/relationships pipeline works unchanged.
  * Does NOT do embedded-financials extraction (that lives in
    prospectus_financials.py — separate Sonnet call).

The caller (ProspectusService) owns the session and the commit.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient, EdgarClientError
from backend.app.models.filing import Filing, FilingSection
from backend.app.models.prospectus_schemas import (
    ExtractedSectionSummary,
    IngestStepOutput,
    ProspectusFinancials,
)
from backend.app.services.edgar_html import extract_sections

logger = logging.getLogger(__name__)

PROSPECTUS_FORM_TYPES: tuple[str, ...] = ("S-1", "S-1/A")


@dataclass
class SourceInput:
    accession_number: str
    cik_trimmed: str | None
    primary_document: str | None


_URL_PATTERN = re.compile(
    r"sec\.gov/Archives/edgar/data/(?P<cik>\d+)/(?P<accn_nodash>\d{18})/(?P<doc>[^/?\s]+)",
    re.IGNORECASE,
)
_ACCN_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def parse_source_input(text: str) -> SourceInput:
    text = text.strip()
    m = _URL_PATTERN.search(text)
    if m:
        accn_nodash = m.group("accn_nodash")
        return SourceInput(
            accession_number=f"{accn_nodash[:10]}-{accn_nodash[10:12]}-{accn_nodash[12:]}",
            cik_trimmed=m.group("cik"),
            primary_document=m.group("doc"),
        )
    if _ACCN_PATTERN.match(text):
        return SourceInput(accession_number=text, cik_trimmed=None, primary_document=None)
    raise ValueError(f"Could not parse {text!r} as an EDGAR URL or accession number")


async def _resolve_issuer_from_submissions(
    edgar: EdgarClient, cik_trimmed: str
) -> tuple[str, str]:
    """Return (cik_padded, issuer_name) for a trimmed CIK."""
    cik_padded = cik_trimmed.zfill(10)
    submissions, _ = await edgar.get_submissions(cik_padded)
    name = submissions.get("name") or submissions.get("entityName") or ""
    return cik_padded, name


async def _find_filing_in_submissions(submissions: dict, accession_number: str) -> dict | None:
    """Walk the submissions feed (recent + paginated older files) and return
    the entry for this accession. Returns None if not found."""
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    accessions = recent.get("accessionNumber", []) or []
    for i, acc in enumerate(accessions):
        if acc == accession_number:
            return {
                "form": recent.get("form", [])[i],
                "primary_document": recent.get("primaryDocument", [])[i],
                "filing_date": recent.get("filingDate", [])[i],
                "period_of_report": recent.get("reportDate", [])[i] or None,
            }
    return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


async def ingest_prospectus(
    *,
    source: SourceInput,
    synthetic_ticker: str,
    issuer_cik: str | None,
    db: AsyncSession,
    edgar: EdgarClient,
) -> tuple[Filing, IngestStepOutput]:
    """Resolve, fetch, extract sections, persist. Returns (Filing, IngestStepOutput)
    with `financials` defaulted to empty (caller fills it in via Task 5).

    `issuer_cik` if supplied is treated as authoritative. Otherwise we infer
    from `source.cik_trimmed` (URL parse).
    """
    cik_trimmed = (
        str(int(issuer_cik)) if issuer_cik
        else source.cik_trimmed
    )
    if not cik_trimmed:
        raise ValueError(
            "Cannot resolve issuer CIK — supply issuer_cik or pass a full URL"
        )

    cik_padded, issuer_name = await _resolve_issuer_from_submissions(edgar, cik_trimmed)

    submissions, _ = await edgar.get_submissions(cik_padded)
    entry = await _find_filing_in_submissions(submissions, source.accession_number)
    if entry is None:
        raise ValueError(
            f"Accession {source.accession_number} not found in submissions feed for CIK {cik_padded}"
        )

    form_type = entry["form"]
    if form_type not in PROSPECTUS_FORM_TYPES:
        raise ValueError(
            f"Filing {source.accession_number} is form '{form_type}', not S-1 / S-1/A"
        )

    primary_document = source.primary_document or entry["primary_document"]
    if not primary_document:
        raise ValueError(f"No primary document for {source.accession_number}")

    accn_no_dash = source.accession_number.replace("-", "")
    primary_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_trimmed}/"
        f"{accn_no_dash}/{primary_document}"
    )

    # Upsert Filing row (under synthetic ticker so downstream code paths work)
    existing = await db.execute(
        select(Filing).where(Filing.accession_number == source.accession_number)
    )
    filing = existing.scalar_one_or_none()
    filing_date = _parse_date(entry["filing_date"]) or date.today()
    if filing is None:
        filing = Filing(
            accession_number=source.accession_number,
            cik=cik_padded,
            ticker=synthetic_ticker,
            form_type=form_type[:16],
            filing_date=filing_date,
            period_of_report=_parse_date(entry.get("period_of_report")),
            primary_document_url=primary_url,
        )
        db.add(filing)
        await db.flush()
    elif not filing.primary_document_url:
        filing.primary_document_url = primary_url

    # Fetch HTML and extract sections
    try:
        html, _ = await edgar.fetch_document(primary_url)
    except EdgarClientError as e:
        raise RuntimeError(f"Failed to fetch primary document: {e}") from e

    sections = extract_sections(html, form_type)

    # Persist sections idempotently
    existing_keys_rows = await db.execute(
        select(FilingSection.section_key).where(FilingSection.filing_id == filing.id)
    )
    existing_keys = set(existing_keys_rows.scalars().all())
    summaries: list[ExtractedSectionSummary] = []
    for section in sections:
        if section.section_key not in existing_keys:
            db.add(FilingSection(
                filing_id=filing.id,
                ticker=synthetic_ticker,
                section_key=section.section_key,
                heading=section.heading,
                text=section.text,
                char_count=section.char_count,
                extraction_method=section.extraction_method,
            ))
        summaries.append(ExtractedSectionSummary(
            section_key=section.section_key,
            heading=section.heading,
            char_count=section.char_count,
        ))
    await db.flush()

    out = IngestStepOutput(
        accession_number=source.accession_number,
        primary_document_url=primary_url,
        issuer_cik=cik_padded,
        issuer_name=issuer_name,
        proposed_ticker=None,  # not derivable from S-1 metadata; set by API caller
        form_type=form_type,
        sections=summaries,
        financials=ProspectusFinancials(),  # populated by Task 5
    )
    return filing, out
