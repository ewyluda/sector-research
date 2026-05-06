"""Smoke test for the pure DCF engine."""
import sys
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF, DRIVER_KEYS,
)
from backend.app.services.dcf import dcf


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


def test_flat_dcf_exit_multiple():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    result = dcf(state)
    # PV of 5 yearly FCFs of 100 @ 10% = 100 * (1 - 1.10^-5) / 0.10 = 379.0787
    # Terminal = EBITDA(year 5) * 12 = 1800; PV @ 10% / (1.10^5) = 1117.69
    # Total intrinsic = 379.08 + 1117.69 = 1496.77
    expected = 1496.77
    actual = result.intrinsic_value
    assert abs(actual - expected) < 1.0, f"intrinsic_value mismatch: got {actual}, expected ≈ {expected}"
    expected_per_share = expected / 100.0
    assert abs(result.intrinsic_per_share - expected_per_share) < 0.01, f"per_share mismatch: got {result.intrinsic_per_share}"
    print(f"OK: flat exit-multiple DCF: intrinsic={actual:.2f} per_share={result.intrinsic_per_share:.4f}")


if __name__ == "__main__":
    test_flat_dcf_exit_multiple()
    print("OK: smoke_dcf passed")
    sys.exit(0)
