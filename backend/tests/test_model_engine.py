"""Golden tests for the financial model on the production layout (2026-09-27
rework): calendarized periods, full historical seeding from FMP-shaped rows,
year-over-year quarterly growth, a balance sheet that balances without a plug,
and a DCF bridged from enterprise value to equity per current share.

Fixture rows are synthetic but use FMP /stable/ field names and dates (live-
checked), including a fiscal year that differs from the calendar year.
"""
import os
import unittest
from datetime import date, timedelta

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph.model_baseline_node import BaselineDriversResponse, DriverProposal, PeriodDrivers  # noqa: E402
from backend.app.models.model_state import ModelCell  # noqa: E402
from backend.app.services.dcf import dcf  # noqa: E402
from backend.app.services.model_balancing import ModelBalanceError, recompute  # noqa: E402
from backend.app.services.model_baseline import (  # noqa: E402
    apply_drivers, assemble_historical_state, default_paths, revenue_growth_path,
)
from backend.app.services.model_history import annual_to_quarterly, map_fmp_quarter  # noqa: E402
from backend.app.services.model_periods import build_periods, calendar_quarter_label  # noqa: E402

# Quarter ends ~25 days after calendar quarter ends (like NVDA's fiscal calendar).
_END = date(2026, 7, 26)
_ENDS = [(_END - timedelta(days=91 * i)).isoformat() for i in range(8)]  # newest first


def _inputs(beta: float = 1.5) -> dict:
    income, balance, cashflow = [], [], []
    for i, d in enumerate(_ENDS):
        rev = 1000.0 * (0.95 ** i)  # growing ~5% a quarter, newest largest
        income.append({
            "date": d, "period": "Q", "fiscalYear": "2027", "revenue": rev, "costOfRevenue": 0.4 * rev,
            "grossProfit": 0.6 * rev, "sellingGeneralAndAdministrativeExpenses": 0.1 * rev,
            "researchAndDevelopmentExpenses": 0.1 * rev, "operatingExpenses": 0.2 * rev,
            "operatingIncome": 0.35 * rev, "ebitda": 0.4 * rev, "interestIncome": 5.0,
            "interestExpense": 8.0, "incomeBeforeTax": 0.35 * rev - 3.0,
            "incomeTaxExpense": 0.2 * (0.35 * rev - 3.0), "netIncome": 0.8 * (0.35 * rev - 3.0),
            "weightedAverageShsOutDil": 100.0 + i, "epsDiluted": 2.0,
        })
        balance.append({
            "date": d, "period": "Q", "cashAndShortTermInvestments": 800.0, "netReceivables": 400.0,
            "inventory": 300.0, "totalCurrentAssets": 1600.0, "propertyPlantEquipmentNet": 500.0,
            "goodwillAndIntangibleAssets": 200.0, "totalAssets": 2600.0, "accountPayables": 150.0,
            "shortTermDebt": 50.0, "totalCurrentLiabilities": 400.0, "longTermDebt": 450.0,
            "totalLiabilities": 1000.0, "retainedEarnings": 1200.0, "totalEquity": 1600.0,
        })
        cashflow.append({
            "date": d, "period": "Q", "netIncome": 0.8 * (0.35 * rev - 3.0),
            "depreciationAndAmortization": 0.05 * rev, "operatingCashFlow": 0.3 * rev,
            "capitalExpenditure": -0.03 * rev, "freeCashFlow": 0.27 * rev, "commonDividendsPaid": -10.0,
            "commonStockRepurchased": -20.0, "netDebtIssuance": 0.0, "netChangeInCash": 5.0,
        })
    return {
        "income": income, "balance": balance, "cashflow": cashflow,
        "profile": {"marketCap": 20000.0, "beta": beta, "price": 200.0},
        "ratios": {"enterpriseValueMultipleTTM": 45.0},
        "estimates": [],
    }


def _built(ai: BaselineDriversResponse | None = None):
    state, defaults = assemble_historical_state(_inputs(), rf=0.04)
    apply_drivers(state, ai, defaults, default_paths(state, [], defaults))
    return recompute(state), defaults


class PeriodTests(unittest.TestCase):
    def test_calendarization(self):
        self.assertEqual(calendar_quarter_label("2026-07-26"), "2026Q2")  # nearest quarter end
        self.assertEqual(calendar_quarter_label("2026-01-25"), "2025Q4")
        self.assertEqual(calendar_quarter_label("2026-09-27"), "2026Q3")

    def test_layout_is_contiguous(self):
        labels = [p.label for p in build_periods("2026Q2")]
        self.assertEqual(labels[:8], ["2024Q3", "2024Q4", "2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2"])
        self.assertEqual(labels[8:14], ["2026Q3", "2026Q4", "2027Q1", "2027Q2", "2027Q3", "2027Q4"])
        self.assertEqual(labels[14:], ["2028Y", "2029Y", "2030Y", "2031Y", "2032Y"])  # no gap after 2027Q4


class SeedingTests(unittest.TestCase):
    def test_every_seeded_quarter_balances(self):
        mapped = map_fmp_quarter(*[_inputs()[k][0] for k in ("income", "balance", "cashflow")])["balance_sheet"]
        self.assertAlmostEqual(mapped["total_assets"], mapped["total_liab_and_equity"])
        self.assertAlmostEqual(mapped["other_current_assets"], 100.0)  # residual vs reported total

    def test_seeded_pnl_reproduces_reported_operating_income(self):
        # D&A may sit in cost of revenue or in operating expenses; either way
        # the model identity EBIT = GP - opex - D&A must hit reported EBIT.
        inc, _, cf = [_inputs()[k][0] for k in ("income", "balance", "cashflow")]
        m = map_fmp_quarter(inc, None, cf)["income_statement"]
        self.assertAlmostEqual(m["gross_profit"] - m["operating_expenses"] - m["depreciation_amortization"],
                               inc["operatingIncome"])
        self.assertAlmostEqual(m["ebitda"], inc["operatingIncome"] + cf["depreciationAndAmortization"])

    def test_wacc_uses_real_beta_and_exit_multiple_is_bounded(self):
        state, _ = assemble_historical_state(_inputs(beta=2.0), rf=0.04)
        self.assertIn("β 2.00", state.assumptions.discount_rate.formula)
        self.assertEqual(state.assumptions.terminal_multiple.value, 30.0)  # 45x bounded to 30x


class RecomputeTests(unittest.TestCase):
    def test_balance_sheet_balances_every_period_without_a_plug(self):
        s, _ = _built()
        for p in s.periods:
            ta = s.balance_sheet["total_assets"][p.label].value
            tle = s.balance_sheet["total_liab_and_equity"][p.label].value
            self.assertAlmostEqual(ta, tle, delta=1e-6 * ta, msg=p.label)
            self.assertNotIn("reconciliation", s.balance_sheet["retained_earnings"][p.label].formula or "")

    def test_quarters_grow_year_over_year_and_first_year_builds_on_four_quarters(self):
        s, _ = _built()
        rev = {k: c.value for k, c in s.income_statement["revenue"].items()}
        g_q = s.drivers["2026Q3"]["revenue_growth_pct"].value
        self.assertAlmostEqual(rev["2026Q3"], rev["2025Q3"] * (1 + g_q))
        g_y = s.drivers["2028Y"]["revenue_growth_pct"].value
        self.assertAlmostEqual(rev["2028Y"], sum(rev[f"2027Q{i}"] for i in range(1, 5)) * (1 + g_y))

    def test_annual_drivers_are_converted_for_quarters(self):
        ai = BaselineDriversResponse(drivers={
            "2026Y": PeriodDrivers(buyback_dollars=DriverProposal(value=400.0, reason="r"),
                                   share_count_change_pct=DriverProposal(value=-0.04, reason="r")),
        })
        s, _ = _built(ai)
        self.assertAlmostEqual(s.drivers["2026Q3"]["buyback_dollars"].value, 100.0)
        self.assertAlmostEqual(annual_to_quarterly("share_count_change_pct", -0.04), 0.96 ** 0.25 - 1)
        self.assertEqual(s.drivers["2026Q3"]["buyback_dollars"].source, "ai_baseline")
        self.assertEqual(s.drivers["2027Q1"]["buyback_dollars"].source, "driver")  # TTM default fills 2027

    def test_tax_and_interest_are_not_zero(self):
        s, _ = _built()
        self.assertGreater(s.income_statement["income_tax"]["2026Q3"].value, 0)
        self.assertGreater(s.income_statement["interest_expense"]["2026Q3"].value, 0)

    def test_an_engine_imbalance_is_an_error_but_an_override_is_reconciled(self):
        s, _ = _built()
        s.balance_sheet["cash_and_equivalents"]["2026Q3"] = ModelCell(value=10_000.0, source="override")
        reconciled = recompute(s)
        self.assertIn("override reconciliation", reconciled.balance_sheet["retained_earnings"]["2026Q3"].formula)
        s2, _ = _built()
        s2.balance_sheet["goodwill"]["2026Q2"].value += 500.0  # corrupt the opening balance
        with self.assertRaises(ModelBalanceError):
            recompute(s2)


class DcfBridgeTests(unittest.TestCase):
    def test_equity_value_is_ev_less_net_debt_over_current_shares(self):
        s, _ = _built()
        r = dcf(s)
        self.assertAlmostEqual(r.net_debt, 50.0 + 450.0 - 800.0)  # latest reported quarter
        self.assertEqual(r.shares, 100.0)  # today's diluted shares, not the terminal year's
        self.assertAlmostEqual(r.intrinsic_value, r.enterprise_value - r.net_debt)
        self.assertAlmostEqual(r.intrinsic_per_share, r.intrinsic_value / 100.0)

    def test_missing_share_count_is_an_error_not_one(self):
        s, _ = _built()
        s.income_statement["shares_diluted"]["2026Q2"] = ModelCell(value=None, source="historical")
        with self.assertRaisesRegex(ValueError, "share count"):
            dcf(s)


class GrowthPathTests(unittest.TestCase):
    def test_consensus_then_fade(self):
        path = revenue_growth_path(
            ["2026Y", "2027Y", "2028Y", "2029Y"],
            [{"date": "2026-12-31", "revenueAvg": 120.0}, {"date": "2025-12-31", "revenueAvg": 100.0}],
            ttm_growth=0.9,
        )
        self.assertAlmostEqual(path["2026Y"][0], 0.20)
        self.assertEqual(path["2026Y"][1], "consensus-implied")
        self.assertAlmostEqual(path["2029Y"][0], 0.04)  # faded to long run by the last year

    def test_ttm_growth_is_bounded_before_fading(self):
        path = revenue_growth_path(["2026Y", "2027Y"], [], ttm_growth=0.9)
        self.assertLess(path["2026Y"][0], 0.5)


if __name__ == "__main__":
    unittest.main()
