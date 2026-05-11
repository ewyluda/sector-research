"""verdict_outcomes

Revision ID: 12f874fd1d02
Revises: 3cf8b874da39
Create Date: 2026-05-10 23:03:29.501374
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "12f874fd1d02"
down_revision: Union[str, None] = "3cf8b874da39"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SECTOR_ETF_SEEDS = [
    ("Technology", "XLK", None),
    ("Energy", "XLE", None),
    ("Healthcare", "XLV", None),
    ("Financial Services", "XLF", None),
    ("Industrials", "XLI", None),
    ("Consumer Cyclical", "XLY", None),
    ("Consumer Defensive", "XLP", None),
    ("Basic Materials", "XLB", None),
    ("Utilities", "XLU", None),
    ("Real Estate", "XLRE", None),
    ("Communication Services", "XLC", None),
]


def upgrade() -> None:
    op.create_table(
        "sector_etf_mapping",
        sa.Column("fmp_sector", sa.String(length=64), primary_key=True),
        sa.Column("etf_ticker", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.bulk_insert(
        sa.table(
            "sector_etf_mapping",
            sa.column("fmp_sector", sa.String),
            sa.column("etf_ticker", sa.String),
            sa.column("notes", sa.Text),
        ),
        [{"fmp_sector": s, "etf_ticker": e, "notes": n} for (s, e, n) in SECTOR_ETF_SEEDS],
    )

    op.create_table(
        "verdict_outcomes",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("theme_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("verdict", sa.String(length=32), nullable=False),
        sa.Column("verdict_emitted_at", sa.DateTime(timezone=True), nullable=False),

        sa.Column("entry_price_at", sa.Date(), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("entry_price_source", sa.String(length=64), nullable=False,
                  server_default=sa.text("'fmp_historical_eod_adjusted'")),

        sa.Column("spy_entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector_etf_ticker", sa.String(length=16), nullable=True),
        sa.Column("sector_etf_entry_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_entry_value", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_constituents", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column("signal_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_outcome_id", sa.UUID(as_uuid=False), nullable=True),
        sa.Column("realized_ticker_return_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_spy_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_sector_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_theme_basket_excess_pct", sa.Numeric(20, 8), nullable=True),

        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["theme_id"], ["themes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_outcome_id"], ["verdict_outcomes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_type", "source_id", name="uq_verdict_outcomes_source"),
    )
    op.create_index("ix_outcomes_ticker_emitted", "verdict_outcomes",
                    ["ticker", sa.text("verdict_emitted_at DESC")])
    op.create_index("ix_outcomes_theme_emitted", "verdict_outcomes",
                    ["theme_id", sa.text("verdict_emitted_at DESC")])
    op.create_index("ix_outcomes_open", "verdict_outcomes", ["closed_at"],
                    postgresql_where=sa.text("closed_at IS NULL"))
    op.create_index("ix_outcomes_open_per_position", "verdict_outcomes",
                    ["ticker", "theme_id", "source_type", "superseded_at"],
                    postgresql_where=sa.text("superseded_at IS NULL"))

    op.create_table(
        "verdict_return_snapshots",
        sa.Column("id", sa.UUID(as_uuid=False), primary_key=True),
        sa.Column("outcome_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("snapshot_offset", sa.String(length=8), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),

        sa.Column("ticker_price", sa.Numeric(20, 6), nullable=False),
        sa.Column("spy_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("sector_etf_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("theme_basket_value", sa.Numeric(20, 6), nullable=True),

        sa.Column("ticker_return_pct", sa.Numeric(20, 8), nullable=False),
        sa.Column("spy_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("sector_excess_pct", sa.Numeric(20, 8), nullable=True),
        sa.Column("theme_basket_excess_pct", sa.Numeric(20, 8), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["outcome_id"], ["verdict_outcomes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("outcome_id", "snapshot_offset", name="uq_snapshot_outcome_offset"),
    )
    op.create_index("ix_snapshots_outcome", "verdict_return_snapshots", ["outcome_id"])


def downgrade() -> None:
    op.drop_index("ix_snapshots_outcome", table_name="verdict_return_snapshots")
    op.drop_table("verdict_return_snapshots")

    op.drop_index("ix_outcomes_open_per_position", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_open", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_theme_emitted", table_name="verdict_outcomes")
    op.drop_index("ix_outcomes_ticker_emitted", table_name="verdict_outcomes")
    op.drop_table("verdict_outcomes")

    op.drop_table("sector_etf_mapping")
