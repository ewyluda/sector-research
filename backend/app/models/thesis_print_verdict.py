"""ThesisPrintVerdict — per-run, per-print Haiku verdict.

One row per (run_id, earnings_print_id). Lazy — written only when the
user clicks "Run thesis-check." Idempotent on (run_id, earnings_print_id):
re-clicking overwrites with a fresh Haiku call.

CASCADE on run_id: re-running the thesis orphans old verdicts. The
status board picks the latest run per (ticker, theme), so users
naturally see "no verdict yet" on a fresh run with prior prints,
prompting a re-trigger.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ThesisPrintVerdict(Base):
    __tablename__ = "thesis_print_verdicts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    earnings_print_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("earnings_prints.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Allowed values: "confirms" | "threatens" | "neutral" | "insufficient"
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    summary_md: Mapped[str] = mapped_column(Text, nullable=False)
    pillars_addressed: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "earnings_print_id",
            name="uq_thesis_print_verdicts_run_print",
        ),
        Index("ix_thesis_print_verdicts_run_id", "run_id"),
    )
