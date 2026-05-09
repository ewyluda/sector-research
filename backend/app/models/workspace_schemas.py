"""Pydantic models for workspace step output schemas.

This module defines the output shapes for each of the 5 workspace loop steps.
These schemas serve dual duty:
1. Pydantic validation at step completion
2. JSONB serialization into workspace_runs.step_outputs
3. Wire format for frontend consumption via GET /api/workspaces/{run_id}

Each step's Output model is a top-level export; nested types (cells, citations, etc.)
are nested within the appropriate Output class.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Workspace Verdict Enum ────────────────────────────────────────────────────

class WorkspaceVerdict(str, Enum):
    """Workspace-level confidence verdict on the thesis."""

    HEALTHY = "healthy"
    IMMINENT = "imminent"
    TRIGGERED = "triggered"
    BROKEN = "broken"


# ── Step 1: Update/Refresh ────────────────────────────────────────────────────

class ChangedCell(BaseModel):
    """A single model cell that changed after refresh."""

    cell_path: str = Field(
        description="Path to the cell: e.g. 'income_statement.revenue.2026Q1' "
        "or 'assumptions.discount_rate' or 'drivers.2026Q1.revenue_growth'"
    )
    prior_value: float | None = Field(description="Value before the update.")
    new_value: float | None = Field(description="Value after the update.")
    source: str = Field(
        description="Source of the new value: "
        "'historical' | 'ai_baseline' | 'driver' | 'formula' | 'override'"
    )
    citation_id: str | None = Field(
        default=None,
        description="Optional link to the data source (filing, estimate, etc.).",
    )


class FilingRef(BaseModel):
    """Reference to a newly-fetched SEC filing."""

    form: str = Field(description="Filing type: '10-Q' | '10-K' | 'DEF 14A'")
    accession: str = Field(description="SEC accession number.")
    fetched_at: str = Field(description="ISO 8601 timestamp when fetched.")


class EstimateDelta(BaseModel):
    """Consensus estimate change for a single metric."""

    metric: str = Field(
        description="Metric name: 'revenue' | 'eps' | 'ebitda' etc."
    )
    period: str = Field(description="Period: '2026Q2' | '2027' etc.")
    prior_consensus: float | None = Field(
        description="Prior consensus value, if known."
    )
    new_consensus: float | None = Field(description="New consensus value.")
    delta_pct: float | None = Field(description="Percent change.")


class UpdateRefreshOutput(BaseModel):
    """Step 1 output: model refresh and consensus updates."""

    version_before: int = Field(
        description="Base model version before the step."
    )
    version_after: int | None = Field(
        default=None,
        description="New version after save, or null if refresh failed.",
    )
    changed_cells: list[ChangedCell] = Field(
        default_factory=list, description="Cells that changed during refresh."
    )
    new_filings: list[FilingRef] = Field(
        default_factory=list, description="Newly-fetched SEC filings."
    )
    consensus_delta: list[EstimateDelta] | None = Field(
        default=None, description="Estimate consensus changes, if fetched."
    )
    summary: str = Field(
        description="Human-readable summary of the refresh (e.g., 'loaded latest 10-Q')."
    )


# ── Step 2: Research Triage ───────────────────────────────────────────────────

class Highlight(BaseModel):
    """A single finding or observation from the research triage."""

    text: str = Field(description="The highlight text.")
    classification: Literal[
        "confirms_thesis", "threatens_thesis", "new_unknown"
    ] = Field(
        description="How this finding relates to the thesis."
    )
    citation_id: str | None = Field(
        default=None, description="Optional link to the source."
    )


class OpenQuestionDelta(BaseModel):
    """A new open question from research or a resolved prior question."""

    question: str = Field(description="The question text.")
    surfaced_by: str = Field(
        description="workspace_run_id that surfaced or resolved this question."
    )
    classification: str = Field(
        description="E.g., 'newly_surfaced' | 'resolved' etc."
    )


class ResearchOutput(BaseModel):
    """Step 2 output: research-driven thesis updates."""

    highlights: list[Highlight] = Field(
        default_factory=list, description="Key research findings."
    )
    new_open_questions: list[OpenQuestionDelta] = Field(
        default_factory=list,
        description="Questions surfaced or resolved in this step.",
    )
    summary: str = Field(description="Synthesis of research implications.")


# ── Step 3: Validation/Sensitivity (Reverse-DCF) ──────────────────────────────

class ImpliedDriver(BaseModel):
    """A single dimension solved via reverse-DCF."""

    dimension: str = Field(
        description="Driver name: 'revenue_growth' | 'operating_margin' | "
        "'terminal_multiple' etc."
    )
    implied_value: float = Field(description="Solved value.")
    baseline_value: float = Field(description="Baseline forecast value.")


class SensitivityGrid(BaseModel):
    """A 2D sensitivity matrix for two dimensions."""

    dim_x: str = Field(description="X-axis dimension name.")
    dim_y: str = Field(description="Y-axis dimension name.")
    x_axis: list[float] = Field(description="X-axis values (21 ticks).")
    y_axis: list[float] = Field(description="Y-axis values (21 ticks).")
    values: list[list[float]] = Field(
        description="2D matrix of results (21x21)."
    )


class ThesisVsPriced(BaseModel):
    """Single point of thesis-vs.-priced-in comparison."""

    metric: str = Field(description="Metric name (e.g., 'revenue_cagr').")
    thesis_value: float = Field(description="Thesis forecast value.")
    priced_in_value: float = Field(
        description="Value implied by current price."
    )
    delta_pct: float = Field(description="Percent difference.")


class ValidationOutput(BaseModel):
    """Step 3 output: reverse-DCF sensitivity and thesis validation."""

    implied_drivers: list[ImpliedDriver] = Field(
        default_factory=list,
        description="Drivers backed out from current price.",
    )
    implied_irr: float | None = Field(
        default=None, description="IRR implied by current price."
    )
    sensitivity_grids: list[SensitivityGrid] = Field(
        default_factory=list,
        description="Up to 3 sensitivity matrices.",
    )
    thesis_vs_priced_in: list[ThesisVsPriced] = Field(
        default_factory=list,
        description="Thesis assumptions vs. what price implies.",
    )
    current_price: float = Field(description="Stock price at time of calc.")
    citation_ids: list[str] = Field(
        default_factory=list, description="Links to data sources."
    )


# ── Step 4: Challenge & Stress-Test ────────────────────────────────────────

class KillCriterionWrite(BaseModel):
    """A kill criterion status update from challenge evaluation."""

    ordinal: int = Field(description="Sequential ordinal (1-based).")
    status: Literal["armed", "triggered", "resolved"] = Field(
        description="Current kill criterion status."
    )
    note: str | None = Field(
        default=None, description="Optional context or observation."
    )


class CatalystUpdate(BaseModel):
    """A catalyst event status update."""

    catalyst_id: str = Field(description="Catalyst identifier.")
    new_status: Literal["still_pending", "resolved", "missed"] = Field(
        description="Current status."
    )
    note: str | None = Field(
        default=None, description="Optional context."
    )


class ChallengeOutput(BaseModel):
    """Step 4 output: thesis challenge and stress-test."""

    stress_test_summary: str = Field(
        description="Summary of stress-test findings."
    )
    kill_criterion_writes: list[KillCriterionWrite] = Field(
        default_factory=list,
        description="Updates to kill criteria status.",
    )
    catalyst_updates: list[CatalystUpdate] = Field(
        default_factory=list,
        description="Updates to catalyst status.",
    )
    proposed_verdict: WorkspaceVerdict = Field(
        description="Recommended workspace verdict after challenge."
    )


# ── Step 5: Differentiation (Peer Comp + Read-Throughs) ──────────────────────

class PeerCompRow(BaseModel):
    """A single row in the peer comparison table."""

    ticker: str = Field(
        description="The peer ticker (or focus ticker for the highlighted row)."
    )
    pe: float | None = Field(default=None, description="Price-to-earnings.")
    ev_ebitda: float | None = Field(default=None, description="EV/EBITDA.")
    p_b: float | None = Field(default=None, description="Price-to-book.")
    p_fcf: float | None = Field(default=None, description="Price-to-FCF.")
    p_s: float | None = Field(default=None, description="Price-to-sales.")
    roe: float | None = Field(default=None, description="Return on equity.")
    revenue_yoy: float | None = Field(
        default=None, description="Revenue YoY growth %."
    )
    eps_yoy: float | None = Field(
        default=None, description="EPS YoY growth %."
    )
    gross_margin: float | None = Field(
        default=None, description="Gross margin %."
    )
    ebitda_margin: float | None = Field(
        default=None, description="EBITDA margin %."
    )


class PeerCompTable(BaseModel):
    """The full peer comparison table."""

    focus_ticker: str = Field(description="Focus company ticker.")
    rows: list[PeerCompRow] = Field(
        default_factory=list, description="Peer rows (focus row first)."
    )
    median: PeerCompRow = Field(
        description="Computed peer median (focus excluded)."
    )
    delta_vs_median_pct: PeerCompRow = Field(
        description="Focus row deltas vs. median (all metrics in %)."
    )


class PeerError(BaseModel):
    """Error during peer resolution or data fetch."""

    peer_ticker: str = Field(description="Peer ticker that failed.")
    error_message: str = Field(description="Error detail.")


class DifferentiationOutput(BaseModel):
    """Step 5 output: peer differentiation and strategic positioning."""

    peer_comp: PeerCompTable | None = Field(
        default=None,
        description="Peer comparison table, or null if no peers resolved.",
    )
    read_throughs: list[dict] = Field(
        default_factory=list,
        description="Serialized read-through items (rich-text / structured format TBD).",
    )
    per_peer_errors: list[PeerError] = Field(
        default_factory=list,
        description="Errors encountered during peer resolution or data fetch.",
    )
