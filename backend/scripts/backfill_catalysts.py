"""One-shot backfill: walk every research_run with a parsed thesis and
insert Catalyst rows for any run that doesn't have them yet.

The script calls promote_catalysts (which is idempotent on run_id since
Task 5 — it deletes existing rows for the run before re-inserting),
so it's safe to re-run. It passes each run's original created_at as the
relative_anchor so historical "Next N months" timeframes anchor to when
the thesis was originally written, not to today.

Usage:
    cd /Users/ericwyluda/Development/projects/sector-research
    source backend/venv/bin/activate
    python -m backend.scripts.backfill_catalysts
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.graph.state import ResearchState
from backend.app.models.phase_schemas import ThesisOutput
from backend.app.models.research_run import ResearchRun
from backend.app.services.catalyst_promotion import promote_catalysts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_catalysts")


async def main() -> int:
    fmp = FMPClient()

    try:
        async with async_session() as db:
            result = await db.execute(select(ResearchRun))
            runs = result.scalars().all()

        log.info("scanning %d total runs", len(runs))
        promoted = skipped_no_thesis = parse_failed = 0

        for run in runs:
            # phase_outputs is nested inside the JSONB state column
            state_dict = run.state if isinstance(run.state, dict) else {}
            po = state_dict.get("phase_outputs", {}) if isinstance(state_dict, dict) else {}
            thesis = po.get("thesis", {}) if isinstance(po, dict) else {}
            structured = thesis.get("structured") if isinstance(thesis, dict) else None
            if not structured:
                skipped_no_thesis += 1
                continue

            async with async_session() as db:
                try:
                    parsed = ThesisOutput.model_validate(structured)
                except Exception as e:
                    log.warning("[%s] thesis parse failed: %s", run.id, e)
                    parse_failed += 1
                    continue

                # Reconstruct a minimal ResearchState for promote_catalysts.
                # It only reads ticker and run_id from state.
                rs = ResearchState(
                    ticker=run.ticker,
                    theme_id=str(run.theme_id) if run.theme_id else "",
                    run_id=str(run.id),
                )

                # Pass the original run's created_at so historical relative
                # timeframes ("Next 6 mo") anchor to when the thesis was
                # actually written. Idempotent: promote_catalysts deletes
                # existing rows for this run_id before re-inserting.
                await promote_catalysts(
                    rs, parsed, fmp, db,
                    relative_anchor=run.created_at,
                )
                await db.commit()
                promoted += 1
                log.info("[%s/%s] promoted %d catalysts",
                         run.ticker, run.id, len(parsed.catalysts))

        log.info(
            "done: promoted=%d skipped_no_thesis=%d parse_failed=%d",
            promoted, skipped_no_thesis, parse_failed,
        )
        return 0
    finally:
        await fmp.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
