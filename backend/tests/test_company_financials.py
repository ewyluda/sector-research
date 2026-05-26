"""Unit tests for build_company_financials.

Stubs the FMP client (each method returns tuple[data, Citation]) — no network.
Verifies the three statements are reshaped into period-aligned column dicts,
numeric-only, with period labels from fiscalYear/period, BS/CF aligned by index.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_financials


class _StubFMP:
    def __init__(self, inc, bal, cf):
        self._inc, self._bal, self._cf = inc, bal, cf

    async def get_income_statement(self, ticker, period="annual", limit=4):
        return self._inc, None

    async def get_balance_sheet(self, ticker, period="annual", limit=4):
        return self._bal, None

    async def get_cash_flow(self, ticker, period="annual", limit=4):
        return self._cf, None


def _stub():
    return _StubFMP(
        inc=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "symbol": "AAPL",
             "revenue": 100.0, "grossProfit": 46.0, "netIncome": 25.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "symbol": "AAPL",
             "revenue": 90.0, "grossProfit": 40.0, "netIncome": 20.0},
        ],
        bal=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "totalAssets": 350.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "totalAssets": 340.0},
        ],
        cf=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "freeCashFlow": 22.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "freeCashFlow": 18.0},
        ],
    )


class BuildCompanyFinancialsTest(unittest.IsolatedAsyncioTestCase):
    async def test_quarter_period_labels_and_alignment(self):
        fin = await build_company_financials(_stub(), "aapl", period="quarter")
        self.assertEqual(fin.ticker, "AAPL")
        self.assertEqual(fin.period, "quarter")
        self.assertEqual(fin.periods, ["Q3 2025", "Q2 2025"])
        self.assertEqual(fin.income["revenue"], [100.0, 90.0])
        self.assertEqual(fin.income["netIncome"], [25.0, 20.0])
        self.assertEqual(fin.balance["totalAssets"], [350.0, 340.0])
        self.assertEqual(fin.cashflow["freeCashFlow"], [22.0, 18.0])

    async def test_numeric_only_no_string_keys(self):
        fin = await build_company_financials(_stub(), "AAPL", period="quarter")
        self.assertNotIn("symbol", fin.income)
        self.assertNotIn("date", fin.income)
        self.assertNotIn("period", fin.income)

    async def test_annual_labels_use_fiscal_year(self):
        fin = await build_company_financials(_stub(), "AAPL", period="annual")
        self.assertEqual(fin.periods, ["2025", "2025"])

    async def test_empty_statements_degrade(self):
        fin = await build_company_financials(_StubFMP([], [], []), "X", period="quarter")
        self.assertEqual(fin.periods, [])
        self.assertEqual(fin.income, {})
        self.assertEqual(fin.balance, {})


if __name__ == "__main__":
    unittest.main()
