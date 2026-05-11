"""One-shot backfill: populate verdict_outcomes from existing research + workspace runs.

Usage from project root with venv active:
    python -m backend.scripts.backfill_outcomes
"""
import asyncio
import logging

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.services import outcome_tracker


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("backfill")


async def main() -> None:
    fmp = FMPClient()
    try:
        async with async_session() as db:
            summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
            await db.commit()
    finally:
        await fmp.close()

    log.info(
        "backfill complete: created=%d existed=%d snapshots_inserted=%d errors=%d",
        summary.outcomes_created,
        summary.outcomes_existed,
        summary.snapshots_inserted,
        len(summary.errors),
    )
    for err in summary.errors[:10]:
        log.warning("  err: %s", err)


if __name__ == "__main__":
    asyncio.run(main())
