"""Pins behaviour of the seven per-category context builders lifted out
of `node_deep_dive`. Counterparty gets exhaustive coverage because its
output format is documented as a prompt contract in CLAUDE.md; the
other six get the empty/routed/unrouted/one-edge matrix the spec asks
for, with the snapshot diff providing the rest of the safety net.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.graph.deep_dive_context import (
    DeepDiveContext,
    build_all_contexts,
    build_counterparty_context,
    build_edgar_context,
    build_filing_excerpt_context,
    build_macro_context,
    build_quant_context,
    build_sentiment_context,
    build_technical_context,
    build_transcript_context,
)
from backend.app.services.relationship_context import (
    CounterpartyContext,
    CounterpartyEntry,
)


def _ctx(**overrides) -> DeepDiveContext:
    """Convenience: empty-context with overrides applied."""
    defaults = dict(
        ticker="ORCL",
        categories=[],
        transcript_analysis=None,
        curated_financials=None,
        signals=None,
        edgar_facts=None,
        filing_sections=None,
        counterparty_context=None,
    )
    defaults.update(overrides)
    return DeepDiveContext(**defaults)


# ── transcript ──────────────────────────────────────────────────────────────


class BuildTranscriptContextTests(unittest.TestCase):
    def test_empty_when_no_transcript(self):
        self.assertEqual(build_transcript_context(_ctx(), "Business Quality"), "")

    def test_empty_when_transcript_is_string(self):
        # When analysis fails, state.transcript_analysis is set to a string
        # (skip marker). Don't try to .get() into it.
        ctx = _ctx(transcript_analysis="no transcripts available")
        self.assertEqual(build_transcript_context(ctx, "Management & Governance"), "")

    def test_empty_when_category_unrouted(self):
        ctx = _ctx(transcript_analysis={"pass1_claims": {"x": 1}})
        # "Technical & Market Structure" is not in TRANSCRIPT_ROUTING.
        self.assertEqual(build_transcript_context(ctx, "Technical & Market Structure"), "")

    def test_routed_category_renders_pass(self):
        ctx = _ctx(
            transcript_analysis={
                "pass3_qa_tensions": {"tension": "guidance vs reality"},
                "pass5_consistency": {"score": 0.7},
            }
        )
        out = build_transcript_context(ctx, "Business Quality")
        self.assertIn("Earnings transcript analysis:", out)
        self.assertIn("[Transcript: pass3_qa_tensions]", out)
        self.assertIn("[Transcript: pass5_consistency]", out)
        self.assertIn('"tension": "guidance vs reality"', out)


# ── macro ───────────────────────────────────────────────────────────────────


class BuildMacroContextTests(unittest.TestCase):
    def test_empty_when_no_curated(self):
        self.assertEqual(build_macro_context(_ctx(), "Macro & Regime"), "")

    def test_empty_when_no_macro_block(self):
        ctx = _ctx(curated_financials={"other_key": 1})
        self.assertEqual(build_macro_context(ctx, "Macro & Regime"), "")

    def test_empty_when_category_unrouted(self):
        ctx = _ctx(curated_financials={"macro_indicators": {"cpi": [{"date": "2024-01-01", "value": 3.1}]}})
        # "Sentiment & Narrative" not in MACRO_ROUTING.
        self.assertEqual(build_macro_context(ctx, "Sentiment & Narrative"), "")

    def test_routed_skips_empty_series(self):
        # Edge case from spec: skip series whose points is empty
        ctx = _ctx(
            curated_financials={
                "macro_indicators": {
                    "fed_funds_rate": [],
                    "cpi": [{"date": "2024-01-01", "value": 3.1}],
                }
            }
        )
        out = build_macro_context(ctx, "Macro & Regime")
        self.assertIn("cpi: latest=3.1 (2024-01-01)", out)
        self.assertNotIn("fed_funds_rate", out)


# ── technical ───────────────────────────────────────────────────────────────


class BuildTechnicalContextTests(unittest.TestCase):
    def test_empty_when_wrong_category(self):
        ctx = _ctx(curated_financials={"daily_prices": [{"date": "2024-01-01", "close": 100}]})
        self.assertEqual(build_technical_context(ctx, "Business Quality"), "")

    def test_empty_when_no_prices(self):
        ctx = _ctx(curated_financials={"daily_prices": []})
        self.assertEqual(build_technical_context(ctx, "Technical & Market Structure"), "")

    def test_routed_renders_summary_and_table(self):
        prices = [
            {
                "date": f"2024-01-{i:02d}",
                "close": 100 + i,
                "volume": 1_000_000,
                "sma_9": 99,
                "sma_20": 98,
                "sma_50": 95,
                "sma_100": 92,
                "sma_200": 90,
                "rsi": 55,
            }
            for i in range(1, 25)
        ]
        ctx = _ctx(curated_financials={"daily_prices": prices})
        out = build_technical_context(ctx, "Technical & Market Structure")
        self.assertIn("Technical indicators (computed from 1Y daily OHLCV):", out)
        self.assertIn("RSI(14): 55", out)
        # 20-row table + 1 header
        self.assertEqual(out.count("\n2024-01-"), 20)


# ── sentiment ───────────────────────────────────────────────────────────────


class BuildSentimentContextTests(unittest.TestCase):
    def test_empty_when_wrong_category(self):
        ctx = _ctx(signals={"velocity": {"ratio": 1.2}})
        self.assertEqual(build_sentiment_context(ctx, "Business Quality"), "")

    def test_empty_when_no_signals(self):
        self.assertEqual(build_sentiment_context(_ctx(), "Sentiment & Narrative"), "")

    def test_empty_when_signals_present_but_all_non_dict(self):
        # Header would be added but every signal entry is missing/invalid.
        ctx = _ctx(signals={"velocity": None, "narrative": "string", "discovery": 42})
        self.assertEqual(build_sentiment_context(ctx, "Sentiment & Narrative"), "")

    def test_routed_renders_all_three_signal_types(self):
        ctx = _ctx(
            signals={
                "velocity": {"ratio": 1.5, "direction": "up", "count_7d": 50, "count_30d_approx": 30},
                "narrative": {"post_count": 75, "summary": "bullish on AI"},
                "discovery": {"score": 0.8, "co_mentions_7d": 10, "total_theme_mentions_7d": 100},
            }
        )
        out = build_sentiment_context(ctx, "Sentiment & Narrative")
        self.assertIn("X social signal", out)
        self.assertIn("Velocity: ratio=1.5", out)
        self.assertIn("Narrative: post_count=75 summary=bullish on AI", out)
        self.assertIn("Discovery: score=0.8", out)


# ── edgar ───────────────────────────────────────────────────────────────────


class BuildEdgarContextTests(unittest.TestCase):
    def test_empty_when_category_unrouted(self):
        # "Business Quality" not in EDGAR_ROUTING.
        ctx = _ctx(edgar_facts={"us-gaap:LongTermDebt": [{"value": 1e9, "unit": "USD"}]})
        self.assertEqual(build_edgar_context(ctx, "Business Quality"), "")

    def test_empty_when_no_facts_dict(self):
        # Routed category but no facts at all → all concepts missing →
        # renders the missing line (NOT empty). This is the spec edge
        # case: present/missing partition.
        out = build_edgar_context(_ctx(), "Financial Health")
        self.assertIn("Not disclosed in XBRL:", out)

    def test_routed_present_and_missing_partition(self):
        # Mix: some concepts have data, some don't. Spec edge case.
        ctx = _ctx(
            edgar_facts={
                "us-gaap:LongTermDebt": [
                    {
                        "value": 5_000_000_000,
                        "unit": "USD",
                        "fiscal_year": 2024,
                        "fiscal_period": "Q4",
                        "period_start": "2024-10-01",
                        "period_end": "2024-12-31",
                    }
                ]
            }
        )
        out = build_edgar_context(ctx, "Financial Health")
        self.assertIn("SEC EDGAR XBRL facts", out)
        self.assertIn("LongTermDebt", out)
        self.assertIn("$5.00B", out)
        self.assertIn("Not disclosed in XBRL:", out)


# ── filing excerpts ─────────────────────────────────────────────────────────


class BuildFilingExcerptContextTests(unittest.TestCase):
    def test_empty_when_category_unrouted(self):
        ctx = _ctx(filing_sections={"item_1_business": {"text": "..."}})
        # "Macro & Regime" not in FILING_EXCERPT_ROUTING.
        self.assertEqual(build_filing_excerpt_context(ctx, "Macro & Regime"), "")

    def test_empty_when_no_sections(self):
        self.assertEqual(build_filing_excerpt_context(_ctx(), "Business Quality"), "")

    def test_routed_renders_header_and_text(self):
        ctx = _ctx(
            filing_sections={
                "item_1_business": {
                    "text": "We make databases.",
                    "heading": "Business",
                    "form_type": "10-K",
                    "filing_date": "2024-06-30",
                }
            }
        )
        out = build_filing_excerpt_context(ctx, "Business Quality")
        self.assertIn("[10-K · 2024-06-30 · Business]", out)
        self.assertIn("We make databases.", out)
        self.assertNotIn("truncated", out)

    def test_truncation_header_when_over_budget(self):
        # Spec edge case: truncate at FILING_EXCERPT_BUDGET_CHARS, add (truncated to N chars).
        from backend.app.graph.deep_dive_routing import FILING_EXCERPT_BUDGET_CHARS

        ctx = _ctx(
            filing_sections={
                "item_1_business": {
                    "text": "x" * (FILING_EXCERPT_BUDGET_CHARS + 100),
                    "heading": "Business",
                    "form_type": "10-K",
                    "filing_date": "2024-06-30",
                }
            }
        )
        out = build_filing_excerpt_context(ctx, "Business Quality")
        self.assertIn(f"(truncated to {FILING_EXCERPT_BUDGET_CHARS} chars)", out)


# ── counterparty (exhaustive — CLAUDE.md format contract) ───────────────────


def _entry(name, ticker=None, rtype="customer", magnitude=None):
    return CounterpartyEntry(
        name=name,
        resolved_ticker=ticker,
        relationship_type=rtype,
        magnitude_pct=magnitude,
        unnamed=False,
    )


class BuildCounterpartyContextTests(unittest.TestCase):
    # 1. unrouted category
    def test_empty_when_category_unrouted(self):
        cp = CounterpartyContext(outbound={"customer": [_entry("AWS")]})
        ctx = _ctx(counterparty_context=cp)
        # "Macro & Regime" not in RELATIONSHIP_ROUTING.
        self.assertEqual(build_counterparty_context(ctx, "Macro & Regime"), "")

    # 2. None counterparty_context
    def test_empty_when_none(self):
        self.assertEqual(build_counterparty_context(_ctx(), "Business Quality"), "")

    # 3. has_data False (empty buckets)
    def test_empty_when_no_data(self):
        ctx = _ctx(counterparty_context=CounterpartyContext())
        self.assertEqual(build_counterparty_context(ctx, "Business Quality"), "")

    # 4. outbound only
    def test_outbound_only_renders(self):
        cp = CounterpartyContext(
            outbound={"customer": [_entry("AWS", ticker="AMZN", magnitude=5.4)]}
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        self.assertIn("RESOLVED COUNTERPARTIES", out)
        self.assertIn("Outbound — ORCL's disclosed relationships:", out)
        self.assertIn("Customers:", out)
        self.assertIn("$AMZN — AWS", out)
        self.assertIn("5.4%", out)
        self.assertNotIn("Mentioned by others", out)

    # 5. inbound only
    def test_inbound_only_renders(self):
        cp = CounterpartyContext(
            inbound={"competitor": [_entry("$MSFT", ticker="MSFT", rtype="competitor")]}
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        self.assertIn("Mentioned by others — who named ORCL in their own filings:", out)
        self.assertIn("As a competitor (1 mention(s)):", out)
        self.assertIn("$MSFT", out)
        self.assertNotIn("Outbound", out)

    # 6. both outbound + inbound
    def test_outbound_and_inbound(self):
        cp = CounterpartyContext(
            outbound={"customer": [_entry("AWS", ticker="AMZN")]},
            inbound={"partner": [_entry("$NVDA", ticker="NVDA", rtype="partner")]},
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        self.assertIn("Outbound — ORCL's disclosed", out)
        self.assertIn("Mentioned by others", out)

    # 7. resolved vs unresolved entry formatting
    def test_unresolved_entry_renders_bare_name(self):
        cp = CounterpartyContext(
            outbound={"customer": [_entry("Some Unresolved Co", ticker=None)]}
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        # Bare name (no $TICKER notation), but still in the entry line
        self.assertIn("Some Unresolved Co", out)
        self.assertNotIn("$ — Some Unresolved Co", out)

    # 8. magnitude_pct present vs absent
    def test_magnitude_omitted_when_none(self):
        cp = CounterpartyContext(
            outbound={
                "customer": [
                    _entry("WithMag", ticker="A", magnitude=12.3),
                    _entry("NoMag", ticker="B", magnitude=None),
                ]
            }
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        self.assertIn("$A — WithMag — customer — 12.3%", out)
        self.assertIn("$B — NoMag — customer", out)
        # Ensure no trailing magnitude on NoMag line.
        for line in out.splitlines():
            if "NoMag" in line:
                self.assertFalse(line.endswith("%"))

    # 9. type_order: customer rendered before supplier, regardless of dict order
    def test_outbound_type_ordering(self):
        cp = CounterpartyContext(
            outbound={
                "supplier": [_entry("Sup", ticker="S")],
                "customer": [_entry("Cus", ticker="C")],
            }
        )
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        i_cust = out.index("Customers:")
        i_sup = out.index("Suppliers:")
        self.assertLess(i_cust, i_sup)

    # 10. trailing newline contract
    def test_trailing_newline(self):
        cp = CounterpartyContext(outbound={"customer": [_entry("AWS", ticker="AMZN")]})
        ctx = _ctx(counterparty_context=cp)
        out = build_counterparty_context(ctx, "Business Quality")
        self.assertTrue(out.endswith("\n"))
        # rstrip()+"\n" means exactly one trailing newline, not two.
        self.assertFalse(out.endswith("\n\n"))


# ── dispatcher ──────────────────────────────────────────────────────────────


class BuildAllContextsTests(unittest.TestCase):
    def test_returns_one_dict_per_category(self):
        ctx = _ctx(categories=["Business Quality", "Macro & Regime"])
        out = build_all_contexts(ctx)
        self.assertEqual(set(out.keys()), {"Business Quality", "Macro & Regime"})
        for cat, kinds in out.items():
            self.assertEqual(
                set(kinds.keys()),
                {"transcript", "macro", "technical", "sentiment", "edgar", "filing", "counterparty", "quant"},
            )

    def test_empty_categories_returns_empty_dict(self):
        self.assertEqual(build_all_contexts(_ctx()), {})


# ── quant ───────────────────────────────────────────────────────────────────

QUANT_FP = {
    "piotroski": {"score": 8, "components_evaluated": 9, "components": [
        {"key": "roa_positive", "label": "ROA positive (TTM)", "passed": True, "detail": "ROA 0.2"},
        {"key": "no_dilution", "label": "No net share issuance YoY", "passed": False, "detail": "102 now vs 100 prior"},
    ]},
    "altman_z": {"z": 9.3767, "zone": "safe", "not_applicable_reason": None},
    "beneish_m": {"m": -3.0567, "zone": "unlikely", "ratios": {"dsri": 0.8, "tata": -0.1},
                  "inputs_missing": [], "not_applicable_reason": None},
    "accruals_ratio": -0.1026,
    "fcf_conversion": 1.25,
    "sbc": {"sbc_pct_revenue": 4.0, "share_growth_yoy_pct": 2.0},
    "margin_slopes": {"gross": {"slope_pp_per_quarter": 0.85, "quarters": 8},
                      "operating": {"slope_pp_per_quarter": None, "quarters": 3},
                      "net": {"slope_pp_per_quarter": -0.1, "quarters": 8}},
    "meta": {"quarters_available": 8, "basis": "ttm_vs_prior_ttm", "sector": "Technology"},
}


class BuildQuantContextTests(unittest.TestCase):
    def test_empty_when_category_unrouted(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        self.assertEqual(build_quant_context(ctx, "Macro & Regime"), "")

    def test_empty_when_no_fingerprint(self):
        self.assertEqual(build_quant_context(_ctx(), "Financial Health"), "")
        ctx = _ctx(curated_financials={})
        self.assertEqual(build_quant_context(ctx, "Financial Health"), "")

    def test_routed_renders_only_routed_groups(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Risk Assessment")  # altman, beneish, accruals
        self.assertIn("Altman Z: 9.3767 (safe", out)
        self.assertIn("Beneish M: -3.0567 (unlikely", out)
        self.assertIn("Accruals ratio", out)
        self.assertNotIn("Piotroski", out)
        self.assertNotIn("SBC", out)

    def test_header_framing_pinned(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Financial Health")
        self.assertIn("Do NOT recompute these; interpret them", out)
        self.assertIn("Piotroski F-score: 8/9 (9 evaluated)", out)
        self.assertIn("✗ no_dilution", out)

    def test_not_applicable_rendered_as_gap(self):
        fp = dict(QUANT_FP)
        fp["altman_z"] = {"z": None, "zone": None,
                          "not_applicable_reason": "Altman Z is not meaningful for financial-sector companies"}
        ctx = _ctx(curated_financials={"quant_fingerprint": fp})
        out = build_quant_context(ctx, "Risk Assessment")
        self.assertIn("Altman Z: n/a — Altman Z is not meaningful", out)

    def test_margin_slopes_skip_null_entries(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Growth & Earnings")
        self.assertIn("gross +0.85pp/q over 8q", out)
        self.assertIn("net -0.1pp/q over 8q", out)
        self.assertNotIn("operating", out.split("Margin trend slopes")[1].split("\n")[0])

    def test_build_all_contexts_includes_quant_kind(self):
        ctx = _ctx(categories=["Financial Health"],
                   curated_financials={"quant_fingerprint": QUANT_FP})
        all_ctx = build_all_contexts(ctx)
        self.assertIn("quant", all_ctx["Financial Health"])
        self.assertIn("Piotroski", all_ctx["Financial Health"]["quant"])


if __name__ == "__main__":
    unittest.main()
