"""Pydantic models for structured LLM phase outputs.

This module is the single source of truth for phase output schemas.
Each phase gets one Pydantic model; parsers in graph/output_parser.py
consume them; React components mirror the same shape on the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Quick Screen ──────────────────────────────────────────────────────────────

# Single source of truth for the Quick Screen dimension set.
# Edit this tuple to add / rename / remove dimensions. The Pydantic validator
# AND the prompt template (prompts.QUICK_SCREEN_SYSTEM) both reference this
# constant, so changes propagate automatically.
#
# The frontend is data-driven and iterates whatever `dimensions` array arrives,
# so it needs zero edits when this list changes.
QUICK_SCREEN_DIMENSIONS: tuple[str, ...] = (
    "Business Quality",
    "Financial Health",
    "Growth Trajectory",
    "Valuation",
    "Momentum",
)


class QuickScreenDimension(BaseModel):
    name: str = Field(..., description="Must match one of QUICK_SCREEN_DIMENSIONS exactly")
    score: int = Field(..., ge=0, le=20)
    max_score: int = Field(20, ge=1)
    rationale: str = Field(..., min_length=1, max_length=400)

    @field_validator("name")
    @classmethod
    def name_must_be_known(cls, v: str) -> str:
        if v not in QUICK_SCREEN_DIMENSIONS:
            raise ValueError(
                f"Dimension name {v!r} is not one of {QUICK_SCREEN_DIMENSIONS}"
            )
        return v


class QuickScreenOutput(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    recommendation: Literal["GO", "WATCHLIST", "PASS"]
    dimensions: list[QuickScreenDimension] = Field(..., min_length=5, max_length=5)
    thesis: str = Field(..., min_length=1, max_length=800)
    key_risk: str = Field(..., min_length=1, max_length=800)

    @field_validator("dimensions")
    @classmethod
    def dimensions_must_cover_all(
        cls, v: list[QuickScreenDimension]
    ) -> list[QuickScreenDimension]:
        names_seen = {d.name for d in v}
        missing = set(QUICK_SCREEN_DIMENSIONS) - names_seen
        if missing:
            raise ValueError(f"Missing dimensions: {sorted(missing)}")
        return v


# ── Thesis Construction ──────────────────────────────────────────────────────

class ThesisPoint(BaseModel):
    """A single bull or bear case point with supporting evidence."""
    title: str = Field(..., min_length=1, max_length=140)
    evidence: str = Field(..., min_length=1, max_length=400)


class Catalyst(BaseModel):
    """A catalyst event with a timeframe estimate."""
    timeframe: str = Field(..., min_length=1, max_length=40)
    description: str = Field(..., min_length=1, max_length=240)


class ThesisOutput(BaseModel):
    core_thesis: str = Field(..., min_length=1, max_length=1200)
    bull_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    bear_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    variant_perception: str = Field(..., min_length=1, max_length=600)
    catalysts: list[Catalyst] = Field(..., min_length=3, max_length=5)
    conviction_score: int = Field(..., ge=0, le=100)
    conviction_rationale: str = Field(..., min_length=1, max_length=600)
