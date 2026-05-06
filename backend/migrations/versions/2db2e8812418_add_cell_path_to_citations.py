"""add cell_path to citations

Revision ID: 2db2e8812418
Revises: e68b9478e450
Create Date: 2026-05-06 14:20:33.083426
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2db2e8812418'
down_revision: Union[str, None] = 'e68b9478e450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('citations', sa.Column('cell_path', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('citations', 'cell_path')
