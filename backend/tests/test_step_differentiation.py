import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.workspace_steps import step_differentiation
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import DifferentiationOutput, PeerCompTable, PeerCompRow


class TestStepDifferentiation(unittest.IsolatedAsyncioTestCase):
    async def test_no_resolved_peers_returns_empty_table(self):
        with patch("backend.app.services.workspace_steps._fetch_resolved_peers",
                   new=AsyncMock(return_value=[])), \
             patch("backend.app.services.workspace_steps._fetch_read_throughs_for_ticker",
                   new=AsyncMock(return_value=[])):
            ctx = _make_ctx()
            out = await step_differentiation(ctx)

        self.assertIsInstance(out, DifferentiationOutput)
        self.assertIsNone(out.peer_comp)
        self.assertEqual(out.read_throughs, [])

    async def test_with_peers_builds_table(self):
        focus = "NVDA"
        peers = ["AMD", "INTC", "MU"]
        with patch("backend.app.services.workspace_steps._fetch_resolved_peers",
                   new=AsyncMock(return_value=peers)), \
             patch("backend.app.services.workspace_steps._fetch_read_throughs_for_ticker",
                   new=AsyncMock(return_value=[{"event_key": "earnings:AMD:2026-Q1"}])), \
             patch("backend.app.services.workspace_steps.build_peer_comp_table",
                   new=AsyncMock(return_value=(_fake_table(focus, peers), []))):
            ctx = _make_ctx(ticker=focus)
            out = await step_differentiation(ctx)

        self.assertIsNotNone(out.peer_comp)
        self.assertEqual(out.peer_comp.focus_ticker, focus)
        self.assertEqual(len(out.read_throughs), 1)


def _make_ctx(ticker: str = "NVDA"):
    prior_run = MagicMock()
    prior_run.id = "test_run_id"
    return WorkspaceContext(
        run_id="r", ticker=ticker,
        db=AsyncMock(), fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        prior_research_run=prior_run, prior_ticker_model=MagicMock(),
        emit=MagicMock(),
    )


def _fake_table(focus, peers):
    return PeerCompTable(
        focus_ticker=focus,
        rows=[PeerCompRow(ticker=t) for t in [focus] + peers],
        median=PeerCompRow(ticker="__median__"),
        delta_vs_median_pct=PeerCompRow(ticker="__delta__"),
    )
