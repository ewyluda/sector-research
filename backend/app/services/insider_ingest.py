"""Form 4 insider-transaction ingest — FMP-primary, EDGAR-traceable.

Maps `FMPClient.get_insider_trading` rows into insider_transactions with a
sha256 natural key for idempotent re-ingest. Wire keys live-verified
2026-06-10 (see plan Task 1); adjust _natural_key if FMP renames.
Service is commit-free — callers own the session (peer_sets convention).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.insider_transaction import InsiderTransaction

logger = logging.getLogger(__name__)

# Dashed accession number anywhere in the SEC link.
_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")

def _direction(transaction_type: str | None) -> str:
    """Open-market purchase/sale only; everything else is 'other'."""
    code = (transaction_type or "").strip().upper()
    if code.startswith("P"):
        return "buy"
    if code.startswith("S"):
        return "sell"
    return "other"


def _accession_from_link(link: str | None) -> str | None:
    if not link:
        return None
    m = _ACCESSION_RE.search(link)
    return m.group(1) if m else None


def _natural_key(ticker: str, row: dict) -> str:
    """sha256 over the identifying fields of one transaction line.

    Numeric/date fields are hashed in PARSED form so serialization drift
    (1000 vs 1000.0, date vs datetime string) can't mint duplicate rows.
    securityName distinguishes same-day lines on different securities.
    """
    parts = [
        ticker.upper(),
        str(row.get("reportingName")),
        str(_parse_date(row.get("transactionDate"))),
        str(row.get("transactionType")),
        str(_num(row.get("securitiesTransacted"))),
        str(_num(row.get("price"))),
        str(row.get("url") or row.get("link")),
        str(row.get("securityName")),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _parse_date(s: object) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _num(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _map_fmp_row(ticker: str, row: dict) -> dict:
    """InsiderTransaction kwargs from one FMP insider-trading/search row."""
    link = row.get("url") or row.get("link")  # live key is `url` (verified 2026-06-10)
    return {
        "ticker": ticker.upper(),
        "insider_name": str(row.get("reportingName") or "unknown")[:256],
        "insider_title": (str(row["typeOfOwner"])[:256] if row.get("typeOfOwner") else None),
        "transaction_type": (str(row["transactionType"])[:64] if row.get("transactionType") else None),
        "direction": _direction(row.get("transactionType")),
        "transaction_date": _parse_date(row.get("transactionDate")),
        "shares": _num(row.get("securitiesTransacted")),
        "price": _num(row.get("price")),
        "shares_owned_after": _num(row.get("securitiesOwned")),
        "accession_number": _accession_from_link(link),
        "sec_link": (str(link)[:512] if link else None),
        "natural_key": _natural_key(ticker, row),
    }


async def upsert_insider_transactions(
    db: AsyncSession, ticker: str, rows: list[dict]
) -> dict:
    """Insert rows whose natural_key isn't present yet. Commit-free."""
    summary = {"ticker": ticker.upper(), "added": 0, "skipped_existing": 0}
    if not rows:
        return summary

    mapped = [_map_fmp_row(ticker, r) for r in rows]
    keys = [m["natural_key"] for m in mapped]
    existing_result = await db.execute(
        select(InsiderTransaction.natural_key).where(
            InsiderTransaction.natural_key.in_(keys)
        )
    )
    existing = set(existing_result.scalars().all())

    seen: set[str] = set()
    for m in mapped:
        key = m["natural_key"]
        if key in existing or key in seen:
            summary["skipped_existing"] += 1
            continue
        seen.add(key)
        db.add(InsiderTransaction(**m))
        summary["added"] += 1
    return summary
