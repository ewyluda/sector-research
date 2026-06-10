"""journal_trades

Revision ID: a2c6676dd30d
Revises: b7e2c9f4a1d3
Create Date: 2026-06-10 14:43:32.320064
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2c6676dd30d'
down_revision: Union[str, None] = 'b7e2c9f4a1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('journal_trades',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('ticker', sa.String(length=16), nullable=False),
    sa.Column('direction', sa.String(length=8), server_default='long', nullable=False),
    sa.Column('entry_date', sa.Date(), nullable=False),
    sa.Column('entry_price', sa.Numeric(precision=20, scale=6), nullable=False),
    sa.Column('entry_price_source', sa.String(length=32), nullable=False),
    sa.Column('exit_date', sa.Date(), nullable=True),
    sa.Column('exit_price', sa.Numeric(precision=20, scale=6), nullable=True),
    sa.Column('exit_price_source', sa.String(length=32), nullable=True),
    sa.Column('quantity', sa.Numeric(precision=20, scale=6), nullable=True),
    sa.Column('spy_entry_price', sa.Numeric(precision=20, scale=6), nullable=True),
    sa.Column('spy_exit_price', sa.Numeric(precision=20, scale=6), nullable=True),
    sa.Column('outcome_id', sa.UUID(as_uuid=False), nullable=True),
    sa.Column('entry_rationale', sa.Text(), nullable=True),
    sa.Column('exit_reason', sa.String(length=32), nullable=True),
    sa.Column('exit_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['outcome_id'], ['verdict_outcomes.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_journal_trades_open_ticker', 'journal_trades', ['ticker'], unique=False, postgresql_where=sa.text('exit_date IS NULL'))
    op.create_index('ix_journal_trades_outcome_id', 'journal_trades', ['outcome_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_journal_trades_outcome_id', table_name='journal_trades')
    op.drop_index('ix_journal_trades_open_ticker', table_name='journal_trades', postgresql_where=sa.text('exit_date IS NULL'))
    op.drop_table('journal_trades')
