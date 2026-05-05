"""ResearchRun — a single ticker's journey through the 6-phase pipeline."""

from uuid import uuid4

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id"), nullable=False, index=True
    )

    # Pipeline state
    phase: Mapped[str] = mapped_column(
        String(64), nullable=False, default="quick_screen"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="in_progress"
    )  # in_progress | paused | completed | watchlist | pass

    # Full LangGraph state, serialised
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Loop tracking (Phase 5 → Phase 3 loop-backs, max 2)
    loop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status board: archive gesture. Null = on the board, non-null = archived.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, default=None
    )
