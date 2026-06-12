"""congress_transactions

Revision ID: c4d8e91f72a6
Revises: a1ea628ef06d
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d8e91f72a6"
down_revision: Union[str, None] = "a1ea628ef06d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "congress_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("politician_name", sa.String(256), nullable=False),
        sa.Column("chamber", sa.String(8), nullable=False),
        sa.Column("district", sa.String(16), nullable=True),
        sa.Column("owner", sa.String(32), nullable=True),
        sa.Column("transaction_type", sa.String(64), nullable=True),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("disclosure_date", sa.Date(), nullable=True),
        sa.Column("amount_range", sa.String(64), nullable=True),
        sa.Column("amount_mid", sa.Numeric(), nullable=True),
        sa.Column("disclosure_link", sa.String(512), nullable=True),
        sa.Column("natural_key", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "natural_key", name="uq_congress_transactions_natural_key"
        ),
    )
    op.create_index(
        "ix_congress_transactions_ticker", "congress_transactions", ["ticker"]
    )
    op.create_index(
        "ix_congress_transactions_ticker_date",
        "congress_transactions",
        ["ticker", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_table("congress_transactions")
