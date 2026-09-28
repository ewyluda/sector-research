"""Live smoke test for the financial model: build a baseline for real tickers
and check the result is internally sound. Nothing is saved.

Deterministic path (FMP data + TTM defaults, no LLM) for every ticker given;
add --ai to also run the AI driver pass (one deep-model call per ticker,
roughly $0.20-0.30 each; needs a completed research run for the ticker).

    python -m backend.scripts.smoke_model_baseline NVDA SMCI [--ai]

Replaces a script that exercised the pre-2026-09-27 seeding against an
invented research-state shape — the same shape the production code read, which
is why the AI pass had been receiving empty inputs.
"""
import asyncio
import logging
import sys

from backend.app.services.dcf import dcf
from backend.app.services.model_balancing import recompute
from backend.app.services.model_baseline import (
    _fetch_fmp_inputs, apply_drivers, assemble_historical_state, build_baseline_state, default_paths,
)

logging.disable(logging.INFO)  # httpx logs request URLs, API keys included


def _report(ticker: str, state, price) -> bool:
    fc = [p for p in state.periods if not p.is_historical]
    gap = max(abs(state.balance_sheet["total_assets"][p.label].value
                  - state.balance_sheet["total_liab_and_equity"][p.label].value) for p in state.periods)
    r = dcf(state)
    rev = [(p.label, round(state.income_statement["revenue"][p.label].value / 1e9, 1)) for p in fc if p.kind == "Y"]
    print(f"{ticker}: {fc[0].label}..{fc[-1].label} | annual revenue $B {rev}")
    print(f"  max balance gap ${gap:.2f} | WACC {state.assumptions.discount_rate.value:.3f} "
          f"| EV ${r.enterprise_value / 1e9:,.0f}B | ${r.intrinsic_per_share:,.2f}/sh vs price {price}")
    ok = gap < 1.0 and r.intrinsic_per_share == r.intrinsic_per_share  # balanced and not NaN
    if ok and r.intrinsic_per_share <= 0:
        print("  OK (WARN: negative equity value — plausible for a distressed name; check assumptions)")
    else:
        print("  OK" if ok else "  FAIL")
    return ok


async def main(tickers: list[str], ai: bool) -> int:
    ok = True
    for t in tickers:
        inputs = await _fetch_fmp_inputs(t)
        if ai:
            state = await build_baseline_state(ticker=t)
        else:
            state, defaults = assemble_historical_state(inputs, rf=0.042)
            apply_drivers(state, None, defaults, default_paths(state, inputs["estimates"], defaults))
            state = recompute(state)
        ok &= _report(t, state, inputs["profile"].get("price"))
    return 0 if ok else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(asyncio.run(main([a.upper() for a in args] or ["NVDA"], "--ai" in sys.argv)))
