"""Deterministic thesis checks over research runs already stored in the
database — free, no model calls. The baseline the live eval is compared to.

    python -m backend.evals.offline [--limit 50]

The prompt is rebuilt from each run's final state with the current prompt
builder, so it approximates (not reproduces) what the model saw: runs that
looped were written against earlier deep-dive outputs, and older runs used
older prompt templates.
"""
import argparse
import asyncio
import logging
import statistics

from sqlalchemy import select

from backend.app.db import async_session
from backend.app.graph.nodes import build_thesis_user_message
from backend.app.graph.state import ResearchState
from backend.app.models.research_run import ResearchRun
from backend.evals.checks import citations, consistency, grounding, raw_data_text

logging.disable(logging.INFO)


def evaluate(state: ResearchState) -> dict | None:
    thesis = ((state.phase_outputs.get("thesis") or {}).get("structured")) or None
    if not isinstance(thesis, dict):
        return None
    prompt = build_thesis_user_message(state)
    price = (state.curated_financials or {}).get("current_price")
    g, c = grounding(thesis, prompt), citations(thesis)
    raw = grounding(thesis, raw_data_text(state.curated_financials)) if state.curated_financials else None
    return {
        "ticker": state.ticker,
        "stance": thesis.get("stance") or "—",
        "grounded": g.share,
        "grounded_raw": raw.share if raw else None,
        "numbers": g.total,
        "ungrounded": g.ungrounded,
        "invalid_citations": c.invalid,
        "uncited_share": c.uncited_evidence / c.evidence_items if c.evidence_items else None,
        "issues": consistency(thesis, price),
    }


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0%}"


async def main(limit: int) -> None:
    async with async_session() as db:
        runs = (await db.execute(
            select(ResearchRun).where(ResearchRun.status.in_(["completed", "watchlist"]))
            .order_by(ResearchRun.created_at.desc()).limit(limit)
        )).scalars().all()
    rows = [r for r in (evaluate(ResearchState.from_dict(run.state)) for run in runs) if r]
    print(f"{'ticker':6} {'stance':6} {'prompt':>6} {'data':>5} {'nums':>4} {'uncited':>7}  issues")
    for r in rows:
        print(f"{r['ticker']:6} {r['stance']:6} {_pct(r['grounded']):>6} {_pct(r['grounded_raw']):>5} {r['numbers']:>4} "
              f"{_pct(r['uncited_share']):>7}  {', '.join(r['issues']) or '—'}")
    shares = [r["grounded"] for r in rows if r["grounded"] is not None]
    raw_shares = [r["grounded_raw"] for r in rows if r["grounded_raw"] is not None]
    issue_counts: dict[str, int] = {}
    for r in rows:
        for i in r["issues"]:
            issue_counts[i] = issue_counts.get(i, 0) + 1
    print(f"\n{len(rows)} theses · median grounded in prompt {_pct(statistics.median(shares) if shares else None)}, "
          f"in raw data {_pct(statistics.median(raw_shares) if raw_shares else None)} · "
          f"invalid citation tags {sum(len(r['invalid_citations']) for r in rows)} · issues {issue_counts}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50)
    asyncio.run(main(ap.parse_args().limit))
