"""create ticker_model_drafts

Revision ID: 524c7aed3d24
Revises: 8b80bfb7f1dc
Create Date: 2026-05-06 14:28:59.438995
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '524c7aed3d24'
down_revision: Union[str, None] = '8b80bfb7f1dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ticker_model_drafts',
    sa.Column('ticker', sa.String(), nullable=False),
    sa.Column('base_version_id', sa.UUID(as_uuid=False), nullable=False),
    sa.Column('state', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['base_version_id'], ['ticker_models.id'], ),
    sa.PrimaryKeyConstraint('ticker')
    )


def downgrade() -> None:
    op.drop_table('ticker_model_drafts')
