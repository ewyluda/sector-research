"""Live smoke test: one tiny structured-output call per configured model.

Unit tests mock the LLM, so they cannot catch API-contract breaks such as the
Sonnet 4.6 prefill 400 that shipped at five call sites. Run this after any
change to `graph/llm.py` or the model settings (costs well under $0.05):

    python -m backend.scripts.smoke_structured_outputs
"""
import asyncio
import sys

from pydantic import BaseModel, Field

from backend.app.graph.llm import HAIKU, SONNET, complete_structured


class _Probe(BaseModel):
    ticker: str
    sector: str
    confidence: int = Field(ge=0, le=100)


async def _probe(model: str) -> bool:
    try:
        out = await complete_structured(
            system="You classify public companies. Reply with the requested JSON only.",
            user="Classify NVIDIA: its ticker, its GICS sector, and your confidence 0-100.",
            output_model=_Probe,
            model=model,
            max_tokens=200,
        )
    except Exception as e:  # noqa: BLE001 — report every failure mode
        print(f"FAIL {model}: {type(e).__name__}: {e}")
        return False
    print(f"OK   {model}: {out.model_dump()}")
    return True


async def main() -> int:
    results = await asyncio.gather(_probe(HAIKU), _probe(SONNET))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
