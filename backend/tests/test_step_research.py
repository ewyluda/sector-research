import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.workspace_steps import step_research
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import ResearchOutput


class TestStepResearch(unittest.IsolatedAsyncioTestCase):
    async def test_haiku_response_parsed(self):
        haiku_response = json.dumps({
            "highlights": [
                {"text": "Guidance raised on data center", "classification": "confirms_thesis", "citation_id": None},
                {"text": "New customer concentration risk", "classification": "threatens_thesis", "citation_id": None},
            ],
            "new_open_questions": [
                {"question": "What's the runway on the new HBM contract?", "classification": "growth"},
            ],
            "summary": "Q1 print broadly confirms thesis with one concentration concern.",
        })
        with patch("backend.app.services.workspace_steps.haiku_complete",
                   new=AsyncMock(return_value=haiku_response)):
            ctx = _make_ctx()
            out = await step_research(ctx)

        self.assertIsInstance(out, ResearchOutput)
        self.assertEqual(len(out.highlights), 2)
        self.assertEqual(out.highlights[0].classification, "confirms_thesis")
        self.assertEqual(len(out.new_open_questions), 1)

    async def test_haiku_failure_propagates(self):
        with patch("backend.app.services.workspace_steps.haiku_complete",
                   new=AsyncMock(side_effect=RuntimeError("anthropic 503"))):
            ctx = _make_ctx()
            with self.assertRaises(RuntimeError):
                await step_research(ctx)


def _make_ctx():
    rr = MagicMock()
    rr.state = {"thesis": {"summary_markdown": "Long NVDA on data center demand."}}
    return WorkspaceContext(
        run_id="r", ticker="NVDA",
        db=AsyncMock(), fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        prior_research_run=rr, prior_ticker_model=MagicMock(),
        emit=MagicMock(),
    )
