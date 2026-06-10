"""Deep-dive valuation ratio wire names — /stable/ FMP serves multiples on
ratios-ttm, returns on key-metrics-ttm (live-verified 2026-06-09 against NVDA).

Pins the fix for the pre-existing bug where _fmt_fundamentals and
_build_curated_financials read key-metrics-ttm spellings (peRatioTTM etc.)
that the live API no longer serves, leaving every valuation field None.
"""
import unittest

from backend.app.graph.nodes import _build_curated_financials, _fmt_fundamentals

# Shaped like the live /stable/key-metrics-ttm payload (subset).
LIVE_KM = {
    "symbol": "NVDA",
    "returnOnEquityTTM": 1.07,
    "returnOnInvestedCapitalTTM": 0.78,
    "returnOnAssetsTTM": 0.65,
    "returnOnTangibleAssetsTTM": 0.66,
    "evToEBITDATTM": 42.0,
    "marketCap": 3.5e12,
}

# Shaped like the live /stable/ratios-ttm payload (subset).
LIVE_RATIOS = {
    "symbol": "NVDA",
    "priceToEarningsRatioTTM": 51.2,
    "enterpriseValueMultipleTTM": 44.7,
    "priceToBookRatioTTM": 38.1,
    "priceToFreeCashFlowRatioTTM": 60.3,
    "priceToSalesRatioTTM": 26.4,
    "priceToEarningsGrowthRatioTTM": 1.8,
    "dividendYieldTTM": 0.0003,
    "interestCoverageRatioTTM": 341.2,
}

# The pre-/stable/ key-metrics-ttm spellings — kept working as fallbacks so
# re-rendering old persisted payloads doesn't regress.
LEGACY_KM = {
    "peRatioTTM": 51.2,
    "enterpriseValueOverEBITDATTM": 44.7,
    "priceToBookRatioTTM": 38.1,
    "priceToFreeCashFlowsRatioTTM": 60.3,
    "priceToSalesRatioTTM": 26.4,
    "pegRatioTTM": 1.8,
    "roeTTM": 1.07,
    "roicTTM": 0.78,
    "returnOnTangibleAssetsTTM": 0.66,
    "dividendYieldTTM": 0.0003,
    "interestCoverageTTM": 341.2,
}


def build(km, ratios):
    return _build_curated_financials(
        ticker="NVDA",
        income=[],
        balance=[],
        cashflow=[],
        profile={},
        dcf=None,
        estimates=[],
        key_metrics=km,
        ratios=ratios,
    )


class TestCuratedFinancialsWireNames(unittest.TestCase):
    def test_live_payload_populates_all_valuation_and_return_fields(self):
        cf = build(LIVE_KM, LIVE_RATIOS)
        self.assertEqual(cf.pe_ratio, 51.2)
        self.assertEqual(cf.ev_to_ebitda, 44.7)
        self.assertEqual(cf.price_to_book, 38.1)
        self.assertEqual(cf.price_to_fcf, 60.3)
        self.assertEqual(cf.price_to_sales, 26.4)
        self.assertEqual(cf.peg_ratio, 1.8)
        self.assertEqual(cf.roe, 1.07)
        self.assertEqual(cf.roic, 0.78)
        self.assertEqual(cf.roa, 0.65)  # true ROA, not tangible-assets variant
        self.assertEqual(cf.dividend_yield, 0.0003)
        self.assertEqual(cf.interest_coverage, 341.2)

    def test_legacy_km_spellings_still_work_without_ratios(self):
        cf = build(LEGACY_KM, None)
        self.assertEqual(cf.pe_ratio, 51.2)
        self.assertEqual(cf.ev_to_ebitda, 44.7)
        self.assertEqual(cf.price_to_fcf, 60.3)
        self.assertEqual(cf.peg_ratio, 1.8)
        self.assertEqual(cf.roe, 1.07)
        self.assertEqual(cf.roic, 0.78)
        self.assertEqual(cf.roa, 0.66)
        self.assertEqual(cf.dividend_yield, 0.0003)
        self.assertEqual(cf.interest_coverage, 341.2)

    def test_missing_everything_stays_none(self):
        cf = build({}, {})
        self.assertIsNone(cf.pe_ratio)
        self.assertIsNone(cf.roe)
        self.assertIsNone(cf.interest_coverage)


class TestFmtFundamentalsWireNames(unittest.TestCase):
    def test_live_payload_renders_valuation_and_return_lines(self):
        text = _fmt_fundamentals(
            "NVDA", [], [], [], {},
            key_metrics=LIVE_KM,
            ratios=LIVE_RATIOS,
        )
        self.assertIn("P/E: 51.20", text)
        self.assertIn("EV/EBITDA: 44.70", text)
        self.assertIn("P/B: 38.10", text)
        self.assertIn("P/FCF: 60.30", text)
        self.assertIn("P/S: 26.40", text)
        self.assertIn("PEG: 1.80", text)
        self.assertIn("Dividend Yield: 0.03%", text)
        self.assertIn("ROE: 107.0%", text)
        self.assertIn("ROIC: 78.0%", text)
        self.assertIn("ROA: 65.0%", text)
        self.assertIn("Interest Coverage: 341.2x", text)

    def test_no_metrics_renders_no_valuation_block(self):
        text = _fmt_fundamentals("NVDA", [], [], [], {})
        self.assertNotIn("Valuation Ratios", text)


if __name__ == "__main__":
    unittest.main()
