"""WorkspaceRun — a post-earnings workspace refresh for a single ticker."""

from uuid import uuid4

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class WorkspaceRun(Base, TimestampMixin):
    __tablename__ = "workspace_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    parent_research_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("research_runs.id", ondelete="SET NULL"), nullable=True
    )

    # Model versions before/after
    ticker_model_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker_model_version_after: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Execution state
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running"
    )  # running | completed | failed | watchlist

    # Final verdict (if completed)
    verdict: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Step outputs keyed by step name (e.g., "update_refresh", "research", "validation", "challenge", "differentiation")
    step_outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Citations collected across all steps
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Error message if status = failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
