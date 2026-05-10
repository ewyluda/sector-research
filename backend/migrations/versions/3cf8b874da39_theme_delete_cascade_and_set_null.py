"""theme delete cascade and set null

Revision ID: 3cf8b874da39
Revises: 8b4fd10f00d3
Create Date: 2026-05-10 14:22:50.327483

Enables `DELETE /api/themes/{id}` to succeed against non-empty themes.
- Theme-scoped data (signals, signal_history, surprise_alerts, watchlist) cascades.
- Research runs are preserved by SET NULL on theme_id (also drops the NOT NULL).
- The themes.parent_theme_id self-reference becomes SET NULL so deleting a parent
  promotes children to root rather than recursively deleting them.
- questions.theme_id was already SET NULL pre-existing — left untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3cf8b874da39'
down_revision: Union[str, None] = '8b4fd10f00d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CASCADE_TABLES = ("signals", "signal_history", "surprise_alerts", "watchlist")


def upgrade() -> None:
    # CASCADE on theme-scoped child tables.
    for tbl in CASCADE_TABLES:
        op.drop_constraint(f"{tbl}_theme_id_fkey", tbl, type_="foreignkey")
        op.create_foreign_key(
            f"{tbl}_theme_id_fkey", tbl, "themes",
            ["theme_id"], ["id"], ondelete="CASCADE",
        )

    # research_runs.theme_id: drop NOT NULL, switch to SET NULL.
    op.alter_column("research_runs", "theme_id", existing_type=sa.UUID(as_uuid=False), nullable=True)
    op.drop_constraint("research_runs_theme_id_fkey", "research_runs", type_="foreignkey")
    op.create_foreign_key(
        "research_runs_theme_id_fkey", "research_runs", "themes",
        ["theme_id"], ["id"], ondelete="SET NULL",
    )

    # themes.parent_theme_id: SET NULL on parent delete.
    op.drop_constraint("themes_parent_theme_id_fkey", "themes", type_="foreignkey")
    op.create_foreign_key(
        "themes_parent_theme_id_fkey", "themes", "themes",
        ["parent_theme_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    # Reverse parent_theme_id back to NO ACTION.
    op.drop_constraint("themes_parent_theme_id_fkey", "themes", type_="foreignkey")
    op.create_foreign_key(
        "themes_parent_theme_id_fkey", "themes", "themes",
        ["parent_theme_id"], ["id"],
    )

    # Reverse research_runs.theme_id. NOTE: this fails if any rows now have
    # theme_id IS NULL (which happens after a theme delete on the upgraded
    # schema). The downgrade is best-effort; backfill or hard-delete orphan
    # runs first if you need this to succeed.
    op.drop_constraint("research_runs_theme_id_fkey", "research_runs", type_="foreignkey")
    op.create_foreign_key(
        "research_runs_theme_id_fkey", "research_runs", "themes",
        ["theme_id"], ["id"],
    )
    op.alter_column("research_runs", "theme_id", existing_type=sa.UUID(as_uuid=False), nullable=False)

    # Reverse the four CASCADE child tables back to NO ACTION.
    for tbl in CASCADE_TABLES:
        op.drop_constraint(f"{tbl}_theme_id_fkey", tbl, type_="foreignkey")
        op.create_foreign_key(
            f"{tbl}_theme_id_fkey", tbl, "themes",
            ["theme_id"], ["id"],
        )
