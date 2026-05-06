"""Regression checks for status-board run selection.

Usage from project root:
    PYTHONPATH=. python backend/scripts/verify_status_board_regressions.py
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.app.services.run_timestamps import (
    completed_at_sql,
    mark_terminal_completed_at,
    stable_completed_at_from_state,
)
from backend.app.services.status_board import _build_latest_runs_sql


def main() -> None:
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first_completed_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    later_mutation_at = datetime(2026, 2, 1, tzinfo=timezone.utc)

    state: dict = {}
    mark_terminal_completed_at(state, first_completed_at)
    assert state["completed_at"] == first_completed_at.isoformat()
    mark_terminal_completed_at(state, later_mutation_at)
    assert state["completed_at"] == first_completed_at.isoformat()
    assert stable_completed_at_from_state(state, later_mutation_at) == first_completed_at
    assert stable_completed_at_from_state({}, created_at) == created_at

    expr = completed_at_sql("r")
    assert "completed_at" in expr
    assert "created_at" in expr
    assert "updated_at" not in expr

    sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
    lower_sql = sql.lower()
    assert params == {}
    assert "with latest as" in lower_sql
    assert "distinct on (r.ticker, r.theme_id)" in lower_sql
    assert "updated_at" not in lower_sql

    latest_idx = lower_sql.index("from latest")
    archived_idx = lower_sql.index("archived_at is null")
    assert archived_idx > latest_idx

    sql_with_archived, _ = _build_latest_runs_sql(
        theme_id="theme-1",
        include_archived=True,
    )
    assert "archived_at IS NULL" not in sql_with_archived

    print("status-board regression checks passed")


if __name__ == "__main__":
    main()
