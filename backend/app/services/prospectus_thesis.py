"""Final synthesis step — single Sonnet pass over all category outputs."""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.graph.llm import SONNET, complete
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    ProspectusThesisOutput,
)

logger = logging.getLogger(__name__)

THESIS_SYSTEM = """You are a buy-side analyst writing a one-page thesis on a company that has just filed its S-1.

Your inputs are the seven per-category analyses produced earlier in the pipeline, plus the extracted historical financials.

Output ONE JSON object matching this schema — no prose outside the JSON, no markdown fences:

{
  "thesis_statement": "<2-4 sentence thesis>",
  "key_risks": [
    {"risk": "<short label>", "severity": "low|medium|high", "category_source": "<which category surfaced it>"}
  ],
  "ipo_verdict": "participate" | "watch_post_lockup" | "pass",
  "price_range_commentary": "<one paragraph if the S-1 has set a range, else null>",
  "post_ipo_research_plan": [
    {
      "question": "<question to revisit once the company is public>",
      "why_it_matters": "<one sentence>",
      "expected_data_source": "<FMP / transcript / Form 4 / 10-Q / etc.>"
    }
  ]
}

Constraints:
- 3-7 key_risks, sorted by severity (high first).
- 5+ post_ipo_research_plan items. These are the watchlist for re-evaluation post-IPO.
- Verdict rubric:
   participate = thesis works, risks understood, valuation tolerable
   watch_post_lockup = thesis is plausible but you want to see how the float trades and the first earnings print
   pass = something disqualifying — bad governance, broken unit economics, or the deal mechanics are hostile
"""


def _categories_to_prompt_block(categories: CategoriesStepOutput) -> str:
    parts: list[str] = []
    for cat, res in categories.results.items():
        parts.append(
            f"### {cat} (score: {res.score}/100)\n\n"
            f"Key findings:\n" + "\n".join(f"- {kf}" for kf in res.key_findings) + "\n\n"
            f"Analysis:\n{res.content}"
        )
    if categories.failures:
        parts.append("### Category failures (these did not run)")
        for cat, err in categories.failures.items():
            parts.append(f"- {cat}: {err}")
    return "\n\n".join(parts)


async def synthesize_thesis(
    *,
    issuer_name: str,
    categories: CategoriesStepOutput,
    financials_json: dict[str, Any],
) -> ProspectusThesisOutput:
    user = (
        f"Issuer: {issuer_name}\n\n"
        f"## Extracted Financials (JSON)\n\n```json\n{json.dumps(financials_json, indent=2)}\n```\n\n"
        f"## Per-Category Analyses\n\n{_categories_to_prompt_block(categories)}\n\n"
        f"Produce the JSON thesis now."
    )
    raw = await complete(
        system=THESIS_SYSTEM,
        user=user,
        model=SONNET,
        max_tokens=4096,
        assistant_prefill='{"thesis_statement":',
    )
    candidate = raw if raw.lstrip().startswith("{") else '{"thesis_statement":' + raw
    payload = json.loads(candidate)
    return ProspectusThesisOutput.model_validate(payload)
