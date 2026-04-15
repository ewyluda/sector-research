"""SEC EDGAR filing + XBRL fact models.

One `Filing` row per unique accession number. Each `XBRLFact` references a
filing and represents a single numeric fact (concept, unit, period, value).

Kept separate from `CuratedFinancials` (which is JSONB inside ResearchState)
so we can accumulate XBRL history across many filings and tickers without
bloating run state.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
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

    # Timestamp of the most recent Haiku relationship-extraction pass.
    # Null = never attempted; non-null = attempted (even if zero relationships
    # were found). Lets the extractor skip already-attempted sections without
    # storing sentinel relationship rows.
    relationships_extracted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("filing_id", "section_key", name="uq_filing_sections_filing_section"),
        Index("ix_filing_sections_ticker_section", "ticker", "section_key"),
    )


class Relationship(Base):
    """Business relationship extracted from a filing section by Haiku.

    One row per (filing_id, section_key, counterparty_name, relationship_type).
    Stored alongside filings/xbrl_facts so relationships accumulate across
    tickers and time — not tied to any single research run.
    """

    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    filing_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("filings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Ticker of the filer (anchor company). Counterparty resolution to a
    # canonical CIK happens in Phase C.
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Free-text name as it appears in the filing. Resolution to a canonical
    # CIK is deferred to Phase C (counterparty_aliases table).
    counterparty_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    # customer, supplier, partner, competitor, licensor, licensee,
    # distributor, reseller, joint_venture, other
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional percentage (e.g. "20% of revenue"). Null when not disclosed.
    magnitude_pct: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    # True when the filing describes a concentration without naming the
    # counterparty ("a single customer represented 15% of revenue").
    unnamed: Mapped[bool] = mapped_column(default=False, nullable=False)

    # The sentence(s) the extractor based the relationship on — for audit.
    verbatim_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set to True when a reciprocal relationship exists in another filing
    # (e.g. AAPL → TSMC supplier AND TSMC → AAPL customer). Updated in
    # Phase D during bilateral reconciliation.
    confirmed_bilateral: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Phase C write-through resolution. Populated when the counterparty_name
    # has been resolved to a canonical entity via counterparty_aliases. Null
    # until resolved (or unresolvable).
    resolved_to_cik: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    resolved_to_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)

    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )

    __table_args__ = (
        UniqueConstraint(
            "filing_id", "section_key", "counterparty_name", "relationship_type",
            name="uq_relationships_filing_section_counterparty_type",
        ),
        Index("ix_relationships_ticker_type", "ticker", "relationship_type"),
        Index("ix_relationships_counterparty_name", "counterparty_name"),
    )


class CounterpartyAlias(Base):
    """Phase C resolution: map a free-text counterparty mention to a
    canonical company (identified by CIK + optional ticker).

    The alias store grows monotonically — each resolution decision is
    persisted and re-used for future extractions. Manual curator overrides
    always beat fuzzy auto-matches for the same alias_normalized key.
    """

    __tablename__ = "counterparty_aliases"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    # The name as it appeared in the filing (unmodified — for reference).
    alias_name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Canonical key used for lookup: lowercased + stripped of "Inc.",
    # "Corporation", punctuation, etc. Unique so a given normalized form
    # maps to at most one canonical company.
    alias_normalized: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)

    canonical_cik: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Denormalized for quick UI reads. Null if the CIK doesn't have a
    # public ticker in EDGAR (e.g. private subsidiaries that still file).
    canonical_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    canonical_name: Mapped[str] = mapped_column(String(256), nullable=False)

    # "exact_match" — normalized alias == normalized canonical name
    # "fuzzy_auto" — RapidFuzz score ≥ 95
    # "curator_manual" — user manually resolved via the curation queue
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.utcnow()
    )
    # Identifier for the manual curator — nullable for auto-resolved rows.
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_counterparty_aliases_canonical_cik", "canonical_cik"),
    )
