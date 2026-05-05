"""add kill_criterion_states table and archived_at on research_runs

Revision ID: 0b7ff9421fa5
Revises: 27ee955f03d8
Create Date: 2026-05-04 20:48:17.235179
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0b7ff9421fa5'
down_revision: Union[str, None] = '27ee955f03d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kill_criterion_states',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('flipped_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['research_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'ordinal', name='uq_kill_criterion_state_run_ordinal'),
    )
    op.create_index(
        'ix_kill_criterion_states_run_id',
        'kill_criterion_states',
        ['run_id'],
        unique=False,
    )

    op.add_column(
        'research_runs',
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_research_runs_archived_at',
        'research_runs',
        ['archived_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_research_runs_archived_at', table_name='research_runs')
    op.drop_column('research_runs', 'archived_at')
    op.drop_index('ix_kill_criterion_states_run_id', table_name='kill_criterion_states')
    op.drop_table('kill_criterion_states')
