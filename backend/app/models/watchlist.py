"""Watchlist — tickers parked for future re-evaluation."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id"), nullable=False, index=True
    )
    trigger_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("research_runs.id"), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
