"""The LLM call layer: native structured outputs, stop_reason handling, the
no-prefill guard, and quick-screen verdicts derived in code."""
import json
import os
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

import anthropic  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from backend.app.graph import llm  # noqa: E402
from backend.app.graph.llm import LLMOutputError, complete, complete_structured  # noqa: E402
from backend.app.graph.state import ResearchState  # noqa: E402
from backend.app.models.citation import Citation  # noqa: E402
from backend.app.models.phase_schemas import (  # noqa: E402
    QUICK_SCREEN_DIMENSIONS,
    QuickScreenOutput,
    TargetedAnswer,
    quick_screen_recommendation,
)

_USAGE = SimpleNamespace(
    input_tokens=10, output_tokens=5,
    cache_read_input_tokens=0, cache_creation_input_tokens=0,
)


def _fake_client(*, parse_result=None, create_result=None) -> MagicMock:
    client = MagicMock()
    client.messages.parse = AsyncMock(return_value=parse_result)
    client.messages.create = AsyncMock(return_value=create_result)
    return client


class CompleteStructuredTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _msg(stop_reason: str, text: str | None) -> SimpleNamespace:
        content = [SimpleNamespace(type="thinking", thinking="")]
        if text is not None:
            content.append(SimpleNamespace(type="text", text=text))
        return SimpleNamespace(stop_reason=stop_reason, content=content, usage=_USAGE)

    async def test_returns_validated_model_and_sends_schema(self):
        client = _fake_client(create_result=self._msg("end_turn", '{"answer_text": "RPO grew 3x."}'))
        with patch.object(llm, "get_client", return_value=client):
            out = await complete_structured(system="s", user="u", output_model=TargetedAnswer)
        self.assertEqual(out, TargetedAnswer(answer_text="RPO grew 3x."))
        kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertIn("answer_text", kwargs["output_config"]["format"]["schema"]["properties"])
        # A trailing assistant turn is a prefill — never sent.
        self.assertEqual([m["role"] for m in kwargs["messages"]], ["user"])

    async def test_over_length_output_is_clamped_not_failed(self):
        # Live 2026-09-27 (VRT): maxItems is only a hint, and Haiku appended a
        # sixth, empty dimension, which failed the whole quick screen.
        dims = [{"name": n, "score": 12, "rationale": "r" * 450} for n in QUICK_SCREEN_DIMENSIONS]
        dims.append({"name": "Valuation", "score": 20, "rationale": ""})
        raw = json.dumps({"overall_score": 60, "recommendation": "GO", "dimensions": dims,
                          "thesis": "t", "key_risk": "k"})
        client = _fake_client(create_result=self._msg("end_turn", raw))
        with patch.object(llm, "get_client", return_value=client):
            out = await complete_structured(system="s", user="u", output_model=QuickScreenOutput)
        self.assertEqual([d.name for d in out.dimensions], list(QUICK_SCREEN_DIMENSIONS))
        self.assertEqual(len(out.dimensions[0].rationale), 400)

    async def test_too_short_output_still_fails(self):
        raw = json.dumps({"overall_score": 60, "recommendation": "GO", "dimensions": [],
                          "thesis": "t", "key_risk": "k"})
        client = _fake_client(create_result=self._msg("end_turn", raw))
        with patch.object(llm, "get_client", return_value=client), self.assertRaises(ValidationError):
            await complete_structured(system="s", user="u", output_model=QuickScreenOutput)

    def test_dimension_names_are_a_schema_enum(self):
        schema = anthropic.transform_schema(QuickScreenOutput)
        name = schema["$defs"]["QuickScreenDimension"]["properties"]["name"]
        self.assertEqual(name["enum"], list(QUICK_SCREEN_DIMENSIONS))

    async def test_truncation_raises_before_json_parsing(self):
        # Truncated JSON must surface as "truncated", not a parse error.
        msg = self._msg("max_tokens", '{"answer_text": "RPO gr')
        with patch.object(llm, "get_client", return_value=_fake_client(create_result=msg)):
            with self.assertRaisesRegex(LLMOutputError, "max_tokens"):
                await complete_structured(system="s", user="u", output_model=TargetedAnswer)

    async def test_refusal_raises(self):
        msg = self._msg("refusal", None)
        with patch.object(llm, "get_client", return_value=_fake_client(create_result=msg)):
            with self.assertRaisesRegex(LLMOutputError, "refused"):
                await complete_structured(system="s", user="u", output_model=TargetedAnswer)

    async def test_missing_text_raises(self):
        msg = self._msg("end_turn", None)
        with patch.object(llm, "get_client", return_value=_fake_client(create_result=msg)):
            with self.assertRaises(LLMOutputError):
                await complete_structured(system="s", user="u", output_model=TargetedAnswer)

    async def test_thinking_tier_sends_effort_alongside_format(self):
        client = _fake_client(create_result=self._msg("end_turn", '{"answer_text": "x"}'))
        with patch.object(llm, "get_client", return_value=client):
            await complete_structured(system="s", user="u", output_model=TargetedAnswer, model="claude-opus-5-5")
        cfg = client.messages.create.call_args.kwargs["output_config"]
        self.assertEqual(cfg["effort"], "medium")
        self.assertIn("format", cfg)

    async def test_complete_joins_text_blocks_only(self):
        msg = SimpleNamespace(
            stop_reason="end_turn", usage=_USAGE,
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text="Hello "),
                SimpleNamespace(type="text", text="world"),
            ],
        )
        with patch.object(llm, "get_client", return_value=_fake_client(create_result=msg)):
            self.assertEqual(await complete(system="s", user="u"), "Hello world")


class RequestParamsTests(unittest.TestCase):
    def test_fast_tier_gets_no_effort(self):
        # Haiku 4.5 rejects output_config.effort.
        self.assertEqual(llm._request_params("claude-haiku-4-5-20251001", 600), {"max_tokens": 600})

    def test_thinking_tier_gets_effort_and_headroom(self):
        params = llm._request_params("claude-opus-5-5", 600)
        self.assertEqual(params["output_config"], {"effort": "medium"})
        self.assertGreaterEqual(params["max_tokens"], llm.THINKING_MIN_MAX_TOKENS)


class NoPrefillGuardTests(unittest.TestCase):
    """Sonnet 4.6+ rejects assistant prefill with a 400. The lesson was found on
    2026-04-11 and reintroduced at five call sites because it lived only in a
    commit message — this guard makes it a test failure instead."""

    def test_complete_has_no_prefill_parameter(self):
        import inspect
        self.assertNotIn("assistant_prefill", inspect.signature(complete).parameters)

    def test_no_app_code_passes_assistant_prefill(self):
        app = pathlib.Path(__file__).resolve().parents[1] / "app"
        offenders = [
            str(p.relative_to(app)) for p in app.rglob("*.py")
            if "assistant_prefill=" in p.read_text()
        ]
        self.assertEqual(offenders, [])


class QuickScreenLadderTests(unittest.TestCase):
    def test_ladder_boundaries(self):
        self.assertEqual(quick_screen_recommendation(60), "GO")
        self.assertEqual(quick_screen_recommendation(59), "WATCHLIST")
        self.assertEqual(quick_screen_recommendation(35), "WATCHLIST")
        self.assertEqual(quick_screen_recommendation(34), "PASS")


def _quick_screen_output(dim_scores: list[int], overall: int, rec: str) -> QuickScreenOutput:
    return QuickScreenOutput(
        overall_score=overall,
        recommendation=rec,
        dimensions=[
            {"name": n, "score": s, "max_score": 20, "rationale": "r"}
            for n, s in zip(QUICK_SCREEN_DIMENSIONS, dim_scores)
        ],
        thesis="t",
        key_risk="k",
    )


class QuickScreenNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_verdict_comes_from_dimension_sum_not_model_total(self):
        # Real case (RKLB 2026-04-13): dimensions summed to 61 but the model
        # reported 42/WATCHLIST. The ladder applied in code says GO.
        from backend.app.graph import nodes

        cit = Citation(value="X", metric="m", source_name="FMP", source_url="u", tier=1)
        fmp = MagicMock()
        for meth in ("get_income_statement", "get_balance_sheet", "get_cash_flow", "get_company_profile"):
            setattr(fmp, meth, AsyncMock(return_value=([], cit)))
        fake = AsyncMock(return_value=_quick_screen_output([13, 12, 12, 12, 12], 42, "WATCHLIST"))
        state = ResearchState(ticker="RKLB", theme_id="t", run_id="r")
        with patch.object(nodes, "complete_structured", fake):
            state = await nodes.node_quick_screen(state, fmp)

        qs = state.phase_outputs["quick_screen"]
        self.assertEqual(qs["score"], 61)
        self.assertEqual(qs["recommendation"], "GO")
        self.assertEqual(qs["structured"]["overall_score"], 61)
        self.assertEqual(qs["model_overall_score"], 42)
        self.assertEqual(state.status, "in_progress")


if __name__ == "__main__":
    unittest.main()
