import unittest
from unittest.mock import MagicMock
from backend.app.services.workspace_context import WorkspaceContext


class TestWorkspaceContext(unittest.TestCase):
    def test_context_constructs(self):
        ctx = WorkspaceContext(
            run_id="run-1",
            ticker="NVDA",
            db=MagicMock(),
            fmp=MagicMock(),
            edgar=MagicMock(),
            anthropic=MagicMock(),
            prior_research_run=MagicMock(),
            prior_ticker_model=MagicMock(),
            emit=MagicMock(),
        )
        self.assertEqual(ctx.ticker, "NVDA")

    def test_emit_is_callable(self):
        emit = MagicMock()
        ctx = WorkspaceContext(
            run_id="r", ticker="X", db=MagicMock(), fmp=MagicMock(),
            edgar=MagicMock(), anthropic=MagicMock(),
            prior_research_run=MagicMock(), prior_ticker_model=MagicMock(),
            emit=emit,
        )
        ctx.emit({"type": "step_start", "step": "update_refresh"})
        emit.assert_called_once()
