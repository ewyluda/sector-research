"""Pydantic schemas for the trade-journal public API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.models.outcome_schemas import SnapshotOffset, SourceType

Direction = Literal["long", "short"]
ExitReason = Literal[
    "thesis_played_out", "kill_criterion", "stop_loss",
    "better_opportunity", "rebalance", "mistake", "other",
]
TradeStatusFilter = Literal["open", "closed", "all"]


class TradeCreate(BaseModel):
    ticker: str
    entry_date: date
    entry_price: Decimal | None = Field(default=None, gt=0)  # None -> auto-fill
    quantity: Decimal | None = Field(default=None, gt=0)
    direction: Direction = "long"
    outcome_id: str | None = None
    entry_rationale: str | None = None


class TradeUpdate(BaseModel):
    """All fields optional; absent-vs-null distinguished via
    model_dump(exclude_unset=True). Explicit exit_date=None reopens."""
    entry_date: date | None = None
    entry_price: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal | None = Field(default=None, gt=0)
    direction: Direction | None = None
    outcome_id: str | None = None
    entry_rationale: str | None = None
    exit_date: date | None = None
    exit_price: Decimal | None = Field(default=None, gt=0)
    exit_reason: ExitReason | None = None
    exit_note: str | None = None


class TradeReturnsRead(BaseModel):
    return_pct: Decimal | None
    spy_excess_pct: Decimal | None
    holding_days: int | None
    unrealized: bool


class DecisionComparisonRead(BaseModel):
    offset: SnapshotOffset
    trade_return_pct: Decimal
    trade_spy_excess_pct: Decimal | None
    paper_return_pct: Decimal
    paper_spy_excess_pct: Decimal | None
    execution_delta_pct: Decimal | None


class LinkedOutcomeSummary(BaseModel):
    id: str
    verdict: str
    source_type: SourceType
    source_id: str
    theme_id: str | None
    verdict_emitted_at: datetime
    entry_price_at: date
    realized_spy_excess_pct: Decimal | None


class TradeDetail(BaseModel):
    id: str
    ticker: str
    direction: Direction
    status: Literal["open", "closed"]
    entry_date: date
    entry_price: Decimal
    entry_price_source: str
    exit_date: date | None
    exit_price: Decimal | None
    exit_price_source: str | None
    quantity: Decimal | None
    spy_entry_price: Decimal | None
    spy_exit_price: Decimal | None
    outcome_id: str | None
    entry_rationale: str | None
    exit_reason: ExitReason | None
    exit_note: str | None
    returns: TradeReturnsRead | None
    linked_outcome: LinkedOutcomeSummary | None
    comparison: DecisionComparisonRead | None
    created_at: datetime


class ExitReasonStat(BaseModel):
    exit_reason: str
    count: int
    avg_return_pct: Decimal | None
    avg_spy_excess_pct: Decimal | None


class ExecutionVsPaper(BaseModel):
    n: int
    avg_delta_pct: Decimal | None


class CoverageStat(BaseModel):
    outcomes_traded: int
    outcomes_total: int


class JournalSummary(BaseModel):
    trade_count: int
    open_count: int
    closed_count: int
    hit_rate: float | None
    excess_basis_count: int
    avg_return_pct: Decimal | None
    median_return_pct: Decimal | None
    avg_spy_excess_pct: Decimal | None
    avg_holding_days: float | None
    execution_vs_paper: ExecutionVsPaper
    by_exit_reason: list[ExitReasonStat]
    coverage: CoverageStat


class PricePreview(BaseModel):
    price: Decimal
    price_date: date  # may be earlier than requested (weekend/holiday)
    source: str


class LinkCandidate(BaseModel):
    id: str
    verdict: str
    source_type: SourceType
    theme_id: str | None
    verdict_emitted_at: datetime
    entry_price_at: date
