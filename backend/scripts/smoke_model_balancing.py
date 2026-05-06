"""Smoke for the recompute pipeline."""
import sys
from backend.app.models.model_state import ModelState, ModelCell, Period, ModelAssumptions, DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF
from backend.app.services.model_balancing import compute_income_statement


def make_minimal_state() -> ModelState:
    historical_p = Period(label="2025Y", kind="Y", is_historical=True)
    forecast_p = Period(label="2026Y", kind="Y", is_historical=False)

    drivers = {
        "2025Y": {k: ModelCell(value=0.0, source="historical") for k in DRIVER_KEYS},
        "2026Y": {
            "revenue_growth_pct":   ModelCell(value=0.10, source="driver"),
            "revenue_absolute":     ModelCell(value=None, source="driver"),
            "gross_margin_pct":     ModelCell(value=0.50, source="driver"),
            "sga_pct_revenue":      ModelCell(value=0.20, source="driver"),
            "rd_pct_revenue":       ModelCell(value=0.05, source="driver"),
            "other_opex_pct_revenue": ModelCell(value=0.0, source="driver"),
            "da_pct_revenue":       ModelCell(value=0.05, source="driver"),
            "effective_tax_rate":   ModelCell(value=0.21, source="driver"),
            "interest_income_yield": ModelCell(value=0.0, source="driver"),
            "interest_expense_rate": ModelCell(value=0.0, source="driver"),
            "capex_pct_revenue":    ModelCell(value=0.05, source="driver"),
            "dso_days":             ModelCell(value=45.0, source="driver"),
            "dio_days":             ModelCell(value=30.0, source="driver"),
            "dpo_days":             ModelCell(value=40.0, source="driver"),
            "dividend_payout_ratio": ModelCell(value=0.0, source="driver"),
            "buyback_dollars":      ModelCell(value=0.0, source="driver"),
            "share_count_change_pct": ModelCell(value=0.0, source="driver"),
            "debt_repayment_dollars": ModelCell(value=0.0, source="driver"),
            "revolver_rate":        ModelCell(value=0.05, source="driver"),
        },
    }
    income_statement = {li: {} for li in LINE_ITEMS_PNL}
    income_statement["revenue"]["2025Y"] = ModelCell(value=1000.0, source="historical")
    income_statement["shares_diluted"]["2025Y"] = ModelCell(value=100.0, source="historical")
    income_statement["shares_diluted"]["2026Y"] = ModelCell(value=100.0, source="computed")
    balance_sheet = {li: {} for li in LINE_ITEMS_BS}
    cash_flow = {li: {} for li in LINE_ITEMS_CF}

    return ModelState(
        periods=[historical_p, forecast_p],
        drivers=drivers,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=0.10, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )


def test_compute_income_statement_minimal():
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
    print(f"OK: P&L compute: rev={rev} gp={gp} ebit={ebit} ni={ni}")


if __name__ == "__main__":
    test_compute_income_statement_minimal()
    print("OK: smoke_model_balancing (Task 11) passed")
    sys.exit(0)
