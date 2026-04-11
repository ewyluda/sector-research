"""SurpriseAlert — fired when a ticker's velocity ratio exceeds 2.0× prior period."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class SurpriseAlert(Base):
    __tablename__ = "surprise_alerts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id"), nullable=False, index=True
    )

    prior_velocity_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    current_velocity_ratio: Mapped[float] = mapped_column(Float, nullable=False)

    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
