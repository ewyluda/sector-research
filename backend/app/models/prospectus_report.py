"""ProspectusReport — analytical report for an S-1 / S-1/A filing.

Parallel to ResearchRun and WorkspaceRun. step_outputs is a JSONB blob
shaped like WorkspaceRun.step_outputs (one keyed entry per pipeline step).
"""
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


def _slugify_issuer(name: str) -> str:
    """Uppercase alphanumeric-only, truncated to 16 chars."""
    return "".join(c for c in (name or "").upper() if c.isalnum())[:16]


class ProspectusReport(Base, TimestampMixin):
    __tablename__ = "prospectus_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    issuer_cik: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    issuer_name: Mapped[str] = mapped_column(String(256), nullable=False)
    proposed_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)

    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ingesting")
    step_outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def synthetic_ticker(self) -> str:
        """Identifier written into filings.ticker / relationships.ticker.

        See spec — proposed_ticker if disclosed, else uppercase alphanumeric
        slug of issuer_name truncated to 16 chars.
        """
        if self.proposed_ticker:
            return self.proposed_ticker.upper()[:16]
        return _slugify_issuer(self.issuer_name)
