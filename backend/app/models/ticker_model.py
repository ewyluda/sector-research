"""TickerModel ORM — versioned per-ticker financial model state."""
from __future__ import annotations
import uuid
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class TickerModel(Base, TimestampMixin):
    __tablename__ = "ticker_models"
    __table_args__ = (UniqueConstraint("ticker", "version", name="uq_ticker_models_ticker_version"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parent_research_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("research_runs.id"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
