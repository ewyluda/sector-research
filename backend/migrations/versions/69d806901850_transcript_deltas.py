"""transcript_deltas

Revision ID: 69d806901850
Revises: 12f874fd1d02
Create Date: 2026-05-11 13:59:58.060929
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "69d806901850"
down_revision: Union[str, None] = "12f874fd1d02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcript_deltas",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("transcripts_window", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("transcripts_fingerprint", sa.String(), nullable=False),
        sa.Column("axes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("ticker", "transcripts_fingerprint",
                            name="uq_transcript_deltas_ticker_fingerprint"),
    )
    op.create_index(
        "ix_transcript_deltas_ticker_computed_at",
        "transcript_deltas", ["ticker", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_deltas_ticker_computed_at",
                  table_name="transcript_deltas")
    op.drop_table("transcript_deltas")
