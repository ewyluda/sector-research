"""add catalysts table

Revision ID: 27ee955f03d8
Revises: ecaf04c60243
Create Date: 2026-05-03 22:10:20.341519
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '27ee955f03d8'
down_revision: Union[str, None] = 'ecaf04c60243'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('catalysts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('run_id', sa.UUID(), nullable=False),
    sa.Column('ticker', sa.String(length=10), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=True),
    sa.Column('signposts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('linked_pillar', sa.String(length=10), nullable=True),
    sa.Column('expected_date', sa.Date(), nullable=True),
    sa.Column('expected_window_start', sa.Date(), nullable=True),
    sa.Column('expected_window_end', sa.Date(), nullable=True),
    sa.Column('date_source', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['research_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_catalysts_run_id', 'catalysts', ['run_id'], unique=False)
    op.create_index('ix_catalysts_ticker_expected_date', 'catalysts', ['ticker', 'expected_date'], unique=False)
    op.create_index(
        "ix_research_runs_ticker_created_at",
        "research_runs",
        ["ticker", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_runs_ticker_created_at", table_name="research_runs")
    op.drop_index('ix_catalysts_ticker_expected_date', table_name='catalysts')
    op.drop_index('ix_catalysts_run_id', table_name='catalysts')
    op.drop_table('catalysts')
