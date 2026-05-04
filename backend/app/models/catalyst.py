"""Catalyst — first-class catalyst event row, FK'd to a thesis run.

One row per catalyst per thesis run. Re-running the thesis produces a
fresh set; old rows remain as historical record (per-run scoping, not
identity-merged across re-runs).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Catalyst(Base):
    __tablename__ = "catalysts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    ordinal: Mapped[int] = mapped_column(nullable=False)

    # Sonnet-emitted (Tier 1.1 catalyst schema)
    timeframe: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    type: Mapped[str | None] = mapped_column(String(20))
    signposts: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    linked_pillar: Mapped[str | None] = mapped_column(String(10))

    # Date inference
    expected_date: Mapped[date | None]
    expected_window_start: Mapped[date | None]
    expected_window_end: Mapped[date | None]
    date_source: Mapped[str] = mapped_column(String(20), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_catalysts_run_id", "run_id"),
        Index("ix_catalysts_ticker_expected_date", "ticker", "expected_date"),
    )
