"""Live smoke test: one small call per LLM path, on that path's real model and
output schema.

Unit tests mock the LLM, so they cannot catch API-contract breaks — the
Sonnet 4.6 prefill 400 that shipped at five call sites, a schema the API
rejects as too complex, a parameter one model refuses. Each probe asks for a
minimal example for a fictional company, so it exercises the request shape,
not the prompt. Run after changing graph/llm.py, a model setting, or an output
schema (about $0.10):

    python -m backend.scripts.smoke_structured_outputs [--only QuickScreenOutput,...]

PATHS must list every complete_structured call site; test_llm_paths_registry
fails CI when a new one is added without a probe here.
"""
import argparse
import asyncio
import logging
import sys

from backend.app.graph import llm
from backend.app.graph.llm import DEEP_MODEL, FAST_MODEL, complete, complete_structured
from backend.app.graph.model_baseline_node import _BaselineDriversLLMOutput
from backend.app.models.phase_schemas import (
    DeepDiveCategoryOutput, PositionMonitorOutput, QuickScreenOutput, RiskStressTestOutput, ThesisLLMOutput,
)
from backend.app.models.prospectus_schemas import ProspectusCategoryResult, ProspectusFinancials, ProspectusThesisOutput
from backend.app.services import edgar_competition, edgar_relationships
from backend.app.services.earnings_brief import BriefOutput
from backend.app.services.earnings_verdict import GuidanceOutput, VerdictOutput
from backend.app.services.event_classifier import EventClassification
from backend.app.services.questions import _RetryAnswer
from backend.app.services.transcript_delta import _AxesEnvelope

logging.disable(logging.INFO)  # httpx logs request URLs

# (call site as "module:schema", output schema, model) — one per complete_structured call.
PATHS: list[tuple[str, type, str]] = [
    ("graph/model_baseline_node.py:_BaselineDriversLLMOutput", _BaselineDriversLLMOutput, DEEP_MODEL),
    ("graph/nodes.py:QuickScreenOutput", QuickScreenOutput, FAST_MODEL),
    ("graph/nodes.py:DeepDiveCategoryOutput", DeepDiveCategoryOutput, DEEP_MODEL),
    ("graph/nodes.py:ThesisLLMOutput", ThesisLLMOutput, DEEP_MODEL),
    ("graph/nodes.py:RiskStressTestOutput", RiskStressTestOutput, DEEP_MODEL),
    ("graph/nodes.py:PositionMonitorOutput", PositionMonitorOutput, FAST_MODEL),
    ("services/earnings_brief.py:BriefOutput", BriefOutput, FAST_MODEL),
    ("services/earnings_verdict.py:GuidanceOutput", GuidanceOutput, FAST_MODEL),
    ("services/earnings_verdict.py:VerdictOutput", VerdictOutput, FAST_MODEL),
    ("services/edgar_competition.py:ExtractionResult", edgar_competition.ExtractionResult, FAST_MODEL),
    ("services/edgar_relationships.py:ExtractionResult", edgar_relationships.ExtractionResult, FAST_MODEL),
    ("services/event_classifier.py:EventClassification", EventClassification, FAST_MODEL),
    ("services/prospectus_categories.py:ProspectusCategoryResult", ProspectusCategoryResult, DEEP_MODEL),
    ("services/prospectus_financials.py:ProspectusFinancials", ProspectusFinancials, DEEP_MODEL),
    ("services/prospectus_thesis.py:ProspectusThesisOutput", ProspectusThesisOutput, DEEP_MODEL),
    ("services/questions.py:_RetryAnswer", _RetryAnswer, DEEP_MODEL),
    ("services/transcript_delta.py:_AxesEnvelope", _AxesEnvelope, FAST_MODEL),
]

_SYSTEM = ("You are testing an API integration. Produce a minimal but fully valid example of the requested "
           "JSON for a fictional company, ACME Corp (ticker ACME), trading at $50. Keep every string short; "
           "use the fewest list items the schema allows.")


async def _probe(site: str, schema: type, model: str) -> tuple[str, bool, str]:
    try:
        await complete_structured(system=_SYSTEM, user="Return the example JSON.", output_model=schema,
                                  model=model, max_tokens=4000, use_cache=False)
    except Exception as e:  # noqa: BLE001 — report every failure mode
        return site, False, f"{type(e).__name__}: {str(e)[:200]}"
    return site, True, model


async def _probe_text(model: str) -> tuple[str, bool, str]:
    """The plain-text path (transcript passes use complete(), not a schema)."""
    try:
        text = await complete(system=_SYSTEM, user="Reply with the single word OK.", model=model, max_tokens=50)
    except Exception as e:  # noqa: BLE001
        return f"complete() on {model}", False, f"{type(e).__name__}: {str(e)[:200]}"
    return f"complete() on {model}", bool(text.strip()), model


async def main(only: set[str] | None) -> int:
    usage = []

    async def sink(call) -> None:
        usage.append(call)

    llm.usage_sink = sink
    paths = [p for p in PATHS if not only or p[1].__name__ in only]
    probes = [_probe(*p) for p in paths] + ([] if only else [_probe_text(FAST_MODEL), _probe_text(DEEP_MODEL)])
    results = await asyncio.gather(*probes)
    for site, ok, detail in results:
        print(f"{'OK  ' if ok else 'FAIL'} {site} ({detail})")
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n{len(results) - failed}/{len(results)} paths OK · ${sum(u.cost_usd or 0 for u in usage):.2f}")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=lambda s: set(s.split(",")))
    sys.exit(asyncio.run(main(ap.parse_args().only)))
