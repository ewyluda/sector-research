"""Daily earnings prints refresh — APScheduler cron job.

Runs once per weekday at 21:00 UTC (5 PM ET). For each active board ticker:
1. Upsert earnings_prints rows from FMP calendar (idempotent).
2. For any newly-populated print (transition from eps_actual NULL to
   non-NULL), best-effort fetch the matching transcript and run a small
   Haiku call to extract guidance_direction; write back to the print row.

Transcript fetch failures are non-fatal: print row keeps
guidance_direction null. Re-running the scheduler retries.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.earnings_print import EarningsPrint
from backend.app.services.earnings_prints import (
    fetch_active_board_tickers,
    index_earnings_prints,
)
from backend.app.services.earnings_verdict import extract_guidance_direction

logger = logging.getLogger(__name__)

INTER_TICKER_SLEEP = 1.0  # seconds; FMP TTL caching makes this gentle


async def _enrich_one_print_with_guidance(
    print_row: EarningsPrint,
    fmp: FMPClient,
    db: AsyncSession,
) -> bool:
    """Fetch transcript for (ticker, fiscal_year, fiscal_quarter), run
    guidance extraction, write back. Returns True if guidance_direction
    was newly populated."""
    if print_row.guidance_direction is not None:
        return False  # already enriched
    if print_row.eps_actual is None:
        return False  # not post-print yet

    try:
        data, _ = await fmp.get_earnings_transcript(
            print_row.ticker,
            year=print_row.fiscal_year,
            quarter=print_row.fiscal_quarter,
        )
    except Exception as e:
        logger.warning(
            "[%s] transcript fetch failed (%dQ%d): %s",
            print_row.ticker, print_row.fiscal_year, print_row.fiscal_quarter, e,
        )
        return False

    if not isinstance(data, list) or not data:
        return False
    first = data[0] if isinstance(data[0], dict) else None
    if first is None:
        return False
    content = first.get("content") or ""
    if not content:
        return False

    guidance = await extract_guidance_direction(content)
    if guidance is None:
        return False

    fresh = await db.get(EarningsPrint, print_row.id)
    if fresh is None:
        return False
    fresh.guidance_direction = guidance.guidance_direction
    fresh.transcript_year = print_row.fiscal_year
    fresh.transcript_quarter = print_row.fiscal_quarter
    return True


async def run_daily_earnings_refresh() -> dict:
    """Top-level entry point invoked by the cron trigger. Returns a
    summary dict for logging."""
    fmp = FMPClient()
    started = datetime.now(timezone.utc)
    summary: dict = {
        "tickers_processed": 0,
        "prints_upserted": 0,
        "guidance_enriched": 0,
        "errors": [],
    }
    try:
        async with async_session() as db:
            tickers = await fetch_active_board_tickers(db)

        for ticker in tickers:
            try:
                async with async_session() as db:
                    rows = await index_earnings_prints(ticker, fmp, db)
                    summary["prints_upserted"] += len(rows)
                    enriched = 0
                    for r in rows:
                        if await _enrich_one_print_with_guidance(r, fmp, db):
                            enriched += 1
                    summary["guidance_enriched"] += enriched
                    await db.commit()
                summary["tickers_processed"] += 1
            except Exception as e:
                logger.exception("[%s] earnings refresh failed", ticker)
                summary["errors"].append({"ticker": ticker, "error": str(e)})
            await asyncio.sleep(INTER_TICKER_SLEEP)
    finally:
        await fmp.close()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info(
        "earnings refresh complete: %s tickers, %s prints, %s guidance, %s errors, %.1fs",
        summary["tickers_processed"],
        summary["prints_upserted"],
        summary["guidance_enriched"],
        len(summary["errors"]),
        elapsed,
    )
    return summary
