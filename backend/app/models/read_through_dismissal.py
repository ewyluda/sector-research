"""ReadThroughDismissal — records that a peer-event read-through has been
dismissed for a specific thesis run.

Default state (not dismissed) is implicit absence; only dismissals are
persisted. Dismissals survive engine recomputation because event_key is
deterministic (e.g. "earnings:NVDA:2026-08-15", "run_complete:<uuid>").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ReadThroughDismissal(Base):
    __tablename__ = "read_through_dismissals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id", "event_key", name="uq_read_through_dismissals_run_event"
        ),
        Index("ix_read_through_dismissals_run_id", "run_id"),
    )
