"""VerdictOutcome, VerdictReturnSnapshot, SectorEtfMapping — alpha feedback-loop tracking.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md for context.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base


class SectorEtfMapping(Base):
    __tablename__ = "sector_etf_mapping"

    fmp_sector: Mapped[str] = mapped_column(String(64), primary_key=True)
    etf_ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class VerdictOutcome(Base):
    __tablename__ = "verdict_outcomes"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_verdict_outcomes_source"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'research_run' | 'workspace_run'
    source_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict_emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    entry_price_at: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    entry_price_source: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="fmp_historical_eod_adjusted"
    )

    spy_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    sector_etf_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sector_etf_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_entry_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_constituents: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)

    signal_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_outcome_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="SET NULL"),
        nullable=True,
    )
    realized_ticker_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_spy_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_sector_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    realized_theme_basket_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    snapshots: Mapped[list["VerdictReturnSnapshot"]] = relationship(
        "VerdictReturnSnapshot",
        back_populates="outcome",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class VerdictReturnSnapshot(Base):
    __tablename__ = "verdict_return_snapshots"
    __table_args__ = (
        UniqueConstraint("outcome_id", "snapshot_offset", name="uq_snapshot_outcome_offset"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4()))
    outcome_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_offset: Mapped[str] = mapped_column(String(8), nullable=False)  # '1d'|'1w'|'1m'|'3m'|'6m'
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    ticker_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    spy_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    sector_etf_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    theme_basket_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    ticker_return_pct: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    spy_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    sector_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    theme_basket_excess_pct: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    outcome: Mapped["VerdictOutcome"] = relationship("VerdictOutcome", back_populates="snapshots")
