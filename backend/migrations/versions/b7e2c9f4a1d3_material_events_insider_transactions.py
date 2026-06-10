"""material_events + insider_transactions

Revision ID: b7e2c9f4a1d3
Revises: d9659a472017
Create Date: 2026-06-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b7e2c9f4a1d3"
down_revision: Union[str, None] = "d9659a472017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "material_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "filing_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("filings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("item_codes", sa.String(128), nullable=True),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("materiality", sa.String(8), nullable=False),
        sa.Column("headline", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("filing_id", name="uq_material_events_filing"),
    )
    op.create_index("ix_material_events_filing_id", "material_events", ["filing_id"])
    op.create_index("ix_material_events_ticker", "material_events", ["ticker"])
    op.create_index(
        "ix_material_events_ticker_date", "material_events", ["ticker", "filing_date"]
    )

    op.create_table(
        "insider_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("insider_name", sa.String(256), nullable=False),
        sa.Column("insider_title", sa.String(256), nullable=True),
        sa.Column("transaction_type", sa.String(64), nullable=True),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("shares", sa.Numeric(), nullable=True),
        sa.Column("price", sa.Numeric(), nullable=True),
        sa.Column("shares_owned_after", sa.Numeric(), nullable=True),
        sa.Column("accession_number", sa.String(32), nullable=True),
        sa.Column("sec_link", sa.String(512), nullable=True),
        sa.Column("natural_key", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "natural_key", name="uq_insider_transactions_natural_key"
        ),
    )
    op.create_index("ix_insider_transactions_ticker", "insider_transactions", ["ticker"])
    op.create_index(
        "ix_insider_transactions_ticker_date",
        "insider_transactions",
        ["ticker", "transaction_date"],
    )


def downgrade() -> None:
    op.drop_table("insider_transactions")
    op.drop_table("material_events")
