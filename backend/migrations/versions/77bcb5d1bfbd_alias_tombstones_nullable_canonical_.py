"""alias tombstones nullable canonical fields

Revision ID: 77bcb5d1bfbd
Revises: a2c6676dd30d
Create Date: 2026-06-11 00:56:21.482889

Allow canonical_cik and canonical_name to be NULL so that
curator_private tombstone rows (private companies that should never
be resolved) can be stored without a CIK.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '77bcb5d1bfbd'
down_revision: Union[str, None] = 'a2c6676dd30d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('counterparty_aliases', 'canonical_cik',
                    existing_type=sa.VARCHAR(length=16),
                    nullable=True)
    op.alter_column('counterparty_aliases', 'canonical_name',
                    existing_type=sa.VARCHAR(length=256),
                    nullable=True)


def downgrade() -> None:
    # Tombstone rows have null canonical fields and are meaningless under the old
    # NOT NULL schema — remove them before re-adding the constraint.
    op.execute("DELETE FROM counterparty_aliases WHERE source = 'curator_private'")
    op.alter_column('counterparty_aliases', 'canonical_name',
                    existing_type=sa.VARCHAR(length=256),
                    nullable=False)
    op.alter_column('counterparty_aliases', 'canonical_cik',
                    existing_type=sa.VARCHAR(length=16),
                    nullable=False)
