"""Dashboard series: true year-over-year growth, n/m guards, fiscal labels,
and no DCF gap from a non-positive DCF value (2026-09-27 fixes)."""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph.formatters import (  # noqa: E402
    _build_curated_financials,
    _growth_pct,
    _quarter_label,
)

# SMCI quarterly revenue, newest first, as FMP /stable/ returns it
# (fiscalYear, no calendarYear).
_SMCI = [
    ("Q3", "2026", 10.243e9, -6.70e9), ("Q2", "2026", 12.682e9, 0.045e9),
    ("Q1", "2026", 5.018e9, -0.95e9), ("Q4", "2025", 5.757e9, 0.84e9),
    ("Q3", "2025", 4.600e9, -0.25e9), ("Q2", "2025", 5.678e9, 0.60e9),
    ("Q1", "2025", 5.937e9, 0.10e9), ("Q4", "2024", 5.355e9, 0.30e9),
]


def _cf(dcf_value: float):
    income = [{"period": p, "fiscalYear": fy, "revenue": r, "eps": 1.0} for p, fy, r, _ in _SMCI]
    cash = [{"period": p, "fiscalYear": fy, "freeCashFlow": f} for p, fy, _, f in _SMCI]
    return _build_curated_financials(
        "SMCI", income, [], cash, {"price": 29.84}, {"dcf": dcf_value, "Stock Price": 29.84}, [],
    )


class GrowthTests(unittest.TestCase):
    def test_revenue_growth_is_year_over_year(self):
        rev = _cf(40.0).quarterly_revenue
        self.assertAlmostEqual(rev[0].yoy_growth, 122.67, places=1)  # was -19.2 (QoQ)
        self.assertIsNone(rev[4].yoy_growth)  # no quarter four back

    def test_growth_from_negative_or_tiny_base_is_nm(self):
        fcf = _cf(40.0).quarterly_free_cf
        self.assertIsNone(fcf[0].yoy_growth)  # prior -0.25B: negative base
        self.assertIsNone(_growth_pct(-6.7e9, 0.045e9))
        self.assertEqual(_growth_pct(12.0, 10.0), 20.0)

    def test_fiscal_quarter_labels(self):
        self.assertEqual(_cf(40.0).quarterly_revenue[0].period, "Q3 FY26")
        self.assertEqual(_quarter_label({"period": "Q1", "calendarYear": "2024"}), "Q1 2024")
        self.assertEqual(_quarter_label({"date": "2026-03-31"}), "2026-03")

    def test_negative_dcf_has_no_gap(self):
        self.assertIsNone(_cf(-60.37).dcf_gap_percent)
        self.assertIsNotNone(_cf(40.0).dcf_gap_percent)


if __name__ == "__main__":
    unittest.main()
