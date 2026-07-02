"""Regression checks for status-board run selection.

Converted from backend/scripts/verify_status_board_regressions.py (2026-06-10).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from backend.app.services.run_timestamps import (
    completed_at_sql,
    mark_terminal_completed_at,
    stable_completed_at_from_state,
)
from backend.app.services.universe import latest_runs_sql as _build_latest_runs_sql


class TestStatusBoardSql(unittest.TestCase):

    def test_timestamp_idempotence(self) -> None:
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

    def test_completed_at_sql_expression(self) -> None:
        expr = completed_at_sql("r")
        assert "completed_at" in expr
        assert "created_at" in expr
        assert "updated_at" not in expr

    def test_sql_cte_structure(self) -> None:
        sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
        lower_sql = sql.lower()
        assert params == {}
        assert "with latest as" in lower_sql
        assert "distinct on (r.ticker, r.theme_id)" in lower_sql
        assert "updated_at" not in lower_sql

    def test_archived_filter_toggling(self) -> None:
        sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
        lower_sql = sql.lower()
        latest_idx = lower_sql.index("from latest")
        archived_idx = lower_sql.index("archived_at is null")
        assert archived_idx > latest_idx

        sql_with_archived, _ = _build_latest_runs_sql(
            theme_id="theme-1",
            include_archived=True,
        )
        assert "archived_at is null" not in sql_with_archived.lower()

    def test_status_filter_excludes_abandoned_runs(self) -> None:
        """The board keys on completed/watchlist only, so abandoned (and any
        other non-terminal) runs can never surface as a board entry."""
        sql, _ = _build_latest_runs_sql(theme_id=None, include_archived=False)
        lower_sql = sql.lower()
        assert "r.status in ('completed', 'watchlist')" in lower_sql
        assert "abandoned" not in lower_sql

    def test_theme_id_parameterization(self) -> None:
        # With theme_id: bind placeholder in SQL and value in params dict.
        sql_with_theme, params_with_theme = _build_latest_runs_sql(
            theme_id="theme-1",
            include_archived=False,
        )
        assert ":theme_id" in sql_with_theme
        assert params_with_theme == {"theme_id": "theme-1"}

        # Without theme_id: no placeholder in SQL and empty params dict.
        sql_no_theme, params_no_theme = _build_latest_runs_sql(
            theme_id=None,
            include_archived=False,
        )
        assert ":theme_id" not in sql_no_theme
        assert params_no_theme == {}


if __name__ == "__main__":
    unittest.main()
