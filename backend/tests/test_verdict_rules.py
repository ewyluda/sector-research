"""Verdict rules that live in code, not in the prompt: the directional call,
reward/risk from the thesis's own targets, and the risk loop-back policy."""
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from pydantic import ValidationError  # noqa: E402

from backend.app.graph import nodes  # noqa: E402
from backend.app.graph.llm import LLMOutputError  # noqa: E402
from backend.app.graph.routing import MAX_RISK_LOOPS, should_loop  # noqa: E402
from backend.app.graph.state import ResearchState  # noqa: E402
from backend.app.models.phase_schemas import (  # noqa: E402
    PriceTargets,
    RiskStressTestOutput,
    reward_risk,
)


class RewardRiskTests(unittest.TestCase):
    T = PriceTargets(bear=20, base=45, bull=60)

    def test_long_and_short(self):
        self.assertEqual(reward_risk("long", 30, self.T), 1.5)    # (45-30)/(30-20)
        self.assertEqual(reward_risk("short", 50, self.T), 0.5)   # (50-45)/(60-50)
        self.assertEqual(reward_risk("short", 30, self.T), 0.0)   # base above price: no reward

    def test_undefined_cases(self):
        self.assertIsNone(reward_risk("avoid", 30, self.T))
        self.assertIsNone(reward_risk("long", None, self.T))
        self.assertIsNone(reward_risk("long", 15, self.T))        # price below bear case
        self.assertIsNone(reward_risk("long", 30, None))

    def test_targets_must_be_ordered(self):
        with self.assertRaises(ValidationError):
            PriceTargets(bear=50, base=40, bull=60)


class ShouldLoopTests(unittest.TestCase):
    def test_loops_when_model_asks_and_rr_is_weak(self):
        self.assertTrue(should_loop(model_wants_loop=True, categories=["Financial Health"], loop_count=0, rr=1.4))
        self.assertTrue(should_loop(model_wants_loop=True, categories=["Financial Health"], loop_count=0, rr=None))

    def test_no_loop_when_rr_already_comfortable(self):
        self.assertFalse(should_loop(model_wants_loop=True, categories=["Financial Health"], loop_count=0, rr=2.8))

    def test_cap_and_empty_categories(self):
        self.assertFalse(should_loop(model_wants_loop=True, categories=["X"], loop_count=MAX_RISK_LOOPS, rr=1.0))
        self.assertFalse(should_loop(model_wants_loop=True, categories=[], loop_count=0, rr=1.0))
        self.assertFalse(should_loop(model_wants_loop=False, categories=["X"], loop_count=0, rr=1.0))


def _risk_output(rr=1.4, loop=True, cats=("Financial Health",)) -> RiskStressTestOutput:
    risk = {"risk": "r", "category": "Valuation", "probability": "Medium", "impact": "-10%", "mitigation": "m"}
    return RiskStressTestOutput(
        risks=[risk] * 3, rr_ratio=rr, rr_verdict="v",
        loop_required=loop, loop_categories=list(cats), loop_reason="gap",
    )


def _state(stance="long", price=30.0, loop_count=0) -> ResearchState:
    thesis = {"stance": stance, "time_horizon": "12 months",
              "price_targets": {"bear": 20.0, "base": 60.0, "bull": 80.0}}
    return ResearchState(
        ticker="SMCI", theme_id="t", run_id="r", loop_count=loop_count,
        curated_financials={"current_price": price},
        phase_outputs={"thesis": {"content": "{}", "structured": thesis}},
    )


class RiskNodeTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, state, output):
        with patch.object(nodes, "complete_structured", AsyncMock(return_value=output)):
            return await nodes.node_risk_stress_test(state)

    async def test_computed_rr_overrides_model_estimate_and_blocks_loop(self):
        # long at 30, base 60, bear 20 -> 3.0:1 from the thesis's own targets.
        s = await self._run(_state(), _risk_output(rr=1.4, loop=True))
        risk = s.phase_outputs["risk"]
        self.assertEqual(risk["rr_ratio"], 3.0)
        self.assertEqual(risk["rr_source"], "thesis_targets")
        self.assertEqual(risk["model_rr_ratio"], 1.4)
        self.assertFalse(risk["loop_required"])
        self.assertEqual(s.status, "completed")

    async def test_loop_runs_when_rr_is_weak(self):
        s = await self._run(_state(price=55.0), _risk_output(loop=True))  # (60-55)/(55-20)
        self.assertEqual(s.status, "in_progress")
        self.assertEqual(s.loop_count, 1)
        self.assertEqual(s.loop_context["categories"], ["Financial Health"])

    async def test_unknown_categories_are_dropped(self):
        s = await self._run(_state(price=55.0), _risk_output(loop=True, cats=("Vibes",)))
        self.assertEqual(s.status, "completed")
        self.assertEqual(s.phase_outputs["risk"]["loop_categories"], [])

    async def test_cap_with_open_gaps_ends_as_watchlist(self):
        s = await self._run(_state(price=55.0, loop_count=MAX_RISK_LOOPS), _risk_output(loop=True))
        self.assertEqual(s.status, "watchlist")
        self.assertEqual(s.thesis_status, "DRIFTING")


class ThesisNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_thesis_is_an_error_not_an_invented_score(self):
        s = ResearchState(ticker="CORZ", theme_id="t", run_id="r")
        fake = AsyncMock(side_effect=LLMOutputError("truncated at max_tokens"))
        with patch.object(nodes, "complete_structured", fake):
            s = await nodes.node_thesis_construction(s)
        self.assertEqual(s.status, "error")
        self.assertEqual(s.phase_outputs["thesis"]["__type__"], "PhaseError")
        self.assertEqual(s.conviction_score, 0)


if __name__ == "__main__":
    unittest.main()
