"""Tests for workspace-aware staleness in status_board._resolve_staleness."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from backend.app.services.status_board import _resolve_staleness


class TestStatusBoardWorkspaceAware(unittest.TestCase):
    def test_recent_workspace_unstales_old_research(self):
        now = datetime.now(timezone.utc)
        old_research = MagicMock()
        old_research.completed_at = now - timedelta(days=120)
        recent_workspace = MagicMock()
        recent_workspace.created_at = now - timedelta(days=10)

        is_stale, reason = _resolve_staleness(
            research_run=old_research,
            latest_workspace_run=recent_workspace,
            now=now,
        )
        self.assertFalse(is_stale)
        self.assertIsNone(reason)

    def test_no_workspace_old_research_is_stale(self):
        now = datetime.now(timezone.utc)
        old_research = MagicMock()
        old_research.completed_at = now - timedelta(days=120)

        is_stale, reason = _resolve_staleness(
            research_run=old_research,
            latest_workspace_run=None,
            now=now,
        )
        self.assertTrue(is_stale)
        self.assertIn("90", reason)


if __name__ == "__main__":
    unittest.main()
