"""Unit tests for build_company_overview.

Stubs the FMP client (each method returns tuple[data, Citation]) — no network.
Verifies the 8-group statistics grid maps real FMP TTM field names, missing
keys degrade to None (em-dash), and the price series is oldest-first.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_overview


class _StubFMP:
    def __init__(self, profile, km, ratios, growth, prices):
        self._profile, self._km, self._ratios, self._growth, self._prices = (
            profile, km, ratios, growth, prices,
        )

    async def get_company_profile(self, ticker):
        return self._profile, None

    async def get_key_metrics_ttm(self, ticker):
        return self._km, None

    async def get_ratios_ttm(self, ticker):
        return self._ratios, None

    async def get_financial_growth(self, ticker, period="annual", limit=1):
        return self._growth, None

    async def get_historical_price_adjusted(self, ticker, from_date, to_date):
        return self._prices, None


def _full_stub():
    return _StubFMP(
        profile={"companyName": "Apple Inc.", "sector": "Technology",
                 "industry": "Consumer Electronics", "marketCap": 3.4e12,
                 "beta": 1.25, "fullTimeEmployees": 161000},
        km={"enterpriseValueTTM": 3.5e12, "evToEBITDATTM": 25.1,
            "evToSalesTTM": 8.2, "returnOnEquityTTM": 1.47,
            "returnOnAssetsTTM": 0.28, "returnOnInvestedCapitalTTM": 0.55,
            "returnOnCapitalEmployedTTM": 0.6, "returnOnTangibleAssetsTTM": 0.3,
            "currentRatioTTM": 0.87, "netDebtToEBITDATTM": 0.4,
            "workingCapitalTTM": -1.0e9, "earningsYieldTTM": 0.03,
            "freeCashFlowYieldTTM": 0.035},
        ratios={"priceToEarningsRatioTTM": 35.2, "priceToBookRatioTTM": 48.0,
                "priceToSalesRatioTTM": 8.5, "priceToFreeCashFlowRatioTTM": 30.0,
                "priceToEarningsGrowthRatioTTM": 2.1,
                "forwardPriceToEarningsGrowthRatioTTM": 1.9,
                "priceToFairValueTTM": 1.1, "grossProfitMarginTTM": 0.46,
                "ebitdaMarginTTM": 0.34, "operatingProfitMarginTTM": 0.30,
                "pretaxProfitMarginTTM": 0.29, "netProfitMarginTTM": 0.25,
                "dividendYieldTTM": 0.005, "dividendPayoutRatioTTM": 0.15,
                "dividendPerShareTTM": 0.96, "cashPerShareTTM": 4.0},
        growth={"revenueGrowth": 0.08, "epsgrowth": 0.10,
                "freeCashFlowGrowth": 0.05, "ebitdaGrowth": 0.07,
                "fiveYRevenueGrowthPerShare": 0.12,
                "tenYRevenueGrowthPerShare": 0.15,
                "fiveYDividendperShareGrowthPerShare": 0.06},
        prices=[
            {"date": "2025-01-03", "adjClose": 240.0},
            {"date": "2025-01-02", "adjClose": 243.0},  # newest-first from FMP
        ],
    )


class BuildCompanyOverviewTest(unittest.IsolatedAsyncioTestCase):
    async def test_eight_groups_present(self):
        ov = await build_company_overview(_full_stub(), "aapl")
        self.assertEqual(ov.ticker, "AAPL")
        self.assertEqual(ov.sector, "Technology")
        titles = [g.title for g in ov.stats]
        self.assertEqual(titles, [
            "Profile", "Margins", "Returns (TTM)", "Valuation (TTM)",
            "Valuation (Forward)", "Financial Health", "Growth", "Dividends",
        ])

    async def test_maps_real_field_names(self):
        ov = await build_company_overview(_full_stub(), "AAPL")
        groups = {g.title: {i.label: i for i in g.items} for g in ov.stats}
        self.assertAlmostEqual(groups["Returns (TTM)"]["ROE"].value, 1.47)
        self.assertEqual(groups["Returns (TTM)"]["ROE"].unit, "pct")
        self.assertAlmostEqual(groups["Valuation (TTM)"]["P/E"].value, 35.2)
        self.assertEqual(groups["Valuation (TTM)"]["P/E"].unit, "x")
        self.assertAlmostEqual(groups["Margins"]["Gross"].value, 0.46)
        self.assertAlmostEqual(groups["Profile"]["Market Cap"].value, 3.4e12)
        self.assertEqual(groups["Profile"]["Market Cap"].unit, "money")
        self.assertEqual(groups["Profile"]["Employees"].value, 161000)
        self.assertEqual(groups["Profile"]["Employees"].unit, "int")

    async def test_missing_keys_degrade_to_none(self):
        stub = _StubFMP(profile={"companyName": "X"}, km={}, ratios={},
                        growth={}, prices=[])
        ov = await build_company_overview(stub, "X")
        groups = {g.title: {i.label: i for i in g.items} for g in ov.stats}
        self.assertIsNone(groups["Valuation (TTM)"]["P/E"].value)
        self.assertIsNone(groups["Returns (TTM)"]["ROE"].value)
        self.assertEqual(ov.prices, [])

    async def test_prices_sorted_oldest_first(self):
        ov = await build_company_overview(_full_stub(), "AAPL")
        self.assertEqual([p.date for p in ov.prices], ["2025-01-02", "2025-01-03"])
        self.assertEqual(ov.prices[0].close, 243.0)


if __name__ == "__main__":
    unittest.main()
