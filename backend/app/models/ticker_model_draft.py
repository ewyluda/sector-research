"""TickerModelDraft ORM — in-progress (unsaved) model edits per ticker."""
from __future__ import annotations
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class TickerModelDraft(Base, TimestampMixin):
    __tablename__ = "ticker_model_drafts"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    base_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ticker_models.id"), nullable=False
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
