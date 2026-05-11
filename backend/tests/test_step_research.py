import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.app.services.workspace_steps import step_research
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import ResearchOutput
from backend.app.services.transcript_delta import InsufficientTranscriptsError


def _patch_compute_delta(side_effect=None, return_value=None):
    """Convenience patcher for transcript_delta.compute_delta inside workspace_steps."""
    if side_effect is not None:
        mock = AsyncMock(side_effect=side_effect)
    else:
        mock = AsyncMock(return_value=return_value)
    return patch(
        "backend.app.services.transcript_delta.compute_delta",
        new=mock,
    )


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
        with _patch_compute_delta(side_effect=InsufficientTranscriptsError("no transcripts")):
            with patch("backend.app.services.workspace_steps.haiku_complete",
                       new=AsyncMock(return_value=haiku_response)):
                ctx = _make_ctx()
                out = await step_research(ctx)

        self.assertIsInstance(out, ResearchOutput)
        self.assertEqual(len(out.highlights), 2)
        self.assertEqual(out.highlights[0].classification, "confirms_thesis")
        self.assertEqual(len(out.new_open_questions), 1)

    async def test_haiku_failure_propagates(self):
        with _patch_compute_delta(side_effect=InsufficientTranscriptsError("no transcripts")):
            with patch("backend.app.services.workspace_steps.haiku_complete",
                       new=AsyncMock(side_effect=RuntimeError("anthropic 503"))):
                ctx = _make_ctx()
                with self.assertRaises(RuntimeError):
                    await step_research(ctx)

    async def test_delta_block_injected_into_new_sources(self):
        """When compute_delta returns populated axes, the block appears in the prompt."""
        delta_row = MagicMock()
        delta_row.axes = {
            "growth_earnings": {"direction": "softening", "magnitude": "material", "summary": "Rev guidance trimmed."},
            "risk_assessment": None,
        }
        haiku_response = json.dumps({
            "highlights": [{"text": "x", "classification": "confirms_thesis", "citation_id": None}],
            "new_open_questions": [],
            "summary": "ok",
        })
        captured_user: list[str] = []

        async def fake_haiku(*, system, user, anthropic):
            captured_user.append(user)
            return haiku_response

        with _patch_compute_delta(return_value=delta_row):
            with patch("backend.app.services.workspace_steps.haiku_complete", new=fake_haiku):
                ctx = _make_ctx()
                await step_research(ctx)

        self.assertTrue(captured_user, "haiku_complete was never called")
        self.assertIn("transcript-language deltas", captured_user[0])
        self.assertIn("growth_earnings", captured_user[0])
        self.assertNotIn("risk_assessment", captured_user[0])  # null axis omitted

    async def test_delta_failure_does_not_crash_step(self):
        """A generic exception from compute_delta is swallowed; step still runs."""
        haiku_response = json.dumps({
            "highlights": [{"text": "y", "classification": "new_unknown", "citation_id": None}],
            "new_open_questions": [],
            "summary": "fine",
        })
        with _patch_compute_delta(side_effect=RuntimeError("fmp outage")):
            with patch("backend.app.services.workspace_steps.haiku_complete",
                       new=AsyncMock(return_value=haiku_response)):
                ctx = _make_ctx()
                out = await step_research(ctx)
        self.assertIsInstance(out, ResearchOutput)


def _make_ctx():
    rr = MagicMock()
    rr.state = {
        "phase_outputs": {"thesis": {"content": "Long NVDA on data center demand."}},
        "questions_extracted": [{"question": "What is the HBM contract runway?"}],
    }
    return WorkspaceContext(
        run_id="r", ticker="NVDA",
        db=AsyncMock(), fmp=AsyncMock(), edgar=AsyncMock(), anthropic=AsyncMock(),
        prior_research_run=rr, prior_ticker_model=MagicMock(),
        emit=MagicMock(),
    )
