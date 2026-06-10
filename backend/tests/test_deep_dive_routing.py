"""Pins per-category routing for `node_deep_dive`."""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.graph.deep_dive_routing import (
    CategoryRouting,
    EDGAR_ROUTING,
    FILING_EXCERPT_ROUTING,
    MACRO_ROUTING,
    QUANT_ROUTING,
    RELATIONSHIP_ROUTING,
    TRANSCRIPT_ROUTING,
    routing_for,
)


class RoutingTableTests(unittest.TestCase):
    def test_business_quality_full_payload(self):
        r = routing_for("Business Quality")
        self.assertIn("pass3_qa_tensions", r.transcript_passes)
        self.assertEqual(r.macro_indicators, [])
        # Business Quality intentionally has no XBRL concepts routed —
        # `ConcentrationRiskPercentage1` was the only one and it was
        # dropped because the SEC `companyfacts` API doesn't expose
        # dimensional facts. See deep_dive_routing.py.
        self.assertEqual(r.edgar_concepts, [])
        self.assertEqual(r.filing_sections, ["item_1_business"])
        self.assertTrue(r.relationships)

    def test_concentration_concept_not_routed_anywhere(self):
        # Pin the dropped concept so it doesn't sneak back into the
        # whitelist without an explicit decision.
        for cat, concepts in EDGAR_ROUTING.items():
            self.assertNotIn(
                "us-gaap:ConcentrationRiskPercentage1",
                concepts,
                f"{cat} routes ConcentrationRiskPercentage1 — companyfacts doesn't expose it",
            )

    def test_concentration_concept_not_in_client_whitelist(self):
        # The companyfacts ingest pipeline filters to CONCEPT_WHITELIST,
        # so adding a concept here costs DB writes for every ticker.
        # ConcentrationRiskPercentage1 returns nothing → don't ingest it.
        from backend.app.clients.edgar import CONCEPT_WHITELIST
        for taxonomy, concepts in CONCEPT_WHITELIST.items():
            self.assertNotIn(
                "ConcentrationRiskPercentage1",
                concepts,
                f"{taxonomy} whitelists ConcentrationRiskPercentage1 — companyfacts never returns it",
            )

    def test_macro_regime_routes_full_macro_set(self):
        r = routing_for("Macro & Regime")
        self.assertEqual(len(r.macro_indicators), 9)  # all 9 series
        self.assertFalse(r.relationships)

    def test_unknown_category_returns_empty(self):
        r = routing_for("Not A Real Category")
        self.assertEqual(r, CategoryRouting())

    def test_routing_for_returns_copies(self):
        # Mutating the returned lists must not corrupt the underlying
        # registries — caller-side modification has bitten people.
        r = routing_for("Business Quality")
        r.transcript_passes.append("MUTATED")
        r2 = routing_for("Business Quality")
        self.assertNotIn("MUTATED", r2.transcript_passes)


class TableInvariantTests(unittest.TestCase):
    def test_filing_and_relationship_categories_overlap(self):
        # Per CLAUDE.md: relationship context is positioned right after
        # filing excerpts in the prompt, so every relationship-routed
        # category should also be filing-routed.
        for cat in RELATIONSHIP_ROUTING:
            self.assertIn(cat, FILING_EXCERPT_ROUTING, f"{cat} routes relationships but not filing excerpts")

    def test_no_macro_in_pure_qualitative_categories(self):
        # Sentiment & Narrative is qualitative; macro doesn't belong there.
        self.assertNotIn("Sentiment & Narrative", MACRO_ROUTING)

    def test_edgar_routing_uses_us_gaap_prefix(self):
        for cat, concepts in EDGAR_ROUTING.items():
            for c in concepts:
                self.assertTrue(c.startswith("us-gaap:"), f"{cat}: {c} missing us-gaap prefix")

    def test_transcript_routing_uses_pass_keys(self):
        for cat, passes in TRANSCRIPT_ROUTING.items():
            for p in passes:
                self.assertTrue(p.startswith("pass"), f"{cat}: {p} missing pass prefix")


class QuantRoutingTests(unittest.TestCase):
    def test_financial_health_quant_metrics(self):
        r = routing_for("Financial Health")
        self.assertEqual(r.quant_metrics,
                         ["piotroski", "altman_z", "accruals", "fcf_conversion"])

    def test_risk_assessment_gets_forensic_scores(self):
        r = routing_for("Risk Assessment")
        self.assertEqual(r.quant_metrics, ["altman_z", "beneish_m", "accruals"])

    def test_unrouted_category_empty(self):
        self.assertEqual(routing_for("Technical & Market Structure").quant_metrics, [])
        self.assertEqual(routing_for("Macro & Regime").quant_metrics, [])

    def test_table_uses_known_metric_keys_only(self):
        known = {"piotroski", "altman_z", "beneish_m", "accruals",
                 "fcf_conversion", "sbc", "margin_slopes"}
        for cat, keys in QUANT_ROUTING.items():
            self.assertTrue(set(keys) <= known, f"{cat} routes unknown key")

    def test_remaining_categories_pinned(self):
        self.assertEqual(routing_for("Growth & Earnings").quant_metrics,
                         ["margin_slopes", "sbc", "fcf_conversion"])
        self.assertEqual(routing_for("Business Quality").quant_metrics,
                         ["margin_slopes", "piotroski"])
        self.assertEqual(routing_for("Management & Governance").quant_metrics,
                         ["sbc", "beneish_m"])


if __name__ == "__main__":
    unittest.main()
