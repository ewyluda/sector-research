"""SignalHistory — append-only time series of computed X signal values."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class SignalHistory(Base):
    """One row per (ticker, theme_id, signal_type) per scheduler run.

    The current-value `signals` row is updated in place, but a SignalHistory
    row is appended on every refresh so multi-month sparklines and surprise
    threshold tuning have a real time series.
    """

    __tablename__ = "signal_history"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    theme_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        # Time-series read pattern: pick the latest N rows for one
        # (ticker, theme_id, signal_type) ordered by computed_at desc.
        Index(
            "ix_signal_history_lookup",
            "ticker", "theme_id", "signal_type", "computed_at",
        ),
    )
