"""InsiderTransaction — one Form 4 transaction line, FMP-sourced.

`natural_key` is a sha256 over the identifying fields (see
services/insider_ingest.py) so daily re-ingests are idempotent without
guessing FMP's uniqueness semantics. `accession_number`/`sec_link` keep the
door open for a raw-EDGAR backfill later (spec decision)."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class InsiderTransaction(Base):
    __tablename__ = "insider_transactions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    insider_name: Mapped[str] = mapped_column(String(256), nullable=False)
    insider_title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Raw FMP code, e.g. "P-Purchase", "S-Sale", "A-Award"
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Normalized: buy | sell | other (open-market P/S only; awards/exercises = other)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    shares_owned_after: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    accession_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sec_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    natural_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        UniqueConstraint("natural_key", name="uq_insider_transactions_natural_key"),
        Index("ix_insider_transactions_ticker_date", "ticker", "transaction_date"),
    )
