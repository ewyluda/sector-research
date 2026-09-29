"""Cost and latency per run, from the llm_calls table.

    python -m backend.scripts.llm_cost_report [--kind research] [--limit 20]

Prints one line per run (newest first) and the median cost and wall-clock
across them — the numbers behind "a research run costs $X and takes Y minutes".
"""
import argparse
import asyncio
import logging
import statistics

from sqlalchemy import func, select

from backend.app.db import async_session
from backend.app.models.llm_call import LLMCall
from backend.app.services.llm_usage import run_usage

logging.disable(logging.INFO)


async def main(kind: str, limit: int) -> None:
    async with async_session() as db:
        run_ids = (await db.execute(
            select(LLMCall.run_id).where(LLMCall.run_kind == kind)
            .group_by(LLMCall.run_id).order_by(func.max(LLMCall.created_at).desc()).limit(limit)
        )).scalars().all()
        reports = [await run_usage(db, rid) for rid in run_ids]
    if not reports:
        print(f"No {kind} runs recorded in llm_calls yet.")
        return
    print(f"{'run_id':38} {'calls':>5} {'cost $':>8} {'minutes':>7} {'cache hit':>9}")
    for r in reports:
        hit = f"{r['cache_hit_rate']:.0%}" if r["cache_hit_rate"] is not None else "—"
        print(f"{r['run_id']:38} {r['calls']:>5} {r['cost_usd']:>8.2f} {r['wall_clock_s'] / 60:>7.1f} {hit:>9}")
    print(f"\nmedian over {len(reports)} {kind} runs: "
          f"${statistics.median(r['cost_usd'] for r in reports):.2f}, "
          f"{statistics.median(r['wall_clock_s'] for r in reports) / 60:.1f} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="research")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args()
    asyncio.run(main(a.kind, a.limit))
