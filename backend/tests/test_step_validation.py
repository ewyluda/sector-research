"""Tests for step_validation — the third workspace loop step (reverse-DCF re-run)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import ValidationOutput


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_cell(value, source="ai_baseline"):
    return {"value": value, "source": source, "formula": None, "citation_id": None,
            "last_edited_at": None, "last_edited_by": None}


def _make_minimal_model_state() -> dict:
    """Minimal valid ModelState dict — enough for reverse_dcf functions to run against mocks."""
    return {
        "periods": [
            {"label": "2024Q1", "kind": "Q", "is_historical": True, "quarter_index": 1},
            {"label": "2025Q1", "kind": "Q", "is_historical": False, "quarter_index": 1},
            {"label": "2025Q2", "kind": "Q", "is_historical": False, "quarter_index": 2},
            {"label": "2025Y",  "kind": "Y", "is_historical": False, "quarter_index": None},
        ],
        "drivers": {
            "2025Q1": {
                "revenue_growth_pct": _make_cell(0.10),
                "ebit_margin_pct": _make_cell(0.20),
            },
            "2025Q2": {
                "revenue_growth_pct": _make_cell(0.10),
                "ebit_margin_pct": _make_cell(0.20),
            },
            "2025Y": {
                "revenue_growth_pct": _make_cell(0.10),
                "ebit_margin_pct": _make_cell(0.20),
            },
        },
        "income_statement": {
            "revenue": {"2024Q1": _make_cell(100.0, "historical")},
            "cost_of_revenue": {}, "gross_profit": {}, "sga": {}, "rd": {},
            "other_opex": {}, "operating_expenses": {}, "ebit": {},
            "depreciation_amortization": {}, "ebitda": {}, "interest_income": {},
            "interest_expense": {}, "pretax_income": {}, "income_tax": {},
            "net_income": {}, "shares_diluted": {}, "eps_diluted": {},
        },
        "balance_sheet": {
            "cash_and_equivalents": {}, "accounts_receivable": {}, "inventory": {},
            "other_current_assets": {}, "total_current_assets": {}, "ppe_net": {},
            "goodwill": {}, "other_long_term_assets": {}, "total_assets": {},
            "accounts_payable": {}, "short_term_debt": {}, "other_current_liabilities": {},
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
            "discount_rate": _make_cell(0.10),
            "terminal_method": "perpetuity",
            "terminal_multiple": _make_cell(20.0),
            "perpetuity_growth": _make_cell(0.025),
            "tax_rate": _make_cell(0.21),
            "plug_priority": ["debt_paydown", "buyback", "dividend", "cash"],
        },
    }


def _mock_ticker_model(state_dict: dict, version: int = 2):
    m = MagicMock()
    m.version = version
    m.state = state_dict
    return m


def _mock_db_with_model(model_mock):
    """Return an async DB session whose execute() scalar_one_or_none() gives model_mock."""
    scalar = MagicMock()
    scalar.scalar_one_or_none = MagicMock(return_value=model_mock)
    execute_result = AsyncMock(return_value=scalar)
    db = AsyncMock()
    db.execute = execute_result
    return db


def _make_ctx(db, fmp=None) -> WorkspaceContext:
    return WorkspaceContext(
        run_id="run-42",
        ticker="AAPL",
        db=db,
        fmp=fmp or AsyncMock(),
        edgar=AsyncMock(),
        anthropic=MagicMock(),
        prior_research_run=MagicMock(),
        prior_ticker_model=MagicMock(),
        emit=MagicMock(),
    )


# ── Tests ────────────────────────────────────────────────────────────────────

PATCH_FETCH_PRICE = "backend.app.services.workspace_steps._fetch_live_price"
PATCH_SOLVE_DRIVER = "backend.app.services.workspace_steps.solve_implied_driver"
PATCH_SOLVE_IRR = "backend.app.services.workspace_steps.solve_implied_irr"
PATCH_SENS_GRID = "backend.app.services.workspace_steps.sensitivity_grid"
PATCH_THESIS = "backend.app.services.workspace_steps.thesis_vs_priced_in"


class TestStepValidation(unittest.IsolatedAsyncioTestCase):

    async def test_happy_path_returns_validation_output(self):
        """All reverse-DCF helpers succeed; ValidationOutput fields are populated."""
        state_dict = _make_minimal_model_state()
        model = _mock_ticker_model(state_dict, version=2)
        db = _mock_db_with_model(model)
        ctx = _make_ctx(db)

        # sensitivity_grid is called 3 times; return a dict that reflects the kwargs passed.
        def _stub_grid_fn(state, *, x_dim, x_range, y_dim, y_range, size=21):
            return {
                "x_dim": x_dim, "y_dim": y_dim,
                "x_values": [0.0, 0.1], "y_values": [0.1, 0.2],
                "values": [[150.0, 160.0], [155.0, 165.0]],
            }

        stub_thesis = [
            {"dimension": "revenue_growth_pct", "thesis": 0.10, "priced_in": 0.08, "delta": 0.02},
            {"dimension": "ebit_margin_pct",    "thesis": 0.20, "priced_in": 0.18, "delta": 0.02},
            {"dimension": "terminal_multiple",  "thesis": 20.0, "priced_in": 18.0, "delta": 2.0},
        ]

        with (
            patch(PATCH_FETCH_PRICE, new=AsyncMock(return_value=175.0)),
            patch(PATCH_SOLVE_DRIVER, return_value=0.08),
            patch(PATCH_SOLVE_IRR, return_value=0.11),
            patch(PATCH_SENS_GRID, side_effect=_stub_grid_fn),
            patch(PATCH_THESIS, return_value=stub_thesis),
        ):
            from backend.app.services.workspace_steps import step_validation
            out = await step_validation(ctx)

        self.assertIsInstance(out, ValidationOutput)
        self.assertAlmostEqual(out.current_price, 175.0)
        self.assertAlmostEqual(out.implied_irr, 0.11)

        # Three implied drivers populated
        self.assertEqual(len(out.implied_drivers), 3)
        dims = {d.dimension for d in out.implied_drivers}
        self.assertIn("revenue_growth_pct", dims)
        self.assertIn("ebit_margin_pct", dims)
        self.assertIn("terminal_multiple", dims)

        # Three sensitivity grids
        self.assertEqual(len(out.sensitivity_grids), 3)
        grid_pairs = {(g.dim_x, g.dim_y) for g in out.sensitivity_grids}
        self.assertIn(("revenue_growth_pct", "ebit_margin_pct"), grid_pairs)
        self.assertIn(("revenue_growth_pct", "terminal_multiple"), grid_pairs)
        self.assertIn(("ebit_margin_pct",    "terminal_multiple"), grid_pairs)

        # Thesis-vs-priced rows
        self.assertEqual(len(out.thesis_vs_priced_in), 3)

    async def test_no_model_returns_empty_output(self):
        """When no ticker_models row exists, ValidationOutput fields are empty/zero."""
        scalar = MagicMock()
        scalar.scalar_one_or_none = MagicMock(return_value=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=scalar)
        ctx = _make_ctx(db)

        with patch(PATCH_FETCH_PRICE, new=AsyncMock(return_value=175.0)):
            from backend.app.services.workspace_steps import step_validation
            out = await step_validation(ctx)

        self.assertIsInstance(out, ValidationOutput)
        self.assertEqual(out.implied_drivers, [])
        self.assertEqual(out.sensitivity_grids, [])
        self.assertEqual(out.thesis_vs_priced_in, [])
        self.assertIsNone(out.implied_irr)

    async def test_price_zero_returns_empty_output(self):
        """When live price is 0.0 (FMP failure), ValidationOutput is returned empty."""
        state_dict = _make_minimal_model_state()
        model = _mock_ticker_model(state_dict, version=1)
        db = _mock_db_with_model(model)
        ctx = _make_ctx(db)

        with patch(PATCH_FETCH_PRICE, new=AsyncMock(return_value=0.0)):
            from backend.app.services.workspace_steps import step_validation
            out = await step_validation(ctx)

        self.assertIsInstance(out, ValidationOutput)
        self.assertEqual(out.current_price, 0.0)
        self.assertEqual(out.implied_drivers, [])
        self.assertIsNone(out.implied_irr)

    async def test_solver_raises_still_returns_output(self):
        """If a solver raises ValueError, the step does not crash — other fields populated."""
        state_dict = _make_minimal_model_state()
        model = _mock_ticker_model(state_dict, version=1)
        db = _mock_db_with_model(model)
        ctx = _make_ctx(db)

        def _stub_grid_fn2(state, *, x_dim, x_range, y_dim, y_range, size=21):
            return {
                "x_dim": x_dim, "y_dim": y_dim,
                "x_values": [0.0], "y_values": [0.1], "values": [[150.0]],
            }

        with (
            patch(PATCH_FETCH_PRICE, new=AsyncMock(return_value=200.0)),
            patch(PATCH_SOLVE_DRIVER, side_effect=ValueError("unreachable")),
            patch(PATCH_SOLVE_IRR, side_effect=ValueError("unreachable")),
            patch(PATCH_SENS_GRID, side_effect=_stub_grid_fn2),
            patch(PATCH_THESIS, return_value=[]),
        ):
            from backend.app.services.workspace_steps import step_validation
            out = await step_validation(ctx)

        self.assertIsInstance(out, ValidationOutput)
        self.assertAlmostEqual(out.current_price, 200.0)
        # Solvers raised — implied_value should be 0.0 (safe fallback), irr None
        for d in out.implied_drivers:
            self.assertEqual(d.implied_value, 0.0)
        self.assertIsNone(out.implied_irr)


if __name__ == "__main__":
    unittest.main()
