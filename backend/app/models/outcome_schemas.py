"""Pydantic schemas for outcome-tracker public API."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


SnapshotOffset = Literal["1d", "1w", "1m", "3m", "6m"]
SourceType = Literal["research_run", "workspace_run"]
Benchmark = Literal["spy", "sector", "theme_basket"]
Window = Literal["30d", "90d", "1y", "all"]


class EntryConstituent(BaseModel):
    ticker: str
    entry_price: Decimal


class EntryPriceBundle(BaseModel):
    """Entry-anchored prices for outcome creation: ticker + SPY + sector ETF + theme constituents."""
    entry_price_at: date
    ticker_price: Decimal
    spy_price: Decimal | None
    sector_etf_ticker: str | None
    sector_etf_price: Decimal | None
    theme_basket_constituents: list[EntryConstituent]


class SignalSnapshot(BaseModel):
    """Shape of the signal_snapshot JSONB. All fields optional — backfill-tolerant.

    Inner types are `Any` for heterogeneous snapshot fields: `signals_row` holds
    full CompanySignalCard sub-dicts (velocity, discovery, narrative, fundamental)
    with nested keys, not scalars. `deep_dive_scores` and `model_assumptions` are
    typed loosely for the same defensiveness — they are write-once snapshots and
    consumers narrow at the read site.
    """
    signals_row: dict[str, Any] | None = None
    deep_dive_scores: dict[str, Any] | None = None
    workspace_step_verdicts: dict[str, str | None] | None = None
    kill_criterion_state: list[dict[str, Any]] | None = None
    model_assumptions: dict[str, Any] | None = None


class SnapshotRead(BaseModel):
    snapshot_offset: SnapshotOffset
    snapshot_date: date
    ticker_price: Decimal
    spy_price: Decimal | None
    sector_etf_price: Decimal | None
    theme_basket_value: Decimal | None
    ticker_return_pct: Decimal
    spy_excess_pct: Decimal | None
    sector_excess_pct: Decimal | None
    theme_basket_excess_pct: Decimal | None


class OutcomeListItem(BaseModel):
    id: str
    source_type: SourceType
    source_id: str
    ticker: str
    theme_id: str | None
    verdict: str
    verdict_emitted_at: datetime
    entry_price_at: date
    entry_price: Decimal
    sector_etf_ticker: str | None
    superseded_at: datetime | None
    closed_at: datetime | None
    realized_ticker_return_pct: Decimal | None
    realized_spy_excess_pct: Decimal | None
    realized_sector_excess_pct: Decimal | None
    realized_theme_basket_excess_pct: Decimal | None
    snapshots: list[SnapshotRead] = Field(default_factory=list)


class OutcomeDetail(OutcomeListItem):
    theme_basket_constituents: list[EntryConstituent] | None
    signal_snapshot: SignalSnapshot | None


class StatGroup(BaseModel):
    n: int
    mean_return_pct: float | None
    mean_excess_pct: float | None
    win_rate: float | None         # fraction in [0, 1]
    median_excess_pct: float | None


class VerdictStats(BaseModel):
    """Per-verdict-band stats. Field set is the known verdict space:
    workspace emits healthy|imminent|triggered|broken; research emits completed|watchlist|pass.
    'passed' aliases 'pass' (Python keyword collision)."""
    healthy: StatGroup | None = None
    imminent: StatGroup | None = None
    triggered: StatGroup | None = None
    broken: StatGroup | None = None
    completed: StatGroup | None = None
    watchlist: StatGroup | None = None
    passed: StatGroup | None = None  # 'pass' is a Python keyword — service maps research_run.status='pass' to this field name


class ThemeStat(BaseModel):
    theme_id: str | None
    theme_name: str | None
    stats: StatGroup


class SignalBucket(BaseModel):
    bucket: str    # '0-25th' | '25-50th' | '50-75th' | '75-100th' | 'null'
    n: int
    mean_excess_pct: float | None
    win_rate: float | None


class OutcomeSummary(BaseModel):
    window: Window
    snapshot_offset: SnapshotOffset
    benchmark: Benchmark
    source_type: SourceType | Literal["all"]
    overall: StatGroup
    by_verdict: VerdictStats
    by_theme: list[ThemeStat]
    by_signal_bucket: dict[str, list[SignalBucket]]  # key = signal name (e.g. 'velocity', 'fundamental', 'discovery')


class RefreshSummary(BaseModel):
    processed: int
    snapshotted: int
    closed: int
    errors: list[dict[str, str]] = Field(default_factory=list)


class BackfillSummary(BaseModel):
    outcomes_created: int
    outcomes_existed: int
    snapshots_inserted: int
    errors: list[dict[str, str]] = Field(default_factory=list)
