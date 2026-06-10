"""Model balancing / recompute tests (converted from backend/scripts/smoke_model_balancing.py)."""
import unittest

from backend.app.models.model_state import ModelCell
from backend.app.services.model_balancing import compute_income_statement
from backend.tests.model_fixtures import make_minimal_state


class TestModelBalancing(unittest.TestCase):
    def test_compute_income_statement_minimal(self):
        s = make_minimal_state()
        s2 = compute_income_statement(s)
        rev = s2.income_statement["revenue"]["2026Y"].value
        assert abs(rev - 1100.0) < 0.01, f"revenue should be 1000 * 1.10 = 1100, got {rev}"
        gp = s2.income_statement["gross_profit"]["2026Y"].value
        assert abs(gp - 550.0) < 0.01, f"gross_profit should be 1100 * 0.50 = 550, got {gp}"
        ebit = s2.income_statement["ebit"]["2026Y"].value
        # EBIT = revenue - cogs - sga - rd - other_opex - da
        #      = 1100 - 550 - 220 - 55 - 0 - 55 = 220
        assert abs(ebit - 220.0) < 0.01, f"ebit got {ebit}"
        ni = s2.income_statement["net_income"]["2026Y"].value
        # NI = EBIT * (1 - tax) = 220 * 0.79 = 173.80   (no interest)
        assert abs(ni - 173.8) < 0.01, f"net_income got {ni}"

    def test_full_rollforward_balances(self):
        s = make_minimal_state()
        # Add minimal historical BS for rollforward seed
        s.balance_sheet["cash_and_equivalents"]["2025Y"] = ModelCell(value=200.0, source="historical")
        s.balance_sheet["accounts_receivable"]["2025Y"] = ModelCell(value=120.0, source="historical")
        s.balance_sheet["inventory"]["2025Y"] = ModelCell(value=80.0, source="historical")
        s.balance_sheet["other_current_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["ppe_net"]["2025Y"] = ModelCell(value=400.0, source="historical")
        s.balance_sheet["goodwill"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["other_long_term_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["accounts_payable"]["2025Y"] = ModelCell(value=110.0, source="historical")
        s.balance_sheet["short_term_debt"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["other_current_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["long_term_debt"]["2025Y"] = ModelCell(value=200.0, source="historical")
        s.balance_sheet["other_long_term_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
        s.balance_sheet["common_equity"]["2025Y"] = ModelCell(value=200.0, source="historical")
        s.balance_sheet["retained_earnings"]["2025Y"] = ModelCell(value=290.0, source="historical")
        # 2025 BS check: assets = 800; liabilities = 310; equity = 490 → balances ✓

        from backend.app.services.model_balancing import recompute
        s2 = recompute(s)

        assets = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in [
            "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
            "ppe_net", "goodwill", "other_long_term_assets",
        ])
        liab = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in [
            "accounts_payable", "short_term_debt", "other_current_liabilities",
            "long_term_debt", "other_long_term_liabilities",
        ])
        eq = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in ["common_equity", "retained_earnings"])
        diff = assets - (liab + eq)
        assert abs(diff) < 1.0, f"BS imbalance: assets={assets}, liab+eq={liab+eq}, diff={diff}"

    def test_statement_overrides_survive_recompute(self):
        """A user override should remain the stored value after the recompute pass."""
        from backend.app.services.model_balancing import recompute

        s = make_minimal_state()
        s.income_statement["net_income"]["2026Y"] = ModelCell(value=9999.0, source="override")
        s.cash_flow["free_cash_flow"]["2026Y"] = ModelCell(value=7777.0, source="override")
        s.balance_sheet["cash_and_equivalents"]["2026Y"] = ModelCell(value=5555.0, source="override")

        s2 = recompute(s)

        assert s2.income_statement["net_income"]["2026Y"].value == 9999.0
        assert s2.income_statement["net_income"]["2026Y"].source == "override"
        assert s2.cash_flow["free_cash_flow"]["2026Y"].value == 7777.0
        assert s2.cash_flow["free_cash_flow"]["2026Y"].source == "override"
        assert s2.balance_sheet["cash_and_equivalents"]["2026Y"].value == 5555.0
        assert s2.balance_sheet["cash_and_equivalents"]["2026Y"].source == "override"

    def test_share_count_rolls_forward_without_forecast_seed(self):
        """Baseline states may only have historical share count; forecast shares should still populate."""
        from backend.app.services.model_balancing import recompute

        s = make_minimal_state()
        del s.income_statement["shares_diluted"]["2026Y"]

        s2 = recompute(s)

        shares = s2.income_statement["shares_diluted"]["2026Y"]
        assert shares.value == 100.0, f"expected historical shares to roll forward, got {shares.value}"
        assert shares.source == "computed"
        assert s2.income_statement["eps_diluted"]["2026Y"].value != 0.0


if __name__ == "__main__":
    unittest.main()
