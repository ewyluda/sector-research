"""CongressTransaction — one senate/house periodic-transaction-report line,
FMP-sourced (/stable/senate-trades + /stable/house-trades).

`natural_key` is a sha256 over the identifying fields (see
services/congress_ingest.py) so daily re-ingests are idempotent without
guessing FMP's uniqueness semantics — the insider_transactions convention.
Amounts are disclosed ranges; `amount_mid` is the parsed midpoint (lower
bound for open-ended ranges), `amount_range` keeps the raw string."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class CongressTransaction(Base):
    __tablename__ = "congress_transactions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    politician_name: Mapped[str] = mapped_column(String(256), nullable=False)
    chamber: Mapped[str] = mapped_column(String(8), nullable=False)  # senate | house
    district: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Filer relationship on the disclosure line: Self / Spouse / Child / Joint
    owner: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Raw FMP type, e.g. "Purchase", "Sale", "Sale (Partial)", "Exchange"
    transaction_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Normalized: buy | sell | other (exchanges and unknown types = other)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disclosure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_range: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_mid: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    disclosure_link: Mapped[str | None] = mapped_column(String(512), nullable=True)
    natural_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        UniqueConstraint("natural_key", name="uq_congress_transactions_natural_key"),
        Index("ix_congress_transactions_ticker_date", "ticker", "transaction_date"),
    )
