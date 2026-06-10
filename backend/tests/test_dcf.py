"""Pure DCF engine tests (converted from backend/scripts/smoke_dcf.py)."""
import unittest

from backend.app.services.dcf import dcf
from backend.tests.model_fixtures import make_flat_fixture


class TestDcf(unittest.TestCase):
    def test_flat_dcf_exit_multiple(self):
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

    def test_flat_dcf_perpetuity(self):
        state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
        result = dcf(state, terminal_method="perpetuity")
        # PV of 5 FCFs = 379.08
        # Terminal (perp at g=2.5%): TV = 100 * 1.025 / (0.10 - 0.025) = 1366.67
        # PV terminal = 1366.67 / 1.10^5 = 848.42
        # Intrinsic = 379.08 + 848.42 = 1227.50
        expected = 1227.50
        assert abs(result.intrinsic_value - expected) < 1.0, f"perpetuity DCF mismatch: got {result.intrinsic_value}"

    def test_dcf_discount_override(self):
        state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
        base = dcf(state).intrinsic_value
        higher = dcf(state, discount_rate=0.15).intrinsic_value
        assert higher < base, f"higher discount must reduce intrinsic; got {higher} >= {base}"


if __name__ == "__main__":
    unittest.main()
