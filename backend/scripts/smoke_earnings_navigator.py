"""End-to-end smoke for Tier 2.5 — Earnings Cycle Navigator.

Runs three assertions against the live dev DB:
1. Indexer materializes a print row for an active board ticker.
2. Verdict round-trips Haiku → DB persist for a synthetic post-print row.
3. Read-through enrichment surfaces eps_surprise_pct on a peer-event
   payload when a matching earnings_print row exists.

Usage:
    PYTHONPATH=. python -m backend.scripts.smoke_earnings_navigator <run_id> <peer_ticker>

Exits 0 on green, 1 with the failed assertion's name on red.
Cleans up the synthetic earnings_print rows created in assertions 2 and 3.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.services.earnings_prints import (
    fetch_active_board_tickers,
    index_earnings_prints,
)
from backend.app.services.earnings_verdict import compute_verdict
from backend.app.services.read_through import compute_peer_events

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def assertion_1_indexer(fmp: FMPClient) -> None:
    async with async_session() as db:
        tickers = await fetch_active_board_tickers(db)
    assert tickers, "no active board tickers"
    ticker = tickers[0]
    async with async_session() as db:
        rows = await index_earnings_prints(ticker, fmp, db)
        await db.commit()
    assert any(r.eps_estimated is not None for r in rows), \
        f"[{ticker}] no eps_estimated in any of {len(rows)} rows"
    logger.info("assertion 1 passed: %s prints upserted for %s", len(rows), ticker)


async def assertion_2_verdict(run_id: str, fmp: FMPClient) -> str:
    """Synthesize a post-print row, compute verdict, assert shape. Returns
    the synthetic print_id so cleanup can remove it. If the verdict step
    fails, cleans up the synthetic row before propagating the error."""
    synth_ticker = "ZZZS"
    print_id = str(uuid4())
    async with async_session() as db:
        row = EarningsPrint(
            id=print_id,
            ticker=synth_ticker,
            fiscal_year=2026,
            fiscal_quarter=1,
            earnings_date=date(2026, 4, 30),
            eps_estimated=1.50,
            eps_actual=1.62,
            revenue_estimated=10_000_000_000,
            revenue_actual=10_300_000_000,
            eps_surprise_pct=0.08,
            revenue_surprise_pct=0.03,
            guidance_direction="raised",
        )
        db.add(row)
        await db.commit()

    verdict_succeeded = False
    try:
        async with async_session() as db:
            v = await compute_verdict(run_id, print_id, fmp, db)
            await db.commit()
            assert v.verdict in {"confirms", "threatens", "neutral", "insufficient"}, \
                f"unexpected verdict: {v.verdict!r}"
            assert isinstance(v.pillars_addressed, list)
            assert len(v.summary_md) > 50
        logger.info(
            "assertion 2 passed: verdict=%s pillars=%d summary_chars=%d",
            v.verdict, len(v.pillars_addressed), len(v.summary_md),
        )
        verdict_succeeded = True
        return print_id
    finally:
        if not verdict_succeeded:
            # Cleanup the synthetic row before propagating; main()'s
            # finally block won't run cleanup_assertion_2 because
            # print_id was never returned.
            async with async_session() as db:
                await db.execute(delete(EarningsPrint).where(EarningsPrint.id == print_id))
                await db.commit()


async def assertion_3_read_through_enrichment(peer_ticker: str) -> None:
    """Insert a synthetic catalyst + post-print row using a synthetic ticker
    (never a real ticker) to avoid unique-constraint collisions with real rows
    upserted in assertion 1. Verifies the peer-event payload includes
    eps_surprise_pct, then cleans up."""
    synth_ticker = "ZZZP"
    synth_print_id = str(uuid4())
    synth_cat_id = str(uuid4())
    today = datetime.now(timezone.utc).date()
    async with async_session() as db:
        any_run_q = select(ResearchRun).where(ResearchRun.status == "completed").limit(1)
        any_run = (await db.execute(any_run_q)).scalars().first()
        assert any_run is not None, "no completed runs to attach synthetic catalyst to"

        synth_cat = Catalyst(
            id=synth_cat_id,
            run_id=str(any_run.id),
            ticker=synth_ticker,
            ordinal=999,
            timeframe="Smoke synthetic",
            description="Smoke synthetic earnings",
            type="earnings",
            signposts=[],
            linked_pillar=None,
            expected_date=today + timedelta(days=2),
            expected_window_start=today + timedelta(days=2),
            expected_window_end=today + timedelta(days=3),
            date_source="smoke",
        )
        synth_print = EarningsPrint(
            id=synth_print_id,
            ticker=synth_ticker,
            fiscal_year=today.year,
            fiscal_quarter=(today.month - 1) // 3 + 1,
            earnings_date=today + timedelta(days=2),
            eps_estimated=1.0,
            eps_actual=1.1,
            revenue_estimated=1_000_000_000,
            revenue_actual=1_050_000_000,
            eps_surprise_pct=0.10,
            revenue_surprise_pct=0.05,
            guidance_direction="maintained",
        )
        db.add_all([synth_cat, synth_print])
        await db.commit()

    try:
        async with async_session() as db:
            until = datetime.now(timezone.utc) + timedelta(days=10)
            since = until - timedelta(days=30)
            events = await compute_peer_events(db, since, until)
        match = next(
            (e for e in events
             if e.event_type == "earnings"
             and e.peer_ticker == synth_ticker
             and e.payload.get("eps_surprise_pct") == 0.10),
            None,
        )
        assert match is not None, "no enriched earnings event with eps_surprise_pct=0.10"
        logger.info("assertion 3 passed: enriched payload keys=%s", list(match.payload.keys()))
    finally:
        async with async_session() as db:
            await db.execute(delete(Catalyst).where(Catalyst.id == synth_cat_id))
            await db.execute(delete(EarningsPrint).where(EarningsPrint.id == synth_print_id))
            await db.commit()


async def cleanup_assertion_2(print_id: str, run_id: str) -> None:
    async with async_session() as db:
        await db.execute(
            delete(ThesisPrintVerdict)
            .where(ThesisPrintVerdict.run_id == run_id)
            .where(ThesisPrintVerdict.earnings_print_id == print_id)
        )
        await db.execute(delete(EarningsPrint).where(EarningsPrint.id == print_id))
        await db.commit()


async def main(run_id: str, peer_ticker: str) -> int:
    fmp = FMPClient()
    print_id: str | None = None
    try:
        await assertion_1_indexer(fmp)
        print_id = await assertion_2_verdict(run_id, fmp)
        await assertion_3_read_through_enrichment(peer_ticker)
        return 0
    except AssertionError as e:
        logger.error("ASSERTION FAILED: %s", e)
        return 1
    except Exception as e:
        logger.error("UNEXPECTED ERROR: %s", e)
        return 1
    finally:
        if print_id is not None:
            await cleanup_assertion_2(print_id, run_id)
        await fmp.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: smoke_earnings_navigator.py <run_id> <peer_ticker>", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main(sys.argv[1], sys.argv[2])))
