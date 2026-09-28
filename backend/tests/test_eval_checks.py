"""The eval harness's deterministic thesis checks (backend/evals/checks.py)."""
import unittest

from backend.evals.checks import citations, consistency, extract_numbers, grounding


def _thesis(**kw) -> dict:
    base = {
        "core_thesis": "", "variant_perception": "", "bull_case": [], "bear_case": [],
        "stance": "long", "time_horizon": "12 months",
        "price_targets": {"bear": 80.0, "base": 120.0, "bull": 150.0},
        "kill_criteria": [{"condition": "x", "threshold": "y", "monitoring_source": "z"}],
        "pre_mortem": {"framing": "f", "failure_modes": []},
    }
    return {**base, **kw}


class NumberExtractionTests(unittest.TestCase):
    def test_units_scale_and_trivial_numbers_are_skipped(self):
        nums = {n.text: n.value for n in extract_numbers(
            "Revenue $4.2B (+37.7%), 61.7x EV/EBITDA, 1,250 employees, in 2026, 3 catalysts, Q3")}
        self.assertAlmostEqual(nums["$4.2B"], 4.2e9)
        self.assertAlmostEqual(nums["+37.7%"], 37.7)
        self.assertAlmostEqual(nums["61.7x"], 61.7)
        self.assertIn("1,250", nums)
        self.assertNotIn("2026", nums)   # a year
        self.assertNotIn("3", nums)      # a count


class GroundingTests(unittest.TestCase):
    def test_numbers_match_within_display_precision(self):
        prompt = "Revenue: $4,213,000,000. Gross margin 0.3768. Debt/Equity 6.2x. Price $253.28."
        thesis = _thesis(core_thesis="Revenue of $4.2B at a 38% gross margin, 6.2x levered; 55% upside.")
        g = grounding(thesis, prompt)
        self.assertEqual(g.total, 4)
        self.assertEqual(g.grounded, 3)       # $4.2B, 38% (fraction in source), 6.2x
        self.assertEqual(g.ungrounded, ["55%"])  # derived by the model, not in the input

    def test_no_numbers_is_undefined_not_perfect(self):
        self.assertIsNone(grounding(_thesis(core_thesis="Qualitative only."), "x").share)


class CitationTests(unittest.TestCase):
    def test_known_families_pass_and_invented_sources_fail(self):
        thesis = _thesis(bull_case=[
            {"title": "t", "evidence": "RPO up [Source: SEC 10-Q]"},
            {"title": "t", "evidence": "Margins [Source: Bloomberg terminal]"},
            {"title": "t", "evidence": "No tag at all"},
        ])
        c = citations(thesis)
        self.assertEqual(c.tags, 2)
        self.assertEqual(c.invalid, ["Bloomberg terminal"])
        self.assertEqual((c.uncited_evidence, c.evidence_items), (1, 3))


class ConsistencyTests(unittest.TestCase):
    def test_a_coherent_long_has_no_issues(self):
        self.assertEqual(consistency(_thesis(), price=100.0), [])

    def test_stance_must_agree_with_targets_and_price(self):
        self.assertIn("long_without_upside", consistency(_thesis(), price=130.0))
        short = _thesis(stance="short", price_targets={"bear": 50, "base": 110, "bull": 140})
        self.assertIn("short_without_downside", consistency(short, price=100.0))
        avoid = _thesis(stance="avoid", price_targets={"bear": 80, "base": 125, "bull": 150})
        self.assertIn("avoid_with_compelling_upside", consistency(avoid, price=100.0))

    def test_missing_falsifiability_is_flagged(self):
        issues = consistency(_thesis(kill_criteria=[], pre_mortem=None, stance=None), price=100.0)
        self.assertEqual(set(issues), {"no_kill_criteria", "no_pre_mortem", "no_stance"})


if __name__ == "__main__":
    unittest.main()
