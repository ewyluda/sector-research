"""Pre-earnings brief — lazy Haiku synthesis of "what to watch."

Distills thesis pillars + signposts + consensus into 3-5 bullets of what
would confirm vs threaten the thesis if the print delivers/misses.
Not persisted — re-rendered on demand.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import HAIKU, complete
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun

logger = logging.getLogger(__name__)


class BriefOutput(BaseModel):
    summary_md: str = Field(..., description="3-5 markdown bullets")
    pillars_addressed: list[str] = Field(default_factory=list)


EARNINGS_BRIEF_SYSTEM = """You are an equity analyst preparing a pre-earnings checklist for a specific investment thesis.

Inputs you will receive:
- thesis_summary: the high-level thesis statement
- thesis_pillars: the 3-5 named pillars the thesis depends on
- signposts: verbatim signposts from the thesis catalyst, if any
- consensus: analyst-expected EPS and revenue for the upcoming quarter
- recent_trend: last 4 quarters of beat/miss/inline outcomes

Task: produce a 3-5 bullet markdown checklist of what to watch in the
upcoming print. Each bullet should:
- Start with a metric or signpost name (e.g., "**Cloud revenue YoY:**").
- State what would confirm vs threaten the thesis at that line item.
- Be specific (e.g., "above 25% YoY" rather than "strong growth").

Constraints:
- Reason about the print itself only — no broader macro, no buy/sell.
- Do not invent numbers the consensus did not provide.
- If the thesis has fewer than 3 testable pillars, produce 3 bullets and
  note where you had to broaden the question.

Return strict JSON matching the schema. The "pillars_addressed" field
must be a subset of the input thesis_pillars names."""


def _extract_thesis(run: ResearchRun) -> tuple[str | None, list[str]]:
    """Pull (thesis_summary, thesis_pillars[]) from persisted run state.
    Mirrors the helper in read_through.py but additionally extracts pillars."""
    if not isinstance(run.state, dict):
        return None, []
    phase_outputs = run.state.get("phase_outputs") or {}
    thesis = phase_outputs.get("thesis") or {}
    structured = thesis.get("structured") if isinstance(thesis, dict) else None
    if not isinstance(structured, dict):
        return None, []
    summary = structured.get("thesis_summary")
    pillars_raw = structured.get("thesis_pillars") or structured.get("pillars") or []
    pillars: list[str] = []
    if isinstance(pillars_raw, list):
        for p in pillars_raw:
            if isinstance(p, str):
                pillars.append(p)
            elif isinstance(p, dict) and isinstance(p.get("name"), str):
                pillars.append(p["name"])
    return summary, pillars


async def compute_brief(
    run_id: str,
    earnings_print_id: str,
    db: AsyncSession,
) -> BriefOutput:
    """Lazy Haiku call. Raises ValueError if thesis_summary is missing
    or run/print rows are not found."""
    run = await db.get(ResearchRun, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    print_row = await db.get(EarningsPrint, earnings_print_id)
    if print_row is None:
        raise ValueError(f"earnings print not found: {earnings_print_id}")

    thesis_summary, thesis_pillars = _extract_thesis(run)
    if not thesis_summary:
        raise ValueError(f"no thesis_summary in run state: {run_id}")

    cat_q = (
        select(Catalyst)
        .where(Catalyst.run_id == run_id)
        .where(Catalyst.type == "earnings")
        .order_by(Catalyst.ordinal)
    )
    cat_rows = (await db.execute(cat_q)).scalars().all()
    signposts: list[str] = []
    for c in cat_rows:
        if isinstance(c.signposts, list):
            signposts.extend(s for s in c.signposts if isinstance(s, str))

    user_payload: dict[str, Any] = {
        "thesis_summary": thesis_summary,
        "thesis_pillars": thesis_pillars,
        "signposts": signposts[:10],
        "consensus": {
            "eps_estimated": print_row.eps_estimated,
            "revenue_estimated": print_row.revenue_estimated,
            "earnings_date": print_row.earnings_date.isoformat(),
            "fiscal_year": print_row.fiscal_year,
            "fiscal_quarter": print_row.fiscal_quarter,
        },
    }

    raw = await complete(
        model=HAIKU,
        system=EARNINGS_BRIEF_SYSTEM,
        user=json.dumps(user_payload, indent=2),
        assistant_prefill='{"summary_md":',
        max_tokens=800,
    )
    full_json = '{"summary_md":' + raw
    try:
        parsed = BriefOutput.model_validate_json(full_json)
    except Exception as e:
        logger.exception("BriefOutput parse failed: raw=%s", raw[:300])
        raise ValueError(f"brief parse failed: {e}") from e
    return parsed
