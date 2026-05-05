"""EarningsPrint — one row per (ticker, fiscal_period).

Per-ticker, shared across themes. Idempotent on
(ticker, fiscal_year, fiscal_quarter): `INSERT ... ON CONFLICT DO UPDATE`
upgrades a row from "estimates only" to "estimates + actuals" when
FMP populates epsActual. Re-runs of the daily scheduler are safe.

For non-calendar-year reporters where FMP doesn't expose fiscal periods
reliably, fiscal_year/quarter are derived from earnings_date (calendar).
The unique constraint is on the inferred values, not on a pristine
fiscal mapping.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class EarningsPrint(Base):
    __tablename__ = "earnings_prints"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)

    eps_estimated: Mapped[float | None] = mapped_column(Float)
    eps_actual: Mapped[float | None] = mapped_column(Float)
    revenue_estimated: Mapped[float | None] = mapped_column(Float)
    revenue_actual: Mapped[float | None] = mapped_column(Float)

    # Computed at write-time, nullable when actual is missing.
    eps_surprise_pct: Mapped[float | None] = mapped_column(Float)
    revenue_surprise_pct: Mapped[float | None] = mapped_column(Float)

    # Best-effort from transcript scrape; null when undetermined.
    # Allowed values: "raised" | "maintained" | "lowered" | "n/a"
    guidance_direction: Mapped[str | None] = mapped_column(String(20))

    # Pointer to the transcript that informed guidance/verdict.
    transcript_year: Mapped[int | None] = mapped_column(Integer)
    transcript_quarter: Mapped[int | None] = mapped_column(Integer)

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker",
            "fiscal_year",
            "fiscal_quarter",
            name="uq_earnings_prints_period",
        ),
        Index("ix_earnings_prints_ticker_date", "ticker", "earnings_date"),
    )
