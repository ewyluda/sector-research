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


if __name__ == "__main__":
    test_generate_baseline_drivers_with_mock()
    print("OK: smoke_model_baseline (Task 15) passed")
    sys.exit(0)
