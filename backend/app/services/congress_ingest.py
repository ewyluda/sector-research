"""Congressional-trade ingest — FMP senate-trades + house-trades.

Maps /stable/senate-trades and /stable/house-trades rows (shared shape;
wire keys live-verified 2026-06-11) into congress_transactions with a
sha256 natural key for idempotent re-ingest — the insider_ingest.py
pattern. Service is commit-free — callers own the session.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.congress_transaction import CongressTransaction

logger = logging.getLogger(__name__)

# Dollar figures inside the disclosed range string, e.g. "$1,001 - $15,000".
_AMOUNT_RE = re.compile(r"\$([\d,]+)")


def _direction(transaction_type: str | None) -> str:
    """Purchase/Sale only; exchanges and unknown types are 'other'."""
    t = (transaction_type or "").strip().lower()
    if t.startswith("purchase"):
        return "buy"
    if t.startswith("sale"):
        return "sell"
    return "other"


def _amount_mid(amount: str | None) -> float | None:
    """Midpoint of the disclosed dollar range; lower bound for open-ended
    ranges ("$50,000,000 +"); None when unparseable."""
    if not amount:
        return None
    figures = [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(amount)]
    if not figures:
        return None
    if len(figures) == 1:
        return figures[0]
    return (figures[0] + figures[1]) / 2


def _parse_date(s: object) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _politician_name(row: dict) -> str:
    first = (row.get("firstName") or "").strip()
    last = (row.get("lastName") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    return str(row.get("office") or "unknown")


def _natural_key(ticker: str, chamber: str, row: dict) -> str:
    """sha256 over the identifying fields of one disclosure line.

    Date/amount fields are hashed in PARSED form so serialization drift
    can't mint duplicate rows. `owner` distinguishes same-day Self/Spouse
    lines (live-verified: Whitehouse NVDA 2026-05-08 has both).
    """
    parts = [
        ticker.upper(),
        chamber,
        _politician_name(row),
        str(_parse_date(row.get("transactionDate"))),
        str(row.get("type")),
        str(_amount_mid(row.get("amount"))),
        str(row.get("owner")),
        str(row.get("assetDescription")),
    ]
    return sha256("|".join(parts).encode()).hexdigest()


def _map_fmp_row(ticker: str, chamber: str, row: dict) -> dict:
    """CongressTransaction kwargs from one senate/house-trades row."""
    link = row.get("link")
    return {
        "ticker": ticker.upper(),
        "politician_name": _politician_name(row)[:256],
        "chamber": chamber,
        "district": (str(row["district"])[:16] if row.get("district") else None),
        "owner": (str(row["owner"])[:32] if row.get("owner") else None),
        "transaction_type": (str(row["type"])[:64] if row.get("type") else None),
        "direction": _direction(row.get("type")),
        "transaction_date": _parse_date(row.get("transactionDate")),
        "disclosure_date": _parse_date(row.get("disclosureDate")),
        "amount_range": (str(row["amount"])[:64] if row.get("amount") else None),
        "amount_mid": _amount_mid(row.get("amount")),
        "disclosure_link": (str(link)[:512] if link else None),
        "natural_key": _natural_key(ticker, chamber, row),
    }


async def upsert_congress_transactions(
    db: AsyncSession, ticker: str, *, senate_rows: list[dict], house_rows: list[dict]
) -> dict:
    """Insert rows whose natural_key isn't present yet. Commit-free."""
    summary = {"ticker": ticker.upper(), "added": 0, "skipped_existing": 0}
    mapped = [_map_fmp_row(ticker, "senate", r) for r in senate_rows]
    mapped += [_map_fmp_row(ticker, "house", r) for r in house_rows]
    if not mapped:
        return summary

    keys = [m["natural_key"] for m in mapped]
    existing_result = await db.execute(
        select(CongressTransaction.natural_key).where(
            CongressTransaction.natural_key.in_(keys)
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
        db.add(CongressTransaction(**m))
        summary["added"] += 1
    return summary
