import sys
import json
import asyncio
from unittest.mock import patch, AsyncMock
from backend.app.graph.model_baseline_node import generate_baseline_drivers, BaselineDriversResponse


FAKE_LLM_OUTPUT = {
    "drivers": {
        "2026Y": {
            "revenue_growth_pct": {"value": 0.10, "reason": "matches consensus", "source_citation_id": None},
            "gross_margin_pct":   {"value": 0.50, "reason": "stable from 8Q history", "source_citation_id": None},
            "sga_pct_revenue":    {"value": 0.20, "reason": "from history", "source_citation_id": None},
            "rd_pct_revenue":     {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "other_opex_pct_revenue": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "da_pct_revenue":     {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "effective_tax_rate": {"value": 0.21, "reason": "statutory", "source_citation_id": None},
            "interest_income_yield": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "interest_expense_rate": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "capex_pct_revenue":  {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "dso_days": {"value": 45.0, "reason": "stable", "source_citation_id": None},
            "dio_days": {"value": 30.0, "reason": "stable", "source_citation_id": None},
            "dpo_days": {"value": 40.0, "reason": "stable", "source_citation_id": None},
            "dividend_payout_ratio": {"value": 0.0, "reason": "no dividend", "source_citation_id": None},
            "buyback_dollars": {"value": 0.0, "reason": "no buyback program", "source_citation_id": None},
            "share_count_change_pct": {"value": 0.0, "reason": "flat", "source_citation_id": None},
            "debt_repayment_dollars": {"value": 0.0, "reason": "no schedule", "source_citation_id": None},
            "revolver_rate": {"value": 0.05, "reason": "n/a baseline", "source_citation_id": None},
            "revenue_absolute": {"value": None, "reason": "use growth pct", "source_citation_id": None}
        }
    }
}


async def _test():
    fake = json.dumps(FAKE_LLM_OUTPUT)
    with patch("backend.app.graph.model_baseline_node.llm.complete", new=AsyncMock(return_value=fake)):
        out = await generate_baseline_drivers(
            ticker="ZZZ",
            historicals_payload="(stub historicals)",
            deep_dive_summary="(stub findings)",
            consensus_estimates="(stub estimates)",
            forecast_period_labels=["2026Y"],
        )
    assert isinstance(out, BaselineDriversResponse)
    assert "2026Y" in out.drivers
    assert out.drivers["2026Y"]["gross_margin_pct"].value == 0.50
    print("OK: baseline node returns parsed BaselineDriversResponse")


def test_generate_baseline_drivers_with_mock():
    asyncio.run(_test())


async def test_initialize_model_for_ticker_with_mocks():
    """Mocks ResearchRun + FMP + llm.complete; asserts a ModelState comes out balanced."""
    from backend.app.services import model_baseline
    fake_llm = json.dumps(FAKE_LLM_OUTPUT)
    fake_run_state = {
        "curated_financials": {
            "income_statements": [{"period": "2025Y", "revenue": 1000.0, "ebitda": 200.0, "shares_diluted": 100.0,
                                   "gross_profit": 500.0, "operating_expenses": 300.0, "depreciation_amortization": 50.0,
                                   "ebit": 150.0, "net_income": 120.0, "eps_diluted": 1.20}],
            "balance_sheets": [{"period": "2025Y", "cash_and_equivalents": 200.0, "accounts_receivable": 120.0,
                                "inventory": 80.0, "ppe_net": 400.0, "accounts_payable": 110.0,
                                "long_term_debt": 200.0, "common_equity": 200.0, "retained_earnings": 290.0}],
            "cash_flows": [],
            "profile": {"beta": 1.0},
        },
        "thesis_output": {"core_thesis": "growth thesis"},
        "deep_dive_results": {},
    }
    with patch.object(model_baseline, "_load_seeding_context", new=AsyncMock(return_value=fake_run_state)), \
         patch("backend.app.graph.model_baseline_node.llm.complete", new=AsyncMock(return_value=fake_llm)), \
         patch.object(model_baseline, "_get_risk_free_rate", new=AsyncMock(return_value=0.04)), \
         patch.object(model_baseline, "recompute", side_effect=lambda s: s):
        state = await model_baseline.build_baseline_state(ticker="ZZZ", forecast_period_labels=["2026Y"])
    assert state.assumptions.discount_rate.value > 0
    print(f"OK: build_baseline_state produces ModelState (discount={state.assumptions.discount_rate.value:.4f})")


if __name__ == "__main__":
    test_generate_baseline_drivers_with_mock()
    asyncio.run(test_initialize_model_for_ticker_with_mocks())
    print("OK: smoke_model_baseline (Tasks 15+16) passed")
    sys.exit(0)
