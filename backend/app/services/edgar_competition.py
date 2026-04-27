"""Extract structured Competition disclosure from a 10-K's Item 1 Business
section using Haiku. Persists per-segment narrative + per-(segment, area)
competitor lists into filing_segments and competitor_landscape.

Idempotent on `filing_sections.competition_extracted_at`. Re-runs are no-ops
unless `force=True`.
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
