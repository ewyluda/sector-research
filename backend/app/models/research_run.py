"""ResearchRun — a single ticker's journey through the 6-phase pipeline."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_runs"
    __table_args__ = (
        Index("ix_research_runs_ticker_created_at", "ticker", "created_at"),
        Index("ix_research_runs_status_board_latest", "ticker", "theme_id", text("created_at DESC"),
              postgresql_where=text("status IN ('completed', 'watchlist') AND theme_id IS NOT NULL")),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Pipeline state
    phase: Mapped[str] = mapped_column(
        String(64), nullable=False, default="quick_screen"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_progress"
    )  # in_progress | paused | completed | watchlist | pass | abandoned

    # Full ResearchState, serialised
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Loop tracking (Phase 5 → Phase 3 loop-backs, max 2)
    loop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status board: archive gesture. Null = on the board, non-null = archived.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=None
    )
