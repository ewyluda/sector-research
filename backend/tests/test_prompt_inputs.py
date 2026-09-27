"""What the model actually receives: theme, date, price, full thesis, category
analyses, transcript passes, workspace evidence. Each of these reached the
prompt wrong (UUID, nothing, truncated, or a placeholder) before 2026-09-26."""
import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph import nodes  # noqa: E402
from backend.app.graph.formatters import fmt_price_line  # noqa: E402
from backend.app.graph.output_parser import extract_json_value  # noqa: E402
from backend.app.graph.state import CategoryResult, ResearchState  # noqa: E402
from backend.app.services.workspace_steps import (  # noqa: E402
    _render_model_deltas,
    _render_new_sources,
)


def _state(**kw) -> ResearchState:
    return ResearchState(ticker="SMCI", theme_id="2fa4ee2a-b652-47d9-8a29-9ec0a4a767d1", run_id="r", **kw)


class ThemeAndDateTests(unittest.TestCase):
    def test_theme_context_uses_name_and_bounded_description(self):
        s = _state(theme_name="Power & energy bottleneck", theme_description="Grid   limits\n" + "x" * 5000)
        ctx = nodes._theme_context(s)
        self.assertTrue(ctx.startswith("Power & energy bottleneck — Grid limits"))
        self.assertNotIn("2fa4ee2a", ctx)
        self.assertLessEqual(len(ctx), len("Power & energy bottleneck — ") + nodes.THEME_DESCRIPTION_BUDGET_CHARS)

    def test_theme_context_for_old_runs_without_a_name(self):
        self.assertEqual(nodes._theme_context(_state()), "(theme not recorded for this run)")

    def test_as_of_is_today(self):
        self.assertEqual(nodes._as_of(), date.today().isoformat())

    def test_old_persisted_state_still_loads(self):
        d = _state().to_dict()
        d.pop("theme_name")
        d.pop("theme_description")
        self.assertEqual(ResearchState.from_dict(d).theme_name, "")


class PriceTests(unittest.TestCase):
    def test_price_line(self):
        self.assertEqual(fmt_price_line({"price": 299.96, "range": "95.1-310.2"}),
                         "Price: $299.96 (52-week range $95.1-310.2)")
        self.assertIsNone(fmt_price_line({"price": 0}))
        self.assertIsNone(fmt_price_line({}))

    def test_market_block_with_negative_dcf(self):
        s = _state(curated_financials={
            "current_price": 29.84, "fifty_two_week_low": 19.48, "fifty_two_week_high": 62.36,
            "dcf_intrinsic_value": -60.37,
            "daily_prices": [{"sma_50": 32.57, "sma_200": 35.67, "rsi": 40.6}],
        })
        block = nodes._market_data_block(s)
        self.assertIn("Current price: $29.84", block)
        self.assertIn("52-week range: $19.48 – $62.36", block)
        self.assertIn("SMA50 $32.57", block)
        self.assertIn("FMP DCF value: n/m", block)

    def test_market_block_without_price(self):
        self.assertEqual(nodes._market_data_block(_state()), "(no current price available)")


class RiskPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_risk_step_sees_full_thesis_and_price(self):
        thesis = "core " * 600 + "BEAR-CASE-SENTINEL " + "kill " * 1500 + "KILL-CRITERIA-SENTINEL"
        s = _state(
            theme_name="Neo-clouds",
            curated_financials={"current_price": 50.0},
            phase_outputs={"thesis": {"content": thesis}},
        )
        fake = AsyncMock(return_value="not json")
        with patch.object(nodes, "complete", fake):
            await nodes.node_risk_stress_test(s)
        user = fake.call_args.kwargs["user"]
        self.assertIn("BEAR-CASE-SENTINEL", user)
        self.assertIn("KILL-CRITERIA-SENTINEL", user)
        self.assertIn("Current price: $50.00", user)
        self.assertIn("Theme: Neo-clouds", user)


class ThesisCategoryTextTests(unittest.TestCase):
    def test_thesis_reads_the_analysis_not_the_json_head(self):
        r = CategoryResult(
            category="Financial Health", content='{"score": 28, ' + "x" * 5000, score=28,
            structured={"score_rationale": "Liquidity gap.", "analysis": "ANALYSIS-SENTINEL",
                        "data_gaps": ["revolver capacity"]},
        )
        text = nodes._category_analysis_text(r)
        self.assertIn("ANALYSIS-SENTINEL", text)
        self.assertIn("Data gaps: revolver capacity", text)
        self.assertNotIn('{"score"', text)


class ExtractJsonTests(unittest.TestCase):
    def test_fenced_and_preamble_and_trailing_note(self):
        self.assertEqual(extract_json_value('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(
            extract_json_value('I notice the transcript is cut off. [note]\n```json\n[{"a": 1}]\n```\nHope this helps {x}'),
            [{"a": 1}],
        )

    def test_no_json(self):
        self.assertIsNone(extract_json_value("The transcript appears to be empty."))


class TranscriptPassTests(unittest.IsolatedAsyncioTestCase):
    async def test_fenced_pass_output_is_parsed_not_stored_as_string(self):
        from backend.app.services.transcript_analysis import run_transcript_analysis
        fake = AsyncMock(return_value='```json\n{"claims": ["capex up"]}\n```')
        with patch("backend.app.graph.llm.complete", fake):
            res = await run_transcript_analysis(
                "NVDA", [{"content": "Question: capex? data center investment billion"}], fmp=None,
            )
        self.assertEqual(res.status, "ok")
        self.assertEqual(res.value["pass1_claims"], {"claims": ["capex up"]})
        self.assertIsInstance(res.value["pass4_validation"], dict)


class WorkspaceChallengeEvidenceTests(unittest.TestCase):
    def test_model_deltas_rendered_from_refresh_output(self):
        out = _render_model_deltas({
            "changed_cells": [{"cell_path": "income_statement.revenue.2026Q2", "prior_value": 1.0,
                               "new_value": 1.2, "source": "historical"}],
            "consensus_delta": [{"metric": "eps", "period": "2027", "prior_consensus": 2.0, "new_consensus": 2.3}],
        })
        self.assertIn("income_statement.revenue.2026Q2: 1.0 -> 1.2 (historical)", out)
        self.assertIn("consensus eps 2027: 2.0 -> 2.3", out)
        self.assertNotIn("see step_outputs", out)

    def test_skipped_and_failed_refresh(self):
        self.assertIn("skipped", _render_model_deltas({"model_skipped": True}))
        self.assertIn("unavailable", _render_model_deltas({"error": "boom"}))

    def test_new_sources_from_filings_and_research(self):
        out = _render_new_sources(
            {"new_filings": [{"form": "10-Q", "accession": "0001-26-000123"}]},
            {"highlights": [{"text": "Backlog doubled", "classification": "confirms_thesis"}],
             "summary": "Demand intact."},
        )
        self.assertIn("New filing: 10-Q 0001-26-000123", out)
        self.assertIn("[confirms_thesis] Backlog doubled", out)
        self.assertIn("Research summary: Demand intact.", out)


if __name__ == "__main__":
    unittest.main()
