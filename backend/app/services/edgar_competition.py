"""Extract structured Competition disclosure from a 10-K's Item 1 Business
section using Haiku. Persists per-segment narrative + per-(segment, area)
competitor lists into filing_segments and competitor_landscape.

Idempotent on `filing_sections.competition_extracted_at`. Successfully parsed
runs are no-ops unless `force=True`; failed calls remain retryable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import HAIKU, complete
from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.filing import (
    CompetitorLandscape,
    Filing,
    FilingSection,
    FilingSegment,
)
from backend.app.services.counterparty_resolver import normalize_name

logger = logging.getLogger(__name__)

# Item 1 averages 30–60K chars; the Competition subsection is reliably in
# the first half. 25K covers IIVI's 2-page table with headroom.
SECTION_CHAR_BUDGET = 25_000

ITEM_1_KEY = "item_1_business"


# ── Pydantic schemas (LLM output contract) ────────────────────────────────────


class CompetitorRef(BaseModel):
    name: str = Field(
        ...,
        description="Exact casing from the filing.",
    )
    magnitude_pct: float | None = Field(
        default=None,
        description=(
            "Percentage when disclosed (rare in competition tables). Null otherwise."
        ),
    )
    verbatim_quote: str | None = Field(
        default=None,
        description=(
            "Optional anchoring sentence from the filing (≤200 chars)."
        ),
    )


class CompetitionArea(BaseModel):
    area_of_competition: str = Field(
        ...,
        description=(
            "Left-column text from the competition table — e.g. "
            "'Optical components, modules, and subsystems for optical communications'."
        ),
    )
    competitors: list[CompetitorRef] = Field(default_factory=list)


class CompetitionSegment(BaseModel):
    segment_name: str = Field(
        ...,
        description=(
            "Segment name as the filer uses it. Use 'Overall' for "
            "single-segment companies that don't name a segment."
        ),
    )
    narrative: str = Field(
        ...,
        description=(
            "2–3 sentences on segment scope, end markets, and growth "
            "direction. From Item 1 text only — do not invent numbers."
        ),
    )
    areas: list[CompetitionArea] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    segments: list[CompetitionSegment] = Field(default_factory=list)


# ── Summary returned to API callers ──────────────────────────────────────────


@dataclass
class ExtractionSummary:
    ticker: str
    filing_id: str | None
    segments_extracted: int = 0
    areas_extracted: int = 0
    competitors_extracted: int = 0
    skipped: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "filing_id": self.filing_id,
            "segments_extracted": self.segments_extracted,
            "areas_extracted": self.areas_extracted,
            "competitors_extracted": self.competitors_extracted,
            "skipped": self.skipped,
            "errors": list(self.errors),
        }


# ── Prompts ──────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """You extract the Competition disclosure from Item 1 of a 10-K filing.

Most filers structure this as a table:
  Segment → Areas of Competition → list of named Competitors.

Some filers (single-segment businesses) describe competition as a paragraph
without a segment header. In that case use segment_name="Overall".

Rules:
- Capture every Segment, every Area of Competition, and every named Competitor as written in the filing.
- Use the EXACT casing from the text for company names. Don't normalize.
- Do NOT infer competitors from background knowledge. Only extract entities the filer explicitly names.
- Skip generic language ("we face competition from numerous companies"); only extract when the filer names competitors OR names a competitive arena (an "area of competition") with at least one named competitor.
- For each segment, write a 2–3 sentence `narrative` summarizing segment scope, end markets, and growth direction. Pull cues from the same Item 1 text — DO NOT invent numbers or revenue figures.
- If the filing discloses no structured competition, return an empty `segments` array.

Output strict JSON matching this schema:
{
  "segments": [
    {
      "segment_name": "string (or 'Overall' for single-segment filers)",
      "narrative": "2-3 sentences from Item 1 text",
      "areas": [
        {
          "area_of_competition": "left-column text",
          "competitors": [
            {
              "name": "Exact Company Name Inc.",
              "magnitude_pct": number | null,
              "verbatim_quote": "optional anchor sentence ≤200 chars"
            }
          ]
        }
      ]
    }
  ]
}"""

_USER_TEMPLATE = """Ticker: {ticker}
Filing: {form_type} filed {filing_date}
Section: {section_key} ({heading})

Section text (truncated to {budget} chars):
\"\"\"
{text}
\"\"\"

Extract the Competition disclosure as the JSON object described in the system prompt."""


# ── Extraction ────────────────────────────────────────────────────────────────


async def _call_haiku_on_item_1(
    ticker: str,
    form_type: str,
    filing_date: str,
    section_key: str,
    heading: str | None,
    text: str,
) -> tuple[ExtractionResult | None, str | None]:
    """Run one Haiku extraction pass. Returns (result, error_str).

    On any failure returns (None, error_str) so callers can surface the error
    without aborting. Failures are intentionally retryable.
    """
    truncated = text[:SECTION_CHAR_BUDGET]
    prompt = _USER_TEMPLATE.format(
        ticker=ticker.upper(),
        section_key=section_key,
        heading=heading or section_key,
        form_type=form_type,
        filing_date=filing_date,
        budget=SECTION_CHAR_BUDGET,
        text=truncated,
    )
    try:
        raw = await complete(
            system=_SYSTEM_PROMPT,
            user=prompt,
            model=HAIKU,
            max_tokens=4000,
            assistant_prefill='{"segments":',
        )
    except Exception as e:
        logger.warning(
            "Haiku competition call failed for %s: %s", ticker, e,
        )
        return None, f"haiku_call_failed: {e}"

    parsed, err = parse_structured_output(raw, ExtractionResult)
    if parsed is None:
        logger.warning(
            "competition parse failed for %s: %s; raw head: %r",
            ticker, err, raw[:400],
        )
        return None, err or "unknown_parse_error"
    return parsed, None


async def extract_ticker_competition(
    ticker: str,
    db: AsyncSession,
    *,
    force: bool = False,
) -> ExtractionSummary:
    """Extract Competition data for the latest 10-K of `ticker`.

    Steps:
      1. Resolve latest 10-K filing.
      2. Look up its item_1_business filing_section.
      3. If competition_extracted_at is set and not force, return skipped.
      4. Call Haiku, persist filing_segments + competitor_landscape.
      5. Stamp the tombstone after a successful parse (even on zero segments).
      6. Run resolver to back-fill resolved_to_cik / _ticker into JSONB.

    Caller is responsible for `await db.commit()`.
    """
    ticker_upper = ticker.upper()
    summary = ExtractionSummary(ticker=ticker_upper, filing_id=None)

    # Step 1: latest 10-K
    filing = (
        await db.execute(
            select(Filing)
            .where(Filing.ticker == ticker_upper, Filing.form_type == "10-K")
            .order_by(Filing.filing_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if filing is None:
        summary.errors.append(f"no 10-K filed for {ticker_upper}")
        return summary
    summary.filing_id = filing.id

    # Step 2: item_1_business section
    section = (
        await db.execute(
            select(FilingSection).where(
                FilingSection.filing_id == filing.id,
                FilingSection.section_key == ITEM_1_KEY,
            )
        )
    ).scalar_one_or_none()
    if section is None:
        summary.errors.append("item_1_business section not ingested")
        return summary

    # Step 3: idempotency check
    if section.competition_extracted_at is not None and not force:
        summary.skipped = True
        return summary

    # Step 4: call Haiku
    result, err = await _call_haiku_on_item_1(
        ticker=ticker_upper,
        form_type=filing.form_type,
        filing_date=filing.filing_date.isoformat(),
        section_key=section.section_key,
        heading=section.heading,
        text=section.text,
    )

    if err is not None:
        summary.errors.append(err)
        return summary
    assert result is not None  # for type-checker

    # Step 5: stamp tombstone only after a successful parse. Successful
    # zero-segment results are still terminal/idempotent; failures retry.
    section.competition_extracted_at = datetime.utcnow()

    # Step 5a: persist segments + landscape rows. force=True wipes prior rows
    # so we don't accumulate stale segments from earlier extraction runs.
    if force:
        await db.execute(
            FilingSegment.__table__.delete().where(
                FilingSegment.filing_id == filing.id
            )
        )
        await db.execute(
            CompetitorLandscape.__table__.delete().where(
                CompetitorLandscape.filing_id == filing.id
            )
        )

    segment_rows: dict[str, tuple[str, str]] = {}
    landscape_rows: dict[tuple[str, str], dict] = {}

    for seg in result.segments:
        seg_name = " ".join(seg.segment_name.strip().split())[:256] or "Overall"
        seg_key = seg_name.lower()
        narrative = seg.narrative.strip()
        if not narrative:
            continue
        segment_rows.setdefault(seg_key, (seg_name, narrative))

        for area in seg.areas:
            area_text = " ".join(area.area_of_competition.strip().split())
            if not area_text:
                continue
            area_key = area_text.lower()
            row_key = (seg_key, area_key)
            row = landscape_rows.setdefault(
                row_key,
                {
                    "segment_name": seg_name,
                    "area_text": area_text,
                    "competitors": [],
                    "competitor_keys": set(),
                },
            )
            for c in area.competitors:
                name = c.name.strip()[:256]
                if not name:
                    continue
                competitor_key = normalize_name(name) or name.lower()
                if competitor_key in row["competitor_keys"]:
                    continue
                row["competitor_keys"].add(competitor_key)
                row["competitors"].append({
                    "name": name,
                    "name_normalized": normalize_name(name),
                    "magnitude_pct": c.magnitude_pct,
                    "verbatim_quote": (c.verbatim_quote or "").strip()[:1000] or None,
                    "resolved_to_cik": None,
                    "resolved_to_ticker": None,
                })

    for seg_name, narrative in segment_rows.values():
        db.add(FilingSegment(
            filing_id=filing.id,
            ticker=ticker_upper,
            segment_name=seg_name,
            narrative=narrative,
        ))
        summary.segments_extracted += 1

    for row in landscape_rows.values():
        competitors_payload = row["competitors"]
        # Still record empty area rows so the UI can show "named arena" cases
        # where a filer described an area but didn't name competitors.
        summary.competitors_extracted += len(competitors_payload)
        db.add(CompetitorLandscape(
            filing_id=filing.id,
            ticker=ticker_upper,
            segment_name=row["segment_name"],
            area_of_competition=row["area_text"],
            competitors=competitors_payload,
        ))
        summary.areas_extracted += 1

    # Step 6: resolver runs in caller after commit (see API layer). We can't
    # run it here without a second commit — keep the persistence atomic.

    return summary
