"""peer_sets

Revision ID: d9659a472017
Revises: 91f56be7821d
Create Date: 2026-06-09 18:41:07.991749
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd9659a472017'
down_revision: Union[str, None] = '91f56be7821d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "peer_sets",
        sa.Column("ticker", sa.String(length=16), primary_key=True),
        sa.Column("peers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("peer_sets")
