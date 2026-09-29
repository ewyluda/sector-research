"""One-off: correct timestamps written +4h/+5h by naive datetime.utcnow().

Before commit 73ac59f (2026-09-27), these columns were filled with naive
datetime.utcnow() values, which asyncpg encodes as local time: a UTC wall
clock read as America/New_York, so each stored instant is 4h (EDT) or 5h (EST)
late. The correction reads the stored instant back as New York wall-clock time
and re-reads that as UTC — DST-aware per row:

    ts := (ts AT TIME ZONE 'America/New_York') AT TIME ZONE 'UTC'

Only rows stored before --cutoff are touched, so rows written by the fixed
code are left alone. Run it once per database, with no backend on old code
writing to it; a second run would shift the same rows again.

    python -m backend.scripts.fix_naive_timestamps --cutoff 2026-09-28T17:50:00Z           # dry run
    python -m backend.scripts.fix_naive_timestamps --cutoff 2026-09-28T17:50:00Z --apply   # one transaction
"""
import argparse
import asyncio
import logging
from datetime import datetime

from sqlalchemy import text

from backend.app.db import async_session

logging.disable(logging.INFO)

# Every column the old code filled with naive utcnow (see commit 73ac59f).
COLUMNS: list[tuple[str, str]] = [
    ("xbrl_facts", "created_at"),
    ("filing_sections", "extracted_at"),
    ("filing_sections", "relationships_extracted_at"),
    ("filing_sections", "competition_extracted_at"),
    ("relationships", "extracted_at"),
    ("filing_segments", "extracted_at"),
    ("competitor_landscape", "extracted_at"),
    ("counterparty_aliases", "created_at"),
    ("transcript_extractions", "extracted_at"),
    ("congress_transactions", "ingested_at"),
    ("insider_transactions", "ingested_at"),
    ("material_events", "classified_at"),
]
_FIX = "({c} AT TIME ZONE 'America/New_York') AT TIME ZONE 'UTC'"


async def main(cutoff_iso: str, apply: bool) -> None:
    cutoff = datetime.fromisoformat(cutoff_iso)
    if cutoff.tzinfo is None:
        raise SystemExit("--cutoff needs an explicit offset, e.g. 2026-09-28T17:50:00Z")
    async with async_session() as db:
        total = 0
        for table, col in COLUMNS:
            where = f"{col} IS NOT NULL AND {col} < :cutoff"
            n, newest, fixed = (await db.execute(text(
                f"SELECT count(*), max({col}), max({_FIX.format(c=col)}) FROM {table} WHERE {where}"
            ), {"cutoff": cutoff})).one()
            total += n
            print(f"{table}.{col}: {n} rows; newest {newest} → {fixed}")
            if apply and n:
                await db.execute(text(f"UPDATE {table} SET {col} = {_FIX.format(c=col)} WHERE {where}"),
                                 {"cutoff": cutoff})
        if apply:
            await db.commit()
        print(f"\n{total} rows {'corrected' if apply else 'would be corrected (dry run; pass --apply)'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", required=True, help="only rows stored before this instant (ISO 8601 with offset)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.cutoff, a.apply))
