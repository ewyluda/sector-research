"""Live thesis eval: rerun the thesis step on frozen inputs, check every
output deterministically, measure dispersion across reruns, and score each
thesis with a rubric judge on a different model. Spends API credit — run
--dry-run first for the estimate.

    python -m backend.evals.live --dry-run
    python -m backend.evals.live [--reruns 3] [--tickers NVDA,ORCL] [--no-judge]

Writes backend/evals/results/<date>_<prompt version>.json and prints a table.
The thesis request is the production one (same system prompt, user message,
schema, model and effort), so results describe what the app does.
"""
import argparse
import asyncio
import json
import logging
import statistics
from collections import Counter
from datetime import date

from pydantic import BaseModel, Field

from backend.app.graph import llm
from backend.app.graph.llm import DEEP_MODEL, complete_structured
from backend.app.graph.nodes import build_thesis_user_message
from backend.app.graph.prompts import THESIS_SYSTEM, THESIS_USER
from backend.app.graph.state import ResearchState
from backend.app.models.phase_schemas import ThesisLLMOutput
from backend.app.services.llm_usage import CallUsage, prompt_version
from backend.evals import FIXTURES, RESULTS
from backend.evals.checks import citations, consistency, grounding, raw_data_text

logging.disable(logging.INFO)

# A different model from the one that writes the thesis, to limit self-preference.
JUDGE_MODEL = "claude-sonnet-5"
THESIS_PROMPT_VERSION = prompt_version(THESIS_SYSTEM + THESIS_USER)

JUDGE_SYSTEM = """You grade equity research theses written by an analyst. You are given the inputs
the analyst had, then the thesis. Score each dimension 1-5 against the anchors; be strict —
a 3 is competent, a 5 is what a demanding portfolio manager would praise.

- specificity: 1 = generic claims that fit any company; 5 = claims only this company, now, could support.
- evidence: 1 = assertions without support; 5 = every material claim tied to a figure or fact in the inputs.
- falsifiability: 1 = no observable test; 5 = kill criteria and catalysts are dated, measurable and would clearly settle the thesis.
- variant_view: 1 = restates consensus; 5 = a clear, reasoned difference from consensus with what would prove it.
- coherence: 1 = stance, targets, conviction and bull/bear cases contradict each other; 5 = they fit together.

Also name the single weakest point in one sentence."""


class JudgeScores(BaseModel):
    specificity: int = Field(ge=1, le=5)
    evidence: int = Field(ge=1, le=5)
    falsifiability: int = Field(ge=1, le=5)
    variant_view: int = Field(ge=1, le=5)
    coherence: int = Field(ge=1, le=5)
    weakest_point: str = Field(max_length=400)


DIMENSIONS = ("specificity", "evidence", "falsifiability", "variant_view", "coherence")


def load_inputs(tickers: list[str] | None) -> dict[str, ResearchState]:
    out = {}
    for path in sorted(FIXTURES.glob("*.json")):
        if tickers and path.stem not in tickers:
            continue
        out[path.stem] = ResearchState.from_dict(json.loads(path.read_text())["state"])
    return out


async def run_one(state: ResearchState, prompt: str, judge: bool, usage: list[CallUsage]) -> dict:
    start = len(usage)
    thesis = (await complete_structured(
        system=THESIS_SYSTEM, user=prompt, output_model=ThesisLLMOutput, model=DEEP_MODEL, max_tokens=6000,
    )).model_dump()
    result = {"thesis": thesis, "cost_usd": sum(u.cost_usd or 0 for u in usage[start:])}
    price = (state.curated_financials or {}).get("current_price")
    result["grounded_prompt"] = grounding(thesis, prompt).share
    raw = grounding(thesis, raw_data_text(state.curated_financials))
    result["grounded_data"], result["ungrounded"] = raw.share, raw.ungrounded
    cites = citations(thesis)
    result["uncited_share"] = cites.uncited_evidence / cites.evidence_items if cites.evidence_items else None
    result["invalid_citations"] = cites.invalid
    result["issues"] = consistency(thesis, price)
    if judge:
        scores = await complete_structured(
            system=JUDGE_SYSTEM,
            shared_prefix=f"INPUTS THE ANALYST HAD:\n\n{prompt}",  # cached across reruns of a ticker
            user=f"THESIS TO GRADE:\n\n{json.dumps(thesis, indent=1)}",
            output_model=JudgeScores, model=JUDGE_MODEL, max_tokens=2000,
        )
        result["judge"] = scores.model_dump()
    result["cost_usd"] = sum(u.cost_usd or 0 for u in usage[start:])
    return result


def summarize(ticker: str, runs: list[dict], price: float | None) -> dict:
    stances = Counter(r["thesis"]["stance"] for r in runs)
    convictions = [r["thesis"]["conviction_score"] for r in runs]
    bases = [r["thesis"]["price_targets"]["base"] for r in runs]
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    out = {
        "ticker": ticker, "reruns": len(runs), "price": price,
        "stances": dict(stances),
        "stance_agreement": stances.most_common(1)[0][1] / len(runs),
        "conviction_mean": statistics.fmean(convictions),
        "conviction_sd": statistics.pstdev(convictions),
        "base_target_cv": statistics.pstdev(bases) / statistics.fmean(bases),
        "implied_move": (statistics.median(bases) / price - 1) if price else None,
        "grounded_data": med([r["grounded_data"] for r in runs if r["grounded_data"] is not None]),
        "grounded_prompt": med([r["grounded_prompt"] for r in runs if r["grounded_prompt"] is not None]),
        "uncited_share": med([r["uncited_share"] for r in runs if r["uncited_share"] is not None]),
        "issues": dict(Counter(i for r in runs for i in r["issues"])),
        "cost_usd": sum(r["cost_usd"] for r in runs),
    }
    judged = [r["judge"] for r in runs if "judge" in r]
    if judged:
        out["judge"] = {d: statistics.fmean(j[d] for j in judged) for d in DIMENSIONS}
    return out


def estimate(states: dict[str, ResearchState], reruns: int, judge: bool) -> float:
    """Rough USD estimate: ~3.5 chars per token, ~4K output tokens per thesis
    (thinking included) and ~1.5K per judgement; judge reads its cache after the first rerun."""
    total = 0.0
    for state in states.values():
        tokens = len(build_thesis_user_message(state) + THESIS_SYSTEM) / 3.5
        total += reruns * (tokens * 4 + 4000 * 20) / 1e6
        if judge:
            total += (tokens * 2.5 + (reruns - 1) * tokens * 0.2 + reruns * (1500 * 10 + 2500 * 2)) / 1e6
    return total


async def main(reruns: int, tickers: list[str] | None, judge: bool, dry_run: bool) -> None:
    states = load_inputs(tickers)
    est = estimate(states, reruns, judge)
    print(f"{len(states)} inputs × {reruns} reruns{' + judge' if judge else ''} "
          f"— estimated ${est:.2f} (thesis prompt version {THESIS_PROMPT_VERSION})")
    if dry_run:
        return
    usage: list[CallUsage] = []

    async def sink(call: CallUsage) -> None:
        usage.append(call)

    llm.usage_sink = sink

    async def per_ticker(ticker: str, state: ResearchState) -> tuple[str, list[dict]]:
        # The date the frozen input was produced, not today: otherwise every
        # input reads as months stale.
        prompt = build_thesis_user_message(state, as_of=(state.created_at or "")[:10] or None)
        runs = []
        for _ in range(reruns):  # sequential: later reruns and judgements read the cache
            try:
                runs.append(await run_one(state, prompt, judge, usage))
            except Exception as exc:  # noqa: BLE001 — a failed call is a result, not a crash
                runs.append({"error": f"{type(exc).__name__}: {exc}"})
        return ticker, runs

    results = dict(await asyncio.gather(*(per_ticker(t, s) for t, s in states.items())))
    per = {}
    for ticker, runs in results.items():
        ok = [r for r in runs if "error" not in r]
        price = (states[ticker].curated_financials or {}).get("current_price")
        per[ticker] = summarize(ticker, ok, price) if ok else {"ticker": ticker, "reruns": 0}
        per[ticker]["errors"] = [r["error"] for r in runs if "error" in r]

    RESULTS.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS / f"{date.today().isoformat()}_{THESIS_PROMPT_VERSION}_{len(states)}x{reruns}.json"
    out_path.write_text(json.dumps({
        "date": date.today().isoformat(), "thesis_prompt_version": THESIS_PROMPT_VERSION,
        "model": DEEP_MODEL, "judge_model": JUDGE_MODEL if judge else None, "reruns": reruns,
        "total_cost_usd": round(sum(u.cost_usd or 0 for u in usage), 4),
        "spread": spread(results), "summary": per, "runs": results,
    }, indent=1, default=str))
    print_table(per)
    print(f"\nspread: {spread(results)}")
    print(f"\nactual cost ${sum(u.cost_usd or 0 for u in usage):.2f} · wrote {out_path}")


def spread(results: dict) -> dict:
    """Does the step discriminate? The 2026-09-28 run said avoid for 29 of 30
    theses with conviction 55-58 — perfectly 'stable' and useless."""
    theses = [r["thesis"] for runs in results.values() for r in runs if "error" not in r]
    convictions = [t["conviction_score"] for t in theses]
    return {
        "stances": dict(Counter(t["stance"] for t in theses)),
        "distinct_convictions": len(set(convictions)),
        "conviction_range": [min(convictions), max(convictions)] if convictions else None,
        "conviction_sd": statistics.pstdev(convictions) if convictions else None,
    }


def print_table(per: dict) -> None:
    pct = lambda v: "—" if v is None else f"{v:.0%}"  # noqa: E731
    print("\n| ticker | stance (agree) | conviction ± sd | base vs price | base-target CV | grounded in data | uncited | issues | judge |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in per.values():
        if not s.get("reruns"):
            print(f"| {s['ticker']} | failed: {s.get('errors')} |")
            continue
        top = max(s["stances"], key=s["stances"].get)
        judge = " / ".join(f"{s['judge'][d]:.1f}" for d in DIMENSIONS) if "judge" in s else "—"
        move = "—" if s.get("implied_move") is None else f"{s['implied_move']:+.0%}"
        print(f"| {s['ticker']} | {top} ({pct(s['stance_agreement'])}) | {s['conviction_mean']:.0f} ± {s['conviction_sd']:.0f} | {move} "
              f"| {s['base_target_cv']:.1%} | {pct(s['grounded_data'])} | {pct(s['uncited_share'])} "
              f"| {', '.join(f'{k}×{v}' for k, v in s['issues'].items()) or '—'} | {judge} |")
    print(f"\njudge columns: {' / '.join(DIMENSIONS)} (1-5)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reruns", type=int, default=3)
    ap.add_argument("--tickers", type=lambda s: [t.strip().upper() for t in s.split(",")])
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.reruns, a.tickers, not a.no_judge, a.dry_run))
