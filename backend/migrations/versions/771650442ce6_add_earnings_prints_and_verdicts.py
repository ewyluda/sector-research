"""add earnings_prints and verdicts

Revision ID: 771650442ce6
Revises: 02ec6c96409b
Create Date: 2026-05-05 14:48:32.091106
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '771650442ce6'
down_revision: Union[str, None] = '02ec6c96409b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('earnings_prints',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('ticker', sa.String(length=16), nullable=False),
    sa.Column('fiscal_year', sa.Integer(), nullable=False),
    sa.Column('fiscal_quarter', sa.Integer(), nullable=False),
    sa.Column('earnings_date', sa.Date(), nullable=False),
    sa.Column('eps_estimated', sa.Float(), nullable=True),
    sa.Column('eps_actual', sa.Float(), nullable=True),
    sa.Column('revenue_estimated', sa.Float(), nullable=True),
    sa.Column('revenue_actual', sa.Float(), nullable=True),
    sa.Column('eps_surprise_pct', sa.Float(), nullable=True),
    sa.Column('revenue_surprise_pct', sa.Float(), nullable=True),
    sa.Column('guidance_direction', sa.String(length=20), nullable=True),
    sa.Column('transcript_year', sa.Integer(), nullable=True),
    sa.Column('transcript_quarter', sa.Integer(), nullable=True),
    sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ticker', 'fiscal_year', 'fiscal_quarter', name='uq_earnings_prints_period')
    )
    op.create_index('ix_earnings_prints_ticker_date', 'earnings_prints', ['ticker', 'earnings_date'], unique=False)
    op.create_table('thesis_print_verdicts',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('run_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('earnings_print_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('verdict', sa.String(length=20), nullable=False),
    sa.Column('summary_md', sa.Text(), nullable=False),
    sa.Column('pillars_addressed', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['earnings_print_id'], ['earnings_prints.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['research_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'earnings_print_id', name='uq_thesis_print_verdicts_run_print')
    )
    op.create_index('ix_thesis_print_verdicts_run_id', 'thesis_print_verdicts', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_thesis_print_verdicts_run_id', table_name='thesis_print_verdicts')
    op.drop_constraint('uq_thesis_print_verdicts_run_print', 'thesis_print_verdicts', type_='unique')
    op.drop_table('thesis_print_verdicts')
    op.drop_index('ix_earnings_prints_ticker_date', table_name='earnings_prints')
    op.drop_constraint('uq_earnings_prints_period', 'earnings_prints', type_='unique')
    op.drop_table('earnings_prints')
