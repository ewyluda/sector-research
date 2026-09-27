"""Extract embedded financial figures from S-1 narrative.

S-1s present multi-year financials in three places:
  * Selected Financial Data table (usually right before MD&A)
  * MD&A's "Results of Operations" subsection
  * Consolidated statements at the back

We send Sonnet the MD&A text + any explicitly-collected Selected
Financial Data block and ask for a small, named-key-per-period schema.
A missing year is an explicit null, not a corrupted row.
"""
from __future__ import annotations

import logging


from backend.app.graph.llm import DEEP_MODEL, complete_structured
from backend.app.models.prospectus_schemas import ProspectusFinancials

logger = logging.getLogger(__name__)

CHAR_BUDGET = 25_000

_SYSTEM = """You extract historical financial figures from S-1 / S-1/A prospectus narrative and tables.

Rules:
- Output ONLY valid JSON matching the schema below — no commentary, no markdown fences.
- Currency is whatever the filing reports (dollars, thousands, millions — convert to raw dollars in the output).
- For any field you cannot find with confidence, use null. Do NOT guess.
- `source_snippet` is a verbatim 1-2 sentence quote from the text supporting the row.
- Include up to 3 most-recent annual periods and up to 2 most-recent interim periods.

Schema:
{
  "annual": [
    {
      "period_label": "FY2024",
      "revenue": 14000000000.0,
      "cost_of_revenue": 9000000000.0,
      "operating_income": 2000000000.0,
      "net_income": 1500000000.0,
      "cash_and_equivalents": 4000000000.0,
      "total_debt": 1000000000.0,
      "source_snippet": "Revenues for the year ended December 31, 2024 were $14.0 billion"
    }
  ],
  "interim": [
    {
      "period_label": "Six months ended Jun 30, 2025",
      "revenue": 8000000000.0,
      "operating_income": 1200000000.0,
      "net_income": 900000000.0,
      "source_snippet": "Revenues for the six months ended June 30, 2025 were $8.0 billion"
    }
  ]
}
"""


async def extract_financials(*, mda_text: str, selected_financials_text: str) -> ProspectusFinancials:
    """Return a ProspectusFinancials. Empty when inputs are empty or Sonnet
    returns un-parseable output (caller decides whether that's a soft fail)."""
    body = (selected_financials_text + "\n\n" + mda_text).strip()
    if not body:
        return ProspectusFinancials()

    user = f"Extract financials from the following prospectus narrative.\n\n---\n{body[:CHAR_BUDGET]}\n---"

    try:
        return await complete_structured(
            system=_SYSTEM,
            user=user,
            output_model=ProspectusFinancials,
            model=DEEP_MODEL,
            max_tokens=4096,
        )
    except Exception as e:
        logger.warning("prospectus financials Sonnet call failed: %s", e)
        return ProspectusFinancials()
