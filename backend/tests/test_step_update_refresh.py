"""Tests for step_update_refresh — the first workspace loop step."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.workspace_steps import step_update_refresh
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import UpdateRefreshOutput


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_model_cell_dict(value, source="historical"):
    return {"value": value, "source": source, "formula": None, "citation_id": None,
            "last_edited_at": None, "last_edited_by": None}


def _make_assumption_cell(value, source="ai_baseline"):
    return {"value": value, "source": source, "formula": None, "citation_id": None,
            "last_edited_at": None, "last_edited_by": None}


def _make_baseline_state_dict() -> dict:
    """Minimal valid ModelState dict that round-trips through ModelState.model_validate.

    Historical periods: 2025Q1, 2025Q2, 2025Q3 (three known quarters).
    Forecast periods: 2025Q4, 2026Q1, 2026Y.
    FMP mock data returns 2025Q4 actuals — that period is forecast here,
    but its historical flag means patches only land on historical periods.
    To test new-quarter patching, we leave 2025Q3 without revenue so that
    when FMP returns 2025Q3 data, it patches a historical cell.
    """
    return {
        "periods": [
            {"label": "2025Q1", "kind": "Q", "is_historical": True, "quarter_index": 1},
            {"label": "2025Q2", "kind": "Q", "is_historical": True, "quarter_index": 2},
            {"label": "2025Q3", "kind": "Q", "is_historical": True, "quarter_index": 3},
            {"label": "2025Q4", "kind": "Q", "is_historical": False, "quarter_index": 4},
            {"label": "2026Q1", "kind": "Q", "is_historical": False, "quarter_index": 1},
            {"label": "2026Y", "kind": "Y", "is_historical": False, "quarter_index": None},
        ],
        "drivers": {
            "2025Q4": {"revenue_growth_pct": _make_model_cell_dict(0.10, "ai_baseline")},
            "2026Q1": {"revenue_growth_pct": _make_model_cell_dict(0.10, "ai_baseline")},
            "2026Y":  {"revenue_growth_pct": _make_model_cell_dict(0.10, "ai_baseline")},
        },
        "income_statement": {
            "revenue": {
                "2025Q1": _make_model_cell_dict(100.0),
                "2025Q2": _make_model_cell_dict(105.0),
                # 2025Q3 deliberately missing — FMP will patch it
            },
            "cost_of_revenue": {
                "2025Q1": _make_model_cell_dict(40.0),
                "2025Q2": _make_model_cell_dict(42.0),
            },
            "gross_profit": {},
            "sga": {}, "rd": {}, "other_opex": {}, "operating_expenses": {},
            "ebit": {}, "depreciation_amortization": {}, "ebitda": {},
            "interest_income": {}, "interest_expense": {}, "pretax_income": {},
            "income_tax": {}, "net_income": {}, "shares_diluted": {}, "eps_diluted": {},
        },
        "balance_sheet": {
            "cash_and_equivalents": {
                "2025Q1": _make_model_cell_dict(50.0),
                "2025Q2": _make_model_cell_dict(55.0),
            },
            "accounts_receivable": {}, "inventory": {}, "other_current_assets": {},
            "total_current_assets": {}, "ppe_net": {}, "goodwill": {},
            "other_long_term_assets": {}, "total_assets": {}, "accounts_payable": {},
            "short_term_debt": {}, "other_current_liabilities": {},
            "total_current_liabilities": {}, "long_term_debt": {},
            "other_long_term_liabilities": {}, "total_liabilities": {}, "common_equity": {},
            "retained_earnings": {}, "total_equity": {}, "total_liab_and_equity": {},
        },
        "cash_flow": {
            "net_income_cf": {}, "depreciation_amortization_cf": {},
            "delta_accounts_receivable": {}, "delta_inventory": {},
            "delta_accounts_payable": {}, "operating_cash_flow": {},
            "capex": {}, "free_cash_flow": {}, "debt_issued": {}, "debt_repaid": {},
            "dividends_paid": {}, "buybacks": {}, "net_change_in_cash": {},
        },
        "assumptions": {
            "discount_rate": _make_assumption_cell(0.10),
            "terminal_method": "perpetuity",
            "terminal_multiple": _make_assumption_cell(20.0),
            "perpetuity_growth": _make_assumption_cell(0.025),
            "tax_rate": _make_assumption_cell(0.21),
            "plug_priority": ["debt_paydown", "buyback", "dividend", "cash"],
        },
    }


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _mock_fmp_no_change():
    fmp = AsyncMock()
    fmp.get_income_statement = AsyncMock(return_value=([], MagicMock(id="cit-fmp-1")))
    fmp.get_balance_sheet = AsyncMock(return_value=([], MagicMock(id="cit-fmp-2")))
    fmp.get_cash_flow = AsyncMock(return_value=([], MagicMock(id="cit-fmp-3")))
    fmp.get_analyst_estimates = AsyncMock(return_value=([], MagicMock(id="cit-fmp-4")))
    return fmp


def _mock_fmp_with_new_quarter():
    fmp = AsyncMock()
    # FMP returns period="Q3", calendarYear="2025" — step must join them into "2025Q3"
    # 2025Q3 is a HISTORICAL period in the model fixture but has no revenue data yet,
    # so this patch adds a genuine new historical actual.
    fmp.get_income_statement = AsyncMock(return_value=(
        [{"period": "Q3", "calendarYear": "2025",
          "revenue": 120.0, "grossProfit": 60.0, "operatingIncome": 35.0,
          "netIncome": 25.0, "eps": 0.62, "weightedAverageShsOutDil": 40.0}],
        MagicMock(id="cit-fmp-1"),
    ))
    fmp.get_balance_sheet = AsyncMock(return_value=(
        [{"period": "Q3", "calendarYear": "2025",
          "cashAndCashEquivalents": 60.0, "totalDebt": 80.0, "totalAssets": 300.0}],
        MagicMock(id="cit-fmp-2"),
    ))
    fmp.get_cash_flow = AsyncMock(return_value=(
        [{"period": "Q3", "calendarYear": "2025",
          "operatingCashFlow": 30.0, "capitalExpenditure": -5.0, "freeCashFlow": 25.0}],
        MagicMock(id="cit-fmp-3"),
    ))
    fmp.get_analyst_estimates = AsyncMock(return_value=([], MagicMock(id="cit-fmp-4")))
    return fmp


def _mock_edgar_no_new():
    e = AsyncMock()
    e.get_ticker_to_cik = AsyncMock(return_value=(None, MagicMock()))
    return e


def _mock_edgar_with_new_filing():
    cik = "0001045810"
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K"],
                "accessionNumber": ["0001045810-26-000001", "0001045810-25-000001"],
                "primaryDocument": ["nvda-20260131.htm", "nvda-20250201.htm"],
                "filingDate": ["2026-05-01", "2025-02-15"],
                "reportDate": ["2026-01-31", "2025-01-31"],
            }
        }
    }
    e = AsyncMock()
    e.get_ticker_to_cik = AsyncMock(return_value=(cik, MagicMock(id="cit-edgar-cik")))
    e.get_submissions = AsyncMock(return_value=(submissions, MagicMock(id="cit-edgar-sub")))
    return e


# ── Tests ────────────────────────────────────────────────────────────────────

class TestStepUpdateRefresh(unittest.IsolatedAsyncioTestCase):

    async def test_no_new_data_returns_empty_diff(self):
        """When FMP returns no new rows and EDGAR has no CIK, diff is empty and version unchanged."""
        prior_model = MagicMock()
        prior_model.version = 3
        prior_model.state = _make_baseline_state_dict()
        prior_model.parent_research_run_id = None

        ctx = WorkspaceContext(
            run_id="r1", ticker="NVDA", db=_mock_db(),
            fmp=_mock_fmp_no_change(),
            edgar=_mock_edgar_no_new(),
            anthropic=MagicMock(),
            prior_research_run=MagicMock(),
            prior_ticker_model=prior_model,
            emit=MagicMock(),
        )
        out = await step_update_refresh(ctx)

        self.assertIsInstance(out, UpdateRefreshOutput)
        self.assertEqual(out.version_before, 3)
        # No changes → no new version persisted
        self.assertIsNone(out.version_after)
        self.assertEqual(out.changed_cells, [])
        self.assertEqual(out.new_filings, [])

    async def test_new_quarter_actuals_create_diff(self):
        """When FMP returns a new quarter row, the diff is non-empty and a new version is saved."""
        prior_model = MagicMock()
        prior_model.version = 5
        prior_model.state = _make_baseline_state_dict()
        prior_model.parent_research_run_id = "rr-abc"

        ctx = WorkspaceContext(
            run_id="r2", ticker="NVDA", db=_mock_db(),
            fmp=_mock_fmp_with_new_quarter(),
            edgar=_mock_edgar_with_new_filing(),
            anthropic=MagicMock(),
            prior_research_run=MagicMock(),
            prior_ticker_model=prior_model,
            emit=MagicMock(),
        )
        out = await step_update_refresh(ctx)

        self.assertIsInstance(out, UpdateRefreshOutput)
        self.assertEqual(out.version_before, 5)
        self.assertEqual(out.version_after, 6)
        self.assertGreater(len(out.changed_cells), 0)
        # Revenue cell for the new quarter must appear in the diff
        revenue_paths = [c.cell_path for c in out.changed_cells
                         if c.cell_path.startswith("income_statement.revenue.")]
        self.assertTrue(len(revenue_paths) > 0,
                        f"Expected income_statement.revenue.* in changed_cells, got: "
                        f"{[c.cell_path for c in out.changed_cells]}")
        # New filing ref present
        self.assertEqual(len(out.new_filings), 1)
        self.assertEqual(out.new_filings[0].form, "10-Q")
        # consensus_delta deferred
        self.assertIsNone(out.consensus_delta)


    async def test_update_refresh_skips_model_when_none(self):
        """When ctx.prior_ticker_model is None, FMP is not touched but EDGAR is still queried."""
        ctx = WorkspaceContext(
            run_id="r3", ticker="NVDA", db=_mock_db(),
            fmp=_mock_fmp_no_change(),
            edgar=_mock_edgar_with_new_filing(),
            anthropic=MagicMock(),
            prior_research_run=MagicMock(),
            prior_ticker_model=None,
            emit=MagicMock(),
        )
        out = await step_update_refresh(ctx)

        self.assertIsInstance(out, UpdateRefreshOutput)
        self.assertTrue(out.model_skipped)
        self.assertEqual(out.version_before, 0)
        self.assertIsNone(out.version_after)
        self.assertEqual(out.changed_cells, [])
        self.assertIn("model refresh skipped", out.summary)
        # EDGAR new filing should still be surfaced
        self.assertEqual(len(out.new_filings), 1)
        self.assertEqual(out.new_filings[0].form, "10-Q")
        # FMP must NOT be called when there is no model to refresh
        ctx.fmp.get_income_statement.assert_not_called()


if __name__ == "__main__":
    unittest.main()
