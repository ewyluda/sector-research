"""Question ORM — per-ticker LLM-extracted open questions.

Surface for Tier 1.2 question log. Rows survive runs. Lifecycle:
- created during deep-dive (status='open')
- resolved_auto by node_targeted_followup (priority-1 + auto_answerable)
- resolved_inline by next run's deep-dive resurfacing slot
- resolved_manual or dismissed by /questions UI
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolved_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismiss_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_questions_ticker_status", "ticker", "status"),
        Index("idx_questions_ticker_theme_status", "ticker", "theme_id", "status"),
        Index("idx_questions_status_priority", "status", "priority"),
    )
