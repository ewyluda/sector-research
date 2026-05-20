"""Pydantic schemas for ProspectusReport.step_outputs entries.

One schema per step. All shapes are JSON-serialisable and round-trip
through model_validate / model_dump unchanged so they can be persisted
into and rehydrated from the `prospectus_reports.step_outputs` JSONB
column without custom encoders.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Step 1 — ingest ──────────────────────────────────────────────────────────


class ExtractedSectionSummary(BaseModel):
    """One row per filing section extracted from the S-1."""
    section_key: str
    heading: str
    char_count: int


class AnnualFinancialRow(BaseModel):
    period_label: str = Field(..., description="e.g. 'FY2024' or 'Year ended Dec 31, 2024'")
    revenue: float | None = None
    cost_of_revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    cash_and_equivalents: float | None = None
    total_debt: float | None = None
    source_snippet: str = Field(..., description="Verbatim sentence(s) from the S-1 supporting these figures.")


class InterimFinancialRow(BaseModel):
    period_label: str = Field(..., description="e.g. 'Six months ended Jun 30, 2025'")
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    source_snippet: str


class ProspectusFinancials(BaseModel):
    annual: list[AnnualFinancialRow] = Field(default_factory=list)
    interim: list[InterimFinancialRow] = Field(default_factory=list)


class IngestStepOutput(BaseModel):
    accession_number: str
    primary_document_url: str
    issuer_cik: str
    issuer_name: str
    proposed_ticker: str | None = None
    form_type: str
    sections: list[ExtractedSectionSummary]
    financials: ProspectusFinancials


# ── Step 2 — relationships ───────────────────────────────────────────────────


class RelationshipSummary(BaseModel):
    counterparty_name: str
    relationship_type: str
    magnitude_pct: float | None = None
    resolved_to_ticker: str | None = None
    verbatim_quote: str


class RelationshipsStepOutput(BaseModel):
    edges_extracted: int
    edges_resolved: int
    edges: list[RelationshipSummary]


# ── Step 3 — categories ──────────────────────────────────────────────────────


class ProspectusCategoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    content: str
    score: int = Field(..., ge=0, le=100)
    key_findings: list[str] = Field(default_factory=list)


class CategoriesStepOutput(BaseModel):
    results: dict[str, ProspectusCategoryResult]
    failures: dict[str, str] = Field(default_factory=dict)


# ── Step 4 — thesis ──────────────────────────────────────────────────────────


class IPOVerdict(str, Enum):
    PARTICIPATE = "participate"
    WATCH_POST_LOCKUP = "watch_post_lockup"
    PASS = "pass"


class KeyRisk(BaseModel):
    risk: str
    severity: Literal["low", "medium", "high"]
    category_source: str


class PostIPOPlanItem(BaseModel):
    question: str
    why_it_matters: str
    expected_data_source: str


class ProspectusThesisOutput(BaseModel):
    thesis_statement: str
    key_risks: list[KeyRisk]
    ipo_verdict: IPOVerdict
    price_range_commentary: str | None = None
    post_ipo_research_plan: list[PostIPOPlanItem]
