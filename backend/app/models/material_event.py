"""MaterialEvent — one classified 8-K per row, surfaced on the status board."""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class MaterialEvent(Base):
    """Haiku-classified 8-K filing. One row per Filing (the classifier picks
    the dominant event type; the summary may mention secondary items)."""

    __tablename__ = "material_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Raw EDGAR items string, e.g. "2.02,9.01"
    item_codes: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # guidance | personnel | ma | financing | other
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # high | medium | low
    materiality: Mapped[str] = mapped_column(String(8), nullable=False)
    headline: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )
    # Mirrors read-through dismissal: hidden from badge + Today when set.
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("filing_id", name="uq_material_events_filing"),
        Index("ix_material_events_ticker_date", "ticker", "filing_date"),
    )
