"""Pydantic schemas for transcript delta analysis."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AxisDirection = Literal["softening", "strengthening", "stable"]
AxisMagnitude = Literal["minor", "material", "regime_change"]

CATEGORY_KEYS: tuple[str, ...] = (
    "business_quality",
    "risk_assessment",
    "growth_earnings",
    "sentiment_narrative",
    "management_governance",
    "future_durability",
    "macro_regime",
    "financial_health",
    "valuation_stage",
)


class QuoteRef(BaseModel):
    year: int = Field(ge=2000, le=2100)
    quarter: int = Field(ge=1, le=4)
    role: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=300)


class AxisDelta(BaseModel):
    direction: AxisDirection
    magnitude: AxisMagnitude
    summary: str = Field(min_length=1, max_length=600)
    quotes: list[QuoteRef] = Field(default_factory=list, max_length=3)


class AxesDelta(BaseModel):
    business_quality: AxisDelta | None = None
    risk_assessment: AxisDelta | None = None
    growth_earnings: AxisDelta | None = None
    sentiment_narrative: AxisDelta | None = None
    management_governance: AxisDelta | None = None
    future_durability: AxisDelta | None = None
    macro_regime: AxisDelta | None = None
    financial_health: AxisDelta | None = None
    valuation_stage: AxisDelta | None = None


class TranscriptWindowEntry(BaseModel):
    year: int
    quarter: int


class TranscriptDeltaRead(BaseModel):
    id: str
    ticker: str
    transcripts_window: list[TranscriptWindowEntry]
    axes: AxesDelta
    computed_at: datetime
