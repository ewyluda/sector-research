"""add signal_history

Revision ID: 8b4fd10f00d3
Revises: 28aa0887373a
Create Date: 2026-05-09 23:23:11.072048
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '8b4fd10f00d3'
down_revision: Union[str, None] = '28aa0887373a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('signal_history',
    sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('ticker', sa.String(length=16), nullable=False),
    sa.Column('theme_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('signal_type', sa.String(length=32), nullable=False),
    sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['theme_id'], ['themes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_signal_history_lookup', 'signal_history', ['ticker', 'theme_id', 'signal_type', 'computed_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_signal_history_lookup', table_name='signal_history')
    op.drop_table('signal_history')
