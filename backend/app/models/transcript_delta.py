"""TranscriptDelta ORM — caches Haiku-extracted QoQ language deltas per ticker."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class TranscriptDelta(Base):
    __tablename__ = "transcript_deltas"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    transcripts_window: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    transcripts_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    axes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker", "transcripts_fingerprint",
            name="uq_transcript_deltas_ticker_fingerprint",
        ),
        Index(
            "ix_transcript_deltas_ticker_computed_at",
            "ticker", "computed_at",
        ),
    )
