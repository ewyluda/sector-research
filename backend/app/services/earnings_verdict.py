"""Post-print thesis verdict — Haiku call against the print's actuals.

Produces a structured `VerdictOutput` ({verdict, summary_md,
pillars_addressed}) per (run_id, earnings_print_id) and persists it.
Idempotent on the unique constraint — re-clicking overwrites with a
fresh call.

Sibling helper `extract_guidance_direction` runs as part of the daily
scheduler when a transcript first becomes available. Separate Haiku call
so the deterministic post-print row (with guidance populated) lands
without waiting on a per-thesis verdict.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.graph.llm import HAIKU, complete
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.research_run import ResearchRun
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.services.earnings_brief import _extract_thesis

logger = logging.getLogger(__name__)

VerdictLiteral = Literal["confirms", "threatens", "neutral", "insufficient"]
GuidanceLiteral = Literal["raised", "maintained", "lowered", "n/a"]


class VerdictOutput(BaseModel):
    verdict: VerdictLiteral
    summary_md: str = Field(..., description="3-5 sentences")
    pillars_addressed: list[str] = Field(default_factory=list)


class GuidanceOutput(BaseModel):
    guidance_direction: GuidanceLiteral
    rationale: str = Field(..., description="One sentence.")


EARNINGS_VERDICT_SYSTEM = """You are an equity analyst evaluating whether an earnings print confirms or threatens an investment thesis.

Inputs you will receive:
- thesis_summary: the high-level thesis statement
- thesis_pillars: the named pillars the thesis depends on
- signposts: verbatim signposts from the thesis catalyst, if any
- actuals: EPS surprise %, revenue surprise %, guidance direction, fiscal period
- transcript_excerpt: optional management commentary, capped ~6K chars

Task: emit a verdict — one of:
- "confirms": the print provides direct evidence supporting one or more
  pillars (a beat alone is not enough; the print must speak to thesis logic).
- "threatens": the print provides direct evidence against one or more
  pillars (a miss alone is not enough; the management commentary or
  guidance must reframe the pillar negatively).
- "neutral": the print spoke to thesis pillars but doesn't move them
  meaningfully in either direction.
- "insufficient": the print is silent on thesis pillars — beat/miss numbers
  alone, no qualitative signal. LEAN HEAVILY toward this verdict when in
  doubt; do not infer from sentiment.

Output:
- verdict: one of the four literals above.
- summary_md: 3-5 sentences explaining the verdict, citing specific
  numbers or transcript phrases. Markdown allowed (paragraphs, bullets,
  bold). Keep it scannable.
- pillars_addressed: subset of input thesis_pillars names that the print
  spoke to (empty list if verdict='insufficient').

Return strict JSON matching the schema. Do NOT recommend buy/sell. Do
NOT speculate beyond the evidence provided."""


GUIDANCE_EXTRACTION_SYSTEM = """You are reading the management commentary section of an earnings call transcript. Your only job is to determine forward guidance direction.

Output one of:
- "raised": management increased forward guidance vs. prior outlook.
- "maintained": management reiterated prior guidance unchanged.
- "lowered": management decreased forward guidance vs. prior outlook.
- "n/a": no forward guidance was given on this call (or company does
  not provide guidance).

If the transcript explicitly references prior guidance and the relationship
to it, use that. If the transcript provides numerical ranges without
explicit comparison to prior, mark "n/a" (you do not have prior guidance
to compare against). Do not infer "raised" from optimistic sentiment alone.

Return strict JSON: {"guidance_direction": "...", "rationale": "..."}.
Rationale is one sentence quoting or paraphrasing the relevant transcript
language."""


async def extract_guidance_direction(
    transcript_text: str,
) -> GuidanceOutput | None:
    """Single Haiku call against a (capped) management commentary excerpt.
    Returns None on parse failure or empty input — caller decides how to
    handle (typically: leave guidance_direction null on the print row)."""
    if not transcript_text or len(transcript_text.strip()) < 200:
        return None

    excerpt = transcript_text[:6000]
    raw = await complete(
        model=HAIKU,
        system=GUIDANCE_EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": excerpt}],
        assistant_prefill='{"guidance_direction":',
        max_tokens=200,
    )
    full_json = '{"guidance_direction":' + raw
    try:
        return GuidanceOutput.model_validate_json(full_json)
    except Exception:
        logger.exception("GuidanceOutput parse failed: raw=%s", raw[:200])
        return None


async def compute_verdict(
    run_id: str,
    earnings_print_id: str,
    fmp: FMPClient,
    db: AsyncSession,
) -> ThesisPrintVerdict:
    """Run Haiku verdict + persist via INSERT ... ON CONFLICT DO UPDATE.
    Caller owns the transaction (commit not called here)."""
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

    transcript_excerpt: str | None = None
    if print_row.transcript_year and print_row.transcript_quarter:
        try:
            data, _ = await fmp.get_earnings_transcript(
                print_row.ticker,
                year=print_row.transcript_year,
                quarter=print_row.transcript_quarter,
            )
            if isinstance(data, list) and data and isinstance(data[0], dict):
                transcript_excerpt = (data[0].get("content") or "")[:6000]
        except Exception as e:
            logger.warning(
                "[%s] verdict transcript fetch failed: %s",
                print_row.ticker, e,
            )

    user_payload: dict[str, Any] = {
        "thesis_summary": thesis_summary,
        "thesis_pillars": thesis_pillars,
        "signposts": signposts[:10],
        "actuals": {
            "fiscal_year": print_row.fiscal_year,
            "fiscal_quarter": print_row.fiscal_quarter,
            "eps_surprise_pct": print_row.eps_surprise_pct,
            "revenue_surprise_pct": print_row.revenue_surprise_pct,
            "guidance_direction": print_row.guidance_direction,
        },
        "transcript_excerpt": transcript_excerpt,
    }

    raw = await complete(
        model=HAIKU,
        system=EARNINGS_VERDICT_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(user_payload, indent=2)}],
        assistant_prefill='{"verdict":',
        max_tokens=900,
    )
    full_json = '{"verdict":' + raw
    try:
        parsed = VerdictOutput.model_validate_json(full_json)
    except Exception as e:
        logger.exception("VerdictOutput parse failed: raw=%s", raw[:300])
        raise ValueError(f"verdict parse failed: {e}") from e

    stmt = pg_insert(ThesisPrintVerdict).values(
        run_id=run_id,
        earnings_print_id=earnings_print_id,
        verdict=parsed.verdict,
        summary_md=parsed.summary_md,
        pillars_addressed=parsed.pillars_addressed,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_thesis_print_verdicts_run_print",
        set_={
            "verdict": stmt.excluded.verdict,
            "summary_md": stmt.excluded.summary_md,
            "pillars_addressed": stmt.excluded.pillars_addressed,
            "generated_at": stmt.excluded.generated_at,
        },
    ).returning(ThesisPrintVerdict.id)
    row_id = (await db.execute(stmt)).scalar_one()
    loaded = await db.get(ThesisPrintVerdict, row_id)
    assert loaded is not None  # ON CONFLICT guarantees a row exists
    return loaded
