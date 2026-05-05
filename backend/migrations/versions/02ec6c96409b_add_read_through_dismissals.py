"""add read_through_dismissals

Revision ID: 02ec6c96409b
Revises: 0b7ff9421fa5
Create Date: 2026-05-04 22:47:54.325087
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '02ec6c96409b'
down_revision: Union[str, None] = '0b7ff9421fa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('read_through_dismissals',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('run_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('event_key', sa.String(length=255), nullable=False),
    sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['research_runs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'event_key', name='uq_read_through_dismissals_run_event')
    )
    op.create_index('ix_read_through_dismissals_run_id', 'read_through_dismissals', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_read_through_dismissals_run_id', table_name='read_through_dismissals')
    op.drop_table('read_through_dismissals')
