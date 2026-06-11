"""Shared ModelState fixtures for the math-core tests (moved from backend/scripts/smoke_*)."""
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF, DRIVER_KEYS,
)


def make_flat_fixture(fcf_per_year: float, share_count: float, discount: float, exit_mult: float, ebitda: float) -> ModelState:
    """5-year flat fixture: FCF = $100/yr, EBITDA = $150/yr, 100 shares, 10% discount, 12x EBITDA exit."""
    periods = [Period(label=str(2026 + i), kind="Y", is_historical=False) for i in range(5)]
    drivers = {p.label: {k: ModelCell(value=0.0, source="driver") for k in DRIVER_KEYS} for p in periods}
    income_statement = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_PNL}
    for p in periods:
        income_statement["ebitda"][p.label] = ModelCell(value=ebitda, source="computed")
        income_statement["shares_diluted"][p.label] = ModelCell(value=share_count, source="computed")
    cash_flow = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_CF}
    for p in periods:
        cash_flow["free_cash_flow"][p.label] = ModelCell(value=fcf_per_year, source="computed")
    balance_sheet = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_BS}

    return ModelState(
        periods=periods,
        drivers=drivers,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=discount, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=exit_mult, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )


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
