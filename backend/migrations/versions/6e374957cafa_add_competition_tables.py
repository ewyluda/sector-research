"""add competition tables

Revision ID: 6e374957cafa
Revises: 1e48a3f6aabc
Create Date: 2026-04-27 00:02:11.181470
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6e374957cafa'
down_revision: Union[str, None] = '1e48a3f6aabc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # filing_segments — per-segment narrative
    op.create_table(
        "filing_segments",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("filing_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("segment_name", sa.String(length=256), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "filing_id", "segment_name",
            name="uq_filing_segments_filing_segment",
        ),
    )
    op.create_index(
        op.f("ix_filing_segments_filing_id"), "filing_segments", ["filing_id"],
    )
    op.create_index(
        op.f("ix_filing_segments_ticker"), "filing_segments", ["ticker"],
    )

    # competitor_landscape — per-(segment, area) row with competitors[] JSONB
    op.create_table(
        "competitor_landscape",
        sa.Column("id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("filing_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("segment_name", sa.String(length=256), nullable=False),
        sa.Column("area_of_competition", sa.Text(), nullable=False),
        sa.Column(
            "competitors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["filing_id"], ["filings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "filing_id", "segment_name", "area_of_competition",
            name="uq_competitor_landscape_filing_segment_area",
        ),
    )
    op.create_index(
        op.f("ix_competitor_landscape_filing_id"), "competitor_landscape", ["filing_id"],
    )
    op.create_index(
        op.f("ix_competitor_landscape_ticker"), "competitor_landscape", ["ticker"],
    )

    # tombstone column on filing_sections
    op.add_column(
        "filing_sections",
        sa.Column(
            "competition_extracted_at", sa.DateTime(timezone=True), nullable=True,
        ),
    )

    # one-time cleanup — competitors leave the relationships table entirely;
    # the new tables own this surface
    op.execute("DELETE FROM relationships WHERE relationship_type = 'competitor'")


def downgrade() -> None:
    # NOTE: the deletion of competitor rows is not restored. Re-running
    # extract_ticker_relationships against the same filings recovers them.
    op.drop_column("filing_sections", "competition_extracted_at")
    op.drop_index(op.f("ix_competitor_landscape_ticker"), table_name="competitor_landscape")
    op.drop_index(op.f("ix_competitor_landscape_filing_id"), table_name="competitor_landscape")
    op.drop_table("competitor_landscape")
    op.drop_index(op.f("ix_filing_segments_ticker"), table_name="filing_segments")
    op.drop_index(op.f("ix_filing_segments_filing_id"), table_name="filing_segments")
    op.drop_table("filing_segments")
