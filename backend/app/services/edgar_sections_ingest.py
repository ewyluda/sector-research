"""Ingest narrative filing sections (10-K, 10-Q, DEF 14A) per ticker.

Complementary to `edgar_ingest.py` (which stores XBRL numeric facts).

For each ticker:
  1. Resolve CIK.
  2. Walk the SEC submissions history to find the latest 10-K, latest 10-Q,
     and latest DEF 14A.
  3. For each, upsert a `filings` row (XBRL ingest may or may not have
     created one), fetch the primary document HTML, and extract narrative
     sections via `edgar_html.extract_sections`.
  4. Persist to `filing_sections`, idempotent on (filing_id, section_key).

Returns a summary dict the caller (an API endpoint) can hand back to the
frontend. No transactional boundary management — caller owns the session.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient, EdgarClientError
from backend.app.models.filing import Filing, FilingSection
from backend.app.services.edgar_html import extract_sections

logger = logging.getLogger(__name__)

TARGET_FORMS: tuple[str, ...] = ("10-K", "10-Q", "DEF 14A", "20-F")


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _latest_per_form(submissions: dict) -> dict[str, dict]:
    """Return {form_type: {accession, primary_document, filing_date, period}} for
    the most recent filing of each target form type."""
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    forms = recent.get("form", []) or []
    accessions = recent.get("accessionNumber", []) or []
    docs = recent.get("primaryDocument", []) or []
    filing_dates = recent.get("filingDate", []) or []
    periods = recent.get("reportDate", []) or []

    latest: dict[str, dict] = {}
    # Entries are already in reverse-chronological order by filingDate.
    for i, form in enumerate(forms):
        if form not in TARGET_FORMS or form in latest:
            continue
        latest[form] = {
            "accession_number": accessions[i] if i < len(accessions) else None,
            "primary_document": docs[i] if i < len(docs) else None,
            "filing_date": _parse_date(filing_dates[i] if i < len(filing_dates) else None),
            "period_of_report": _parse_date(periods[i] if i < len(periods) else None),
        }
        if len(latest) == len(TARGET_FORMS):
            break
    return latest


async def _upsert_filing(
    db: AsyncSession,
    ticker: str,
    cik: str,
    form_type: str,
    accession_number: str,
    primary_document_url: str,
    filing_date: date,
    period_of_report: date | None,
) -> Filing:
    existing = await db.execute(
        select(Filing).where(Filing.accession_number == accession_number)
    )
    hit = existing.scalar_one_or_none()
    if hit is not None:
        # Backfill primary_document_url if the XBRL ingest left it None.
        if not hit.primary_document_url:
            hit.primary_document_url = primary_document_url
        return hit

    filing = Filing(
        accession_number=accession_number,
        cik=cik,
        ticker=ticker.upper(),
        form_type=form_type[:16],
        filing_date=filing_date or date.today(),
        period_of_report=period_of_report,
        primary_document_url=primary_document_url,
    )
    db.add(filing)
    await db.flush()
    return filing


async def _existing_section_keys(db: AsyncSession, filing_id: str) -> set[str]:
    rows = await db.execute(
        select(FilingSection.section_key).where(FilingSection.filing_id == filing_id)
    )
    return set(rows.scalars().all())


async def ingest_ticker_sections(
    ticker: str, db: AsyncSession, edgar: EdgarClient
) -> dict:
    """Fetch latest 10-K / 10-Q / DEF 14A for a ticker and persist sections.

    Returns a summary dict with counts per form.
    """
    summary: dict = {
        "ticker": ticker.upper(),
        "cik": None,
        "filings_processed": 0,
        "sections_added": 0,
        "sections_skipped_existing": 0,
        "per_form": {},
        "errors": [],
    }

    cik, _ = await edgar.get_ticker_to_cik(ticker)
    if not cik:
        summary["errors"].append(f"No CIK for ticker {ticker}")
        return summary
    summary["cik"] = cik

    try:
        submissions, _ = await edgar.get_submissions(cik)
    except EdgarClientError as e:
        summary["errors"].append(f"submissions fetch failed: {e}")
        return summary

    latest = _latest_per_form(submissions)
    if not latest:
        summary["errors"].append("No target-form filings in recent submissions")
        return summary

    cik_trimmed = str(int(cik))
    for form_type, meta in latest.items():
        per_form: dict = {
            "accession_number": meta["accession_number"],
            "filing_date": meta["filing_date"].isoformat() if meta["filing_date"] else None,
            "sections_added": 0,
            "sections_skipped_existing": 0,
            "error": None,
        }
        summary["per_form"][form_type] = per_form

        accn = meta["accession_number"]
        doc = meta["primary_document"]
        if not accn or not doc:
            per_form["error"] = "missing accession or primary document"
            continue

        accn_no_dash = accn.replace("-", "")
        primary_url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_trimmed}/{accn_no_dash}/{doc}"
        )

        try:
            filing = await _upsert_filing(
                db=db,
                ticker=ticker,
                cik=cik,
                form_type=form_type,
                accession_number=accn,
                primary_document_url=primary_url,
                filing_date=meta["filing_date"],
                period_of_report=meta["period_of_report"],
            )
        except Exception as e:
            per_form["error"] = f"filing upsert failed: {e}"
            logger.exception("filing upsert failed for %s %s", ticker, accn)
            continue

        try:
            html, _ = await edgar.fetch_document(primary_url)
        except EdgarClientError as e:
            per_form["error"] = f"document fetch failed: {e}"
            continue

        sections = extract_sections(html, form_type)
        if not sections:
            per_form["error"] = "no sections extracted"
            continue

        existing_keys = await _existing_section_keys(db, filing.id)
        for section in sections:
            if section.section_key in existing_keys:
                per_form["sections_skipped_existing"] += 1
                summary["sections_skipped_existing"] += 1
                continue
            db.add(FilingSection(
                filing_id=filing.id,
                ticker=ticker.upper(),
                section_key=section.section_key,
                heading=section.heading,
                text=section.text,
                char_count=section.char_count,
                extraction_method=section.extraction_method,
            ))
            per_form["sections_added"] += 1
            summary["sections_added"] += 1

        summary["filings_processed"] += 1

    await db.flush()
    logger.info(
        "EDGAR sections: %s — %d filings, %d sections added, %d skipped",
        ticker,
        summary["filings_processed"],
        summary["sections_added"],
        summary["sections_skipped_existing"],
    )
    return summary


async def get_latest_sections_by_keys(
    ticker: str, section_keys: Iterable[str], db: AsyncSession
) -> dict[str, dict]:
    """Return {section_key: {text, heading, form_type, filing_date, accession_number}}
    for the most recently filed copy of each requested section_key.

    Only considers sections whose parent filing is the most recent of its
    form type for that ticker (a ticker that has two 10-Ks in the DB will
    prefer the newer one). Empty dict if the ticker has no ingested sections.
    """
    keys = [k for k in section_keys if k]
    if not keys:
        return {}

    result = await db.execute(
        select(FilingSection, Filing)
        .join(Filing, Filing.id == FilingSection.filing_id)
        .where(
            Filing.ticker == ticker.upper(),
            FilingSection.section_key.in_(keys),
        )
        .order_by(FilingSection.section_key, Filing.filing_date.desc())
    )
    out: dict[str, dict] = {}
    for section, filing in result.all():
        if section.section_key in out:
            continue  # already have the most recent for this key
        out[section.section_key] = {
            "text": section.text,
            "heading": section.heading,
            "char_count": section.char_count,
            "form_type": filing.form_type,
            "filing_date": filing.filing_date.isoformat(),
            "accession_number": filing.accession_number,
        }
    return out


async def ingest_batch_sections(
    tickers: Iterable[str], db: AsyncSession, edgar: EdgarClient
) -> list[dict]:
    """Run ingest for each ticker sequentially. Errors captured in the
    per-ticker summary; one failed ticker does not abort the batch."""
    out: list[dict] = []
    for t in tickers:
        try:
            out.append(await ingest_ticker_sections(t, db, edgar))
        except Exception as e:
            logger.exception("batch ingest failed for %s", t)
            out.append({"ticker": t.upper(), "errors": [f"unhandled: {e}"]})
    return out
