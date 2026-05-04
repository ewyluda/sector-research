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
    title: str = Field(..., min_length=1, max_length=300)
    evidence: str = Field(..., min_length=1, max_length=1000)


class Catalyst(BaseModel):
    """A catalyst event with timeframe, type, and watchable signposts."""
    timeframe: str = Field(..., min_length=1, max_length=60)
    description: str = Field(..., min_length=1, max_length=600)
    type: Literal[
        "earnings", "product", "regulatory", "m_and_a", "macro", "other"
    ] | None = None
    signposts: list[str] = Field(default_factory=list, max_length=3)
    linked_pillar: str | None = Field(
        default=None, pattern=r"^(bull|bear):[1-5]$"
    )


class KillCriterion(BaseModel):
    """A falsifiable thesis-killer with an observable trigger."""
    condition: str = Field(..., min_length=1, max_length=300)
    threshold: str = Field(..., min_length=1, max_length=300)
    monitoring_source: str = Field(..., min_length=1, max_length=200)
    kills_pillar: str | None = Field(
        default=None, pattern=r"^(bull|bear):[1-5]$"
    )


class FailureMode(BaseModel):
    """A specific way the thesis could be killed in the next 18 months."""
    mode: str = Field(..., min_length=1, max_length=300)
    leading_indicator: str = Field(..., min_length=1, max_length=300)
    probability: Literal["Low", "Medium", "High"]


class PreMortem(BaseModel):
    """Devil's-advocate analysis: assume the thesis is dead — what killed it?"""
    framing: str = Field(..., min_length=1, max_length=300)
    failure_modes: list[FailureMode] = Field(..., min_length=3, max_length=5)


class ThesisOutput(BaseModel):
    # Sonnet 4.6 is naturally verbose — generous limits to avoid
    # ValidationError rejections on well-formed but wordy output.
    core_thesis: str = Field(..., min_length=1, max_length=4000)
    bull_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    bear_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    variant_perception: str = Field(..., min_length=1, max_length=2000)
    catalysts: list[Catalyst] = Field(..., min_length=3, max_length=5)
    conviction_score: int = Field(..., ge=0, le=100)
    conviction_rationale: str = Field(..., min_length=1, max_length=2000)
    # New (optional for backwards compatibility with old runs):
    kill_criteria: list[KillCriterion] = Field(default_factory=list, max_length=5)
    pre_mortem: PreMortem | None = None


# ── Risk Stress-Test ────────────────────────────────────────────────────────

RISK_PROBABILITY_LEVELS: tuple[str, ...] = ("Low", "Medium", "High")


class RiskEntry(BaseModel):
    """A single risk with probability, impact, and mitigation."""
    risk: str = Field(..., min_length=1, max_length=600)
    category: str = Field(..., min_length=1, max_length=100)
    probability: Literal["Low", "Medium", "High"]
    impact: str = Field(..., min_length=1, max_length=400)
    mitigation: str = Field(..., min_length=1, max_length=600)

    @field_validator("probability")
    @classmethod
    def probability_must_be_valid(cls, v: str) -> str:
        if v not in RISK_PROBABILITY_LEVELS:
            raise ValueError(f"Probability {v!r} not in {RISK_PROBABILITY_LEVELS}")
        return v


class RiskStressTestOutput(BaseModel):
    # Sonnet is verbose — generous limits.
    risks: list[RiskEntry] = Field(..., min_length=3, max_length=7)
    rr_ratio: float = Field(..., ge=0.0, le=50.0)
    rr_verdict: str = Field(..., min_length=1, max_length=2000)
    loop_required: bool
    loop_categories: list[str] = Field(default_factory=list)
    loop_reason: str = Field(default="", max_length=2000)


# ── Position Monitor ───────────────────────────────────────────────────────

class MonitoringItem(BaseModel):
    """A single metric to monitor with its cadence and alert threshold."""
    metric: str = Field(..., min_length=1, max_length=200)
    cadence: str = Field(..., min_length=1, max_length=60)
    threshold: str = Field(..., min_length=1, max_length=300)


class PositionMonitorOutput(BaseModel):
    entry_price_low: str = Field(..., min_length=1, max_length=80)
    entry_price_high: str = Field(..., min_length=1, max_length=80)
    entry_rationale: str = Field(..., min_length=1, max_length=800)
    position_size_pct: float = Field(..., ge=0.0, le=100.0)
    sizing_rationale: str = Field(..., min_length=1, max_length=800)
    add_triggers: list[str] = Field(..., min_length=1, max_length=4)
    stop_loss_level: str = Field(..., min_length=1, max_length=120)
    stop_loss_rationale: str = Field(..., min_length=1, max_length=800)
    invalidation_conditions: list[str] = Field(..., min_length=1, max_length=4)
    monitoring: list[MonitoringItem] = Field(..., min_length=2, max_length=6)
    exit_conditions: list[str] = Field(..., min_length=1, max_length=4)
    time_horizon: str = Field(..., min_length=1, max_length=80)


# ── Deep Dive (shared across all 9 categories) ────────────────────────────

class DeepDiveFinding(BaseModel):
    """A single key finding with supporting evidence."""
    finding: str = Field(..., min_length=1, max_length=400)
    evidence: str = Field(..., min_length=1, max_length=400)


class DeepDiveCategoryOutput(BaseModel):
    score: int = Field(..., ge=0, le=100)
    score_rationale: str = Field(..., min_length=1, max_length=600)
    key_findings: list[DeepDiveFinding] = Field(..., min_length=3, max_length=5)
    analysis: str = Field(..., min_length=1, max_length=5000)
    data_gaps: list[str] = Field(default_factory=list, max_length=3)
