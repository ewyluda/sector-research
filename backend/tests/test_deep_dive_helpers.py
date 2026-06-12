"""Pins behaviour of the pure helpers lifted out of `node_deep_dive`."""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.graph.deep_dive_helpers import (
    format_fact_value,
    unwrap_gather_citation,
    unwrap_gather_result,
)


class UnwrapGatherResultTests(unittest.TestCase):
    def test_returns_data_on_success(self):
        # Each client method returns (data, citation); we want the data slot.
        self.assertEqual(unwrap_gather_result(({"a": 1}, "cit"), default={}), {"a": 1})
        self.assertEqual(unwrap_gather_result(([1, 2, 3], "cit"), default=[]), [1, 2, 3])

    def test_returns_default_on_exception(self):
        self.assertEqual(unwrap_gather_result(RuntimeError("boom"), default={}), {})
        self.assertEqual(unwrap_gather_result(TimeoutError(), default=[]), [])
        self.assertEqual(unwrap_gather_result(ValueError("x"), default=None), None)


class FormatFactValueTests(unittest.TestCase):
    def test_usd_billions(self):
        self.assertEqual(format_fact_value(2_500_000_000, "USD"), "$2.50B")

    def test_usd_millions(self):
        self.assertEqual(format_fact_value(7_300_000, "USD"), "$7.30M")

    def test_usd_dollars(self):
        self.assertEqual(format_fact_value(450_000, "USD"), "$450,000")

    def test_pure_ratio_as_percent(self):
        # |value| <= 1 → percent
        self.assertEqual(format_fact_value(0.123, "pure"), "12.30%")
        self.assertEqual(format_fact_value(-0.05, "pure"), "-5.00%")

    def test_pure_ratio_as_decimal_when_large(self):
        # |value| > 1 → raw decimal (multiplier-style ratios like P/E)
        self.assertEqual(format_fact_value(2.5, "pure"), "2.50")

    def test_other_unit_appends_suffix(self):
        self.assertEqual(format_fact_value(1234, "shares"), "1,234 shares")


class UnwrapGatherCitationTests(unittest.TestCase):
    def test_exception_slot_returns_none(self):
        self.assertIsNone(unwrap_gather_citation(RuntimeError("boom")))

    def test_tuple_slot_returns_citation_half(self):
        sentinel = object()
        self.assertIs(unwrap_gather_citation(("data", sentinel)), sentinel)

    def test_none_citation_passes_through(self):
        self.assertIsNone(unwrap_gather_citation(("data", None)))


if __name__ == "__main__":
    unittest.main()
