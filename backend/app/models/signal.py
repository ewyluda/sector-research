"""Signal — cached X API and computed signal data per ticker per theme."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # velocity | narrative | discovery
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Flexible payload — structure varies by signal_type
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
