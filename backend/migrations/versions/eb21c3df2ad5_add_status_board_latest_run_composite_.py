"""add status board latest run composite index

Revision ID: eb21c3df2ad5
Revises: a2c6676dd30d
Create Date: 2026-06-11 01:57:25.426130
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'eb21c3df2ad5'
down_revision: Union[str, None] = '77bcb5d1bfbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The status-board DISTINCT ON query orders by:
    #   (ticker, theme_id, COALESCE((state->>'completed_at')::timestamptz, created_at) DESC, created_at DESC)
    # The COALESCE expression involves a ::timestamptz cast which is STABLE (not
    # IMMUTABLE), so Postgres cannot use it directly in an expression index.
    # Instead we index (ticker, theme_id, created_at DESC) with a partial WHERE
    # matching the query's filter. This lets the planner use an index scan to
    # narrow to the relevant status/theme_id partition and then sort cheaply;
    # the COALESCE tiebreak is applied on the filtered rows, not the full table.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_research_runs_status_board_latest
        ON research_runs (ticker, theme_id, created_at DESC)
        WHERE status IN ('completed', 'watchlist')
          AND theme_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_research_runs_status_board_latest")
