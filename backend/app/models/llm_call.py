"""LLMCall — one row per Claude API call, for cost and latency accounting.

`run_kind` + `run_id` attribute the call to a research run, workspace run,
prospectus report, or model build (run_id = ticker); calls made outside any
run (event classification, question retries) have both null. No foreign key,
because run_id points at different tables depending on run_kind.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class LLMCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    run_kind: Mapped[str | None] = mapped_column(String(32))
    run_id: Mapped[str | None] = mapped_column(String(64))
    phase: Mapped[str | None] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6))

    __table_args__ = (
        Index("ix_llm_calls_run_id", "run_id"),
        Index("ix_llm_calls_created_at", "created_at"),
    )
