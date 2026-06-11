"""Model diff tests (converted from backend/scripts/smoke_model_diff.py)."""
import unittest
from copy import deepcopy

from backend.app.services.model_diff import diff_states
from backend.tests.model_fixtures import make_minimal_state


class TestModelDiff(unittest.TestCase):
    def test_diff_single_driver_change(self):
        a = make_minimal_state()
        b = deepcopy(a)
        b.drivers["2026Y"]["gross_margin_pct"].value = 0.55  # was 0.50
        d = diff_states(a, b)
        assert d["added"] == [], f"expected no adds, got {d['added']}"
        assert d["removed"] == [], f"expected no removes, got {d['removed']}"
        changed_paths = [c["cell_path"] for c in d["changed"]]
        assert "drivers.2026Y.gross_margin_pct" in changed_paths, f"diff missed driver change: {changed_paths}"


if __name__ == "__main__":
    unittest.main()
