"""Tests for step_challenge: kill-criterion writeback + healthy verdict path."""
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.workspace_steps import step_challenge
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import ChallengeOutput, WorkspaceVerdict


def _make_ctx(kill_criteria=None, catalysts=None):
    rr = MagicMock()
    rr.id = "rr-1"
    # Kill criteria DEFINITIONS live at phase_outputs.thesis.structured.kill_criteria.
    # Each entry uses the KillCriterion shape (condition/threshold/monitoring_source),
    # but step_challenge also accepts 'description' as a fallback key.
    kc_defs = [
        {"condition": kc.get("description", ""), "threshold": "", "monitoring_source": ""}
        if isinstance(kc, dict) else kc
        for kc in (kill_criteria or [])
    ]
    rr.state = {
        "phase_outputs": {
            "thesis": {
                "content": "Long NVDA on AI capex supercycle",
                "structured": {"kill_criteria": kc_defs},
            }
        },
    }
    # DB returns no KillCriterionState rows and no Catalyst rows by default.
    db = AsyncMock()
    _empty_result = MagicMock()
    _empty_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=_empty_result)
    return WorkspaceContext(
        run_id="r",
        ticker="NVDA",
        db=db,
        fmp=AsyncMock(),
        edgar=AsyncMock(),
        anthropic=AsyncMock(),
        prior_research_run=rr,
        prior_ticker_model=MagicMock(),
        emit=MagicMock(),
    )


class TestStepChallenge(unittest.IsolatedAsyncioTestCase):

    async def test_writes_kill_criterion_flips(self):
        """Sonnet returns two kill criteria; both should land via upsert_kill_criterion_state."""
        sonnet_response = json.dumps({
            "stress_test_summary": "thesis intact; ordinal 2 now triggered",
            "kill_criterion_writes": [
                {"ordinal": 1, "status": "armed", "note": "no change"},
                {"ordinal": 2, "status": "triggered", "note": "concentration crossed 25%"},
            ],
            "catalyst_updates": [],
            "proposed_verdict": "broken",
        })
        with patch(
            "backend.app.services.workspace_steps.sonnet_complete",
            new=AsyncMock(return_value=sonnet_response),
        ), patch(
            "backend.app.services.workspace_steps.upsert_kill_criterion_state",
            new=AsyncMock(),
        ) as upsert_mock:
            ctx = _make_ctx(
                kill_criteria=[
                    {"ordinal": 1, "description": "Revenue growth < 10%"},
                    {"ordinal": 2, "description": "Customer concentration > 25%"},
                ]
            )
            out = await step_challenge(ctx)

        self.assertIsInstance(out, ChallengeOutput)
        self.assertEqual(out.proposed_verdict, WorkspaceVerdict.BROKEN)
        self.assertEqual(upsert_mock.await_count, 2)
        # Confirm ordinals passed correctly
        calls = upsert_mock.call_args_list
        ordinals = {c.kwargs["ordinal"] for c in calls}
        self.assertEqual(ordinals, {1, 2})

    async def test_no_kill_criteria_returns_healthy(self):
        """Empty state → no upserts called → healthy verdict returned."""
        sonnet_response = json.dumps({
            "stress_test_summary": "no material changes",
            "kill_criterion_writes": [],
            "catalyst_updates": [],
            "proposed_verdict": "healthy",
        })
        with patch(
            "backend.app.services.workspace_steps.sonnet_complete",
            new=AsyncMock(return_value=sonnet_response),
        ), patch(
            "backend.app.services.workspace_steps.upsert_kill_criterion_state",
            new=AsyncMock(),
        ) as upsert_mock:
            ctx = _make_ctx()
            out = await step_challenge(ctx)

        self.assertEqual(out.proposed_verdict, WorkspaceVerdict.HEALTHY)
        upsert_mock.assert_not_called()
        self.assertEqual(out.stress_test_summary, "no material changes")
