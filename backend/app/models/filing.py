"""SEC EDGAR filing + XBRL fact models.

One `Filing` row per unique accession number. Each `XBRLFact` references a
filing and represents a single numeric fact (concept, unit, period, value).

Kept separate from `CuratedFinancials` (which is JSONB inside ResearchState)
so we can accumulate XBRL history across many filings and tickers without
bloating run state.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, TimestampMixin


class Filing(Base, TimestampMixin):
    __tablename__ = "filings"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    accession_number: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    cik: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    form_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 10-K, 10-Q, 8-K, DEF 14A
    filing_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_of_report: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_document_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        Index("ix_filings_ticker_form", "ticker", "form_type"),
    )


class XBRLFact(Base):
    __tablename__ = "xbrl_facts"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # e.g. us-gaap:RevenueRemainingPerformanceObligation
    unit: Mapped[str] = mapped_column(String(32), nullable=False)  # USD, shares, pure

    # Period: instant filings have period_end = period_start; duration filings span a range.
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(nullable=True)
    fiscal_period: Mapped[str | None] = mapped_column(String(8), nullable=True)  # FY, Q1..Q4

    value: Mapped[float] = mapped_column(Numeric, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        Index("ix_xbrl_facts_ticker_concept", "ticker", "concept"),
        Index("ix_xbrl_facts_concept_period", "concept", "period_end"),
    )


class FilingSection(Base):
    """Extracted narrative section from a 10-K / 10-Q / DEF 14A filing.

    One row per (filing_id, section_key). Full text is stored; prompt builders
    are responsible for truncating to per-category budgets.
    """

    __tablename__ = "filing_sections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # Canonical key identifying the section type.
    # e.g. item_1_business, item_1a_risk_factors, item_7_mda, item_2_mda_10q,
    # def14a_governance
    section_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    heading: Mapped[str | None] = mapped_column(String(512), nullable=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # "anchor" if section was located via <a href="#item1"> TOC links,
    # "regex" if located via normalized-text regex fallback.
    extraction_method: Mapped[str] = mapped_column(String(16), nullable=False)

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        UniqueConstraint("filing_id", "section_key", name="uq_filing_sections_filing_section"),
        Index("ix_filing_sections_ticker_section", "ticker", "section_key"),
    )
