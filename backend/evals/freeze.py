"""Freeze eval inputs: the state each thesis is written from, per ticker.

Takes the latest completed run for each ticker (read-only), removes the
thesis / risk / position outputs, and trims what the thesis prompt doesn't
read (transcript analysis, all but the last day of prices). The result is
the exact input the thesis step sees, fixed so prompt changes can be compared
on identical inputs.

    python -m backend.evals.freeze [--tickers 10]
"""
import argparse
import asyncio
import json
import logging
import re

from sqlalchemy import select

from backend.app.db import async_session
from backend.app.models.research_run import ResearchRun
from backend.evals import FIXTURES

logging.disable(logging.INFO)

_DROP_OUTPUTS = ("thesis", "risk", "position")


def freeze_state(state: dict) -> dict:
    state = json.loads(json.dumps(state))  # deep copy
    state["phase_outputs"] = {k: v for k, v in (state.get("phase_outputs") or {}).items()
                              if k not in _DROP_OUTPUTS}
    state["transcript_analysis"] = None
    cf = state.get("curated_financials") or {}
    if cf.get("daily_prices"):
        cf["daily_prices"] = cf["daily_prices"][-1:]
    state.update(phase="thesis_construction", status="in_progress", loop_context=None)
    return state


async def main(n: int) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    async with async_session() as db:
        runs = (await db.execute(
            select(ResearchRun).where(ResearchRun.status.in_(["completed", "watchlist"]))
            .order_by(ResearchRun.created_at.desc())
        )).scalars().all()
    seen: set[str] = set()
    for run in runs:
        if run.ticker in seen or not (run.state or {}).get("curated_financials"):
            continue
        seen.add(run.ticker)
        path = FIXTURES / f"{run.ticker}.json"
        text = json.dumps({"source_run_id": run.id, "state": freeze_state(run.state)}, indent=1)
        # Stored citation URLs carry a masked "apikey=***"; refuse anything unmasked.
        if re.search(r"apikey=[A-Za-z0-9]{8,}", text, re.IGNORECASE):
            raise RuntimeError(f"{run.ticker}: state contains an unmasked API key — not writing a fixture")
        path.write_text(text)
        print(f"{run.ticker}: run {run.id} ({run.created_at:%Y-%m-%d}) → {path.name} {path.stat().st_size // 1024} KB")
        if len(seen) >= n:
            break


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", type=int, default=10)
    asyncio.run(main(ap.parse_args().tickers))
