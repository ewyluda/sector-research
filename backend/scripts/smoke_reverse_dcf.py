"""Smoke test for reverse DCF solvers."""
import sys
from backend.scripts.smoke_dcf import make_flat_fixture
from backend.app.services.dcf import dcf
from backend.app.services.reverse_dcf import solve_implied_driver


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


if __name__ == "__main__":
    test_implied_terminal_multiple_round_trip()
    print("OK: smoke_reverse_dcf (Task 7) passed")
    sys.exit(0)
