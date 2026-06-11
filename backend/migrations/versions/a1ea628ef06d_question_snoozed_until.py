"""question snoozed_until

Revision ID: a1ea628ef06d
Revises: eb21c3df2ad5
Create Date: 2026-06-11 11:26:25.494350
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1ea628ef06d'
down_revision: Union[str, None] = 'eb21c3df2ad5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('questions', sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('questions', 'snoozed_until')
