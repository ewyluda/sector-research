"""JournalTrade — manual entry/exit trade log linked to verdict_outcomes.

One row = one entry + one exit; scaling in/out = multiple rows. A null
exit_date means the trade is open (no status column — derived).
See docs/superpowers/specs/2026-06-10-trade-journal-design.md.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin
from backend.app.models.outcome import VerdictOutcome


class JournalTrade(TimestampMixin, Base):
    __tablename__ = "journal_trades"
    __table_args__ = (
        # open-trades list is the hot read path
        Index(
            "ix_journal_trades_open_ticker",
            "ticker",
            postgresql_where=text("exit_date IS NULL"),
        ),
        Index("ix_journal_trades_outcome_id", "outcome_id"),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default="long"
    )  # 'long' | 'short'

    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    entry_price_source: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # 'manual' | 'fmp_eod_adjusted'

    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    exit_price_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    spy_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    spy_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)

    outcome_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("verdict_outcomes.id", ondelete="SET NULL"),
        nullable=True,
    )

    entry_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exit_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    outcome: Mapped[VerdictOutcome | None] = relationship("VerdictOutcome")
