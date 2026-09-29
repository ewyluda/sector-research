"""llm_calls

Revision ID: 5e7a2c9d1b40
Revises: c4d8e91f72a6
Create Date: 2026-09-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5e7a2c9d1b40"
down_revision: Union[str, None] = "c4d8e91f72a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("run_kind", sa.String(32), nullable=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("phase", sa.String(64), nullable=True),
        sa.Column("kind", sa.String(128), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(16), nullable=False),
        sa.Column("stop_reason", sa.String(32), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
    )
    op.create_index("ix_llm_calls_run_id", "llm_calls", ["run_id"])
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls")
    op.drop_index("ix_llm_calls_run_id", table_name="llm_calls")
    op.drop_table("llm_calls")
