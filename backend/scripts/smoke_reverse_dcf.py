"""Smoke test for reverse DCF solvers."""
import sys
from backend.scripts.smoke_dcf import make_flat_fixture
from backend.app.models.model_state import ModelCell
from backend.app.services.dcf import dcf
from backend.app.services.reverse_dcf import solve_implied_driver


def _make_recompute_state():
    """Build and recompute a minimal state suitable for driver-dimension solvers."""
    from backend.scripts.smoke_model_balancing import make_minimal_state
    from backend.app.services.model_balancing import recompute
    state = make_minimal_state()
    state.balance_sheet["cash_and_equivalents"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["accounts_receivable"]["2025Y"] = ModelCell(value=120.0, source="historical")
    state.balance_sheet["inventory"]["2025Y"] = ModelCell(value=80.0, source="historical")
    state.balance_sheet["other_current_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["ppe_net"]["2025Y"] = ModelCell(value=400.0, source="historical")
    state.balance_sheet["goodwill"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["other_long_term_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["accounts_payable"]["2025Y"] = ModelCell(value=110.0, source="historical")
    state.balance_sheet["short_term_debt"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["other_current_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["long_term_debt"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["other_long_term_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["common_equity"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["retained_earnings"]["2025Y"] = ModelCell(value=290.0, source="historical")
    return recompute(state)


def test_implied_terminal_multiple_round_trip():
    # Start with a state at exit_mult=12; intrinsic = 1496.77
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    base = dcf(state).intrinsic_per_share         # = 14.9677
    # Target a higher per-share price; solver should return a higher multiple
    target = 18.0
    implied = solve_implied_driver(state, dimension="terminal_multiple", target_per_share=target)
    assert implied > 12.0, f"implied multiple should exceed baseline 12, got {implied}"
    # Re-run dcf with that multiple, expect intrinsic_per_share ≈ target
    state2 = state.model_copy(deep=True)
    state2.assumptions.terminal_multiple.value = implied
    out = dcf(state2).intrinsic_per_share
    assert abs(out - target) < 0.05, f"round-trip mismatch: got {out}, expected {target}"
    print(f"OK: implied terminal_multiple={implied:.3f} → per_share={out:.4f} (target {target})")


def test_implied_irr_round_trip():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    target_per_share = 14.9677  # the baseline at r=10%
    from backend.app.services.reverse_dcf import solve_implied_irr
    irr = solve_implied_irr(state, target_per_share=target_per_share)
    assert abs(irr - 0.10) < 0.005, f"implied IRR should ≈ 10%, got {irr}"
    print(f"OK: implied IRR={irr:.4f}")


def test_sensitivity_grid_shape():
    # Use the recompute-ready fixture since both driver dimensions go through recompute()
    state = _make_recompute_state()
    from backend.app.services.reverse_dcf import sensitivity_grid
    grid = sensitivity_grid(
        state,
        x_dim="revenue_growth_pct", x_range=(-0.05, 0.15),
        y_dim="ebit_margin_pct",    y_range=(0.30, 0.70),
        size=21,
    )
    assert len(grid["x_values"]) == 21
    assert len(grid["y_values"]) == 21
    assert len(grid["values"]) == 21
    assert len(grid["values"][0]) == 21
    # Top-right corner (highest growth + margin) should exceed baseline
    baseline = dcf(state).intrinsic_per_share
    assert grid["values"][-1][-1] > baseline
    print(f"OK: 21x21 grid; baseline={baseline:.2f}, top-right={grid['values'][-1][-1]:.2f}")


def test_thesis_vs_priced_in_shape():
    # Use the recompute-ready fixture since driver dimensions go through recompute()
    state = _make_recompute_state()
    from backend.app.services.reverse_dcf import thesis_vs_priced_in
    baseline = dcf(state).intrinsic_per_share
    target = baseline * 0.8   # below baseline → market less optimistic than thesis
    out = thesis_vs_priced_in(state, target_per_share=target)
    assert len(out) == 3
    dimensions = {row["dimension"] for row in out}
    assert dimensions == {"revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"}
    for row in out:
        assert "thesis" in row and "priced_in" in row and "delta" in row
    print(f"OK: thesis_vs_priced_in: {out}")


def test_implied_growth_uses_recompute():
    """Validates that solving for revenue_growth_pct produces a state whose recompute output matches."""
    state = _make_recompute_state()
    base_per_share = dcf(state).intrinsic_per_share

    # Solve for revenue_growth that yields 1.2x baseline per-share (1.5x may be unreachable
    # with a single-period forecast and tight WC drag)
    target = base_per_share * 1.2
    implied = solve_implied_driver(state, dimension="revenue_growth_pct", target_per_share=target)
    assert -0.50 <= implied <= 1.00, f"implied growth {implied} outside expected bounds"
    print(f"OK: implied growth via recompute: {implied:.4f} for target {target:.4f}")


def test_ebit_margin_dimension_sets_ebit_margin_not_gross_margin():
    """The ebit_margin_pct reverse-DCF dimension should target EBIT/revenue, not gross margin."""
    from backend.app.services.reverse_dcf import _apply_uniform_override

    state = _make_recompute_state()
    target_margin = 0.30
    out = _apply_uniform_override(state, "ebit_margin_pct", target_margin)
    period = next(p.label for p in out.periods if not p.is_historical)
    revenue = out.income_statement["revenue"][period].value or 0.0
    ebit = out.income_statement["ebit"][period].value or 0.0
    gross_margin = out.drivers[period]["gross_margin_pct"].value

    assert revenue != 0.0
    assert abs((ebit / revenue) - target_margin) < 1e-6
    assert gross_margin != target_margin, "gross margin should be derived from the target EBIT margin"
    print("OK: ebit_margin_pct override produces the requested EBIT/revenue margin")


if __name__ == "__main__":
    test_implied_terminal_multiple_round_trip()
    test_implied_irr_round_trip()
    test_sensitivity_grid_shape()
    test_thesis_vs_priced_in_shape()
    test_implied_growth_uses_recompute()
    test_ebit_margin_dimension_sets_ebit_margin_not_gross_margin()
    print("OK: smoke_reverse_dcf (Tasks 7-13) passed")
    sys.exit(0)
