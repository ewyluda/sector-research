"""Theme model — curated investment themes with sub-secular grouping."""

from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class Theme(Base, TimestampMixin):
    __tablename__ = "themes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Sub-secular grouping: nullable parent_theme_id
    parent_theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("themes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # JSONB columns for flexible theme configuration
    seed_tickers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    screener_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    x_search_terms: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)

    # Signal score weighting — configurable per theme
    signal_weights: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: {
            "x_velocity": 0.40,
            "fundamental_quality": 0.40,
            "discovery": 0.20,
        },
    )

    # Relationships
    sub_themes = relationship("Theme", backref="parent_theme", remote_side="Theme.id")
