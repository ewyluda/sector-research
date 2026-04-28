"""transcript relationships: nullable filing_id, source columns, partial indexes, transcript_extractions table

Revision ID: ecaf04c60243
Revises: 6e374957cafa
Create Date: 2026-04-27 22:16:53.253848
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'ecaf04c60243'
down_revision: Union[str, None] = '6e374957cafa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Make relationships.filing_id nullable.
    op.alter_column(
        "relationships",
        "filing_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=True,
    )

    # 2. Add discriminator + transcript provenance columns.
    op.add_column(
        "relationships",
        sa.Column(
            "source_type",
            sa.String(length=16),
            nullable=False,
            server_default="filing",
        ),
    )
    op.add_column(
        "relationships",
        sa.Column("transcript_year", sa.Integer(), nullable=True),
    )
    op.add_column(
        "relationships",
        sa.Column("transcript_quarter", sa.SmallInteger(), nullable=True),
    )

    # 3. Belt-and-suspenders backfill (DEFAULT covers new rows, this covers
    # any existing rows in case server_default isn't applied retroactively).
    op.execute("UPDATE relationships SET source_type = 'filing' WHERE source_type IS NULL")

    # 4. Source-consistency CHECK.
    op.create_check_constraint(
        "ck_relationships_source_consistency",
        "relationships",
        "(source_type = 'filing' AND filing_id IS NOT NULL) "
        "OR (source_type = 'transcript' "
        "AND filing_id IS NULL "
        "AND transcript_year IS NOT NULL "
        "AND transcript_quarter IS NOT NULL)",
    )

    # 5. Drop the existing unique constraint (NULL filing_id breaks it).
    op.drop_constraint(
        "uq_relationships_filing_section_counterparty_type",
        "relationships",
        type_="unique",
    )

    # 6. Two partial unique indexes — one per source_type flavor.
    op.create_index(
        "uq_relationships_filing",
        "relationships",
        ["filing_id", "section_key", "counterparty_name", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("filing_id IS NOT NULL"),
    )
    op.create_index(
        "uq_relationships_transcript",
        "relationships",
        ["ticker", "transcript_year", "transcript_quarter", "counterparty_name", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("filing_id IS NULL"),
    )

    # 7. transcript_extractions tombstone table.
    op.create_table(
        "transcript_extractions",
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.SmallInteger(), nullable=False),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "relationships_added",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "ticker", "year", "quarter", name="pk_transcript_extractions"
        ),
    )


def downgrade() -> None:
    op.drop_table("transcript_extractions")
    op.drop_index("uq_relationships_transcript", table_name="relationships")
    op.drop_index("uq_relationships_filing", table_name="relationships")
    op.create_unique_constraint(
        "uq_relationships_filing_section_counterparty_type",
        "relationships",
        ["filing_id", "section_key", "counterparty_name", "relationship_type"],
    )
    op.drop_constraint("ck_relationships_source_consistency", "relationships", type_="check")
    op.drop_column("relationships", "transcript_quarter")
    op.drop_column("relationships", "transcript_year")
    op.drop_column("relationships", "source_type")
    # Caller must ensure no transcript-sourced rows exist before downgrading.
    op.alter_column(
        "relationships",
        "filing_id",
        existing_type=postgresql.UUID(as_uuid=False),
        nullable=False,
    )
