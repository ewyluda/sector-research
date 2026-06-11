"""Citation: the first-class data provenance primitive.

Two representations:
  - Citation (dataclass): returned by every data client method alongside data
  - CitationRecord (ORM): persisted row in the citations table
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


@dataclass
class Citation:
    """Returned by every data client method as tuple[data, Citation].

    This is the in-memory representation used throughout the pipeline.
    """

    value: str | float
    metric: str  # e.g. "Revenue Growth YoY"
    source_name: str  # e.g. "FMP /income-statement"
    source_url: str  # direct link to endpoint or SEC filing
    tier: int  # 1 = authoritative, 2 = qualitative signal only
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cell_path: str | None = None

    def with_cell(self, path: str) -> "Citation":
        """Return a copy of this Citation with cell_path set."""
        from dataclasses import replace
        return replace(self, cell_path=path)

    def to_record(self, run_id: str) -> "CitationRecord":
        """Convert to a persistable ORM instance."""
        return CitationRecord(
            run_id=run_id,
            metric=self.metric,
            value=str(self.value),
            source_name=self.source_name,
            source_url=self.source_url,
            tier=self.tier,
            retrieved_at=self.retrieved_at,
            cell_path=self.cell_path,
        )


class CitationRecord(Base):
    """Persisted citation row. One per metric per data retrieval."""

    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("research_runs.id"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(256), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    source_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    cell_path: Mapped[str | None] = mapped_column(String, nullable=True, index=False)
