"""Smoke for cell-path-keyed JSON diff between ModelStates."""
import sys
from copy import deepcopy
from backend.scripts.smoke_model_balancing import make_minimal_state
from backend.app.services.model_diff import diff_states


def test_diff_single_driver_change():
    a = make_minimal_state()
    b = deepcopy(a)
    b.drivers["2026Y"]["gross_margin_pct"].value = 0.55  # was 0.50
    d = diff_states(a, b)
    assert d["added"] == [], f"expected no adds, got {d['added']}"
    assert d["removed"] == [], f"expected no removes, got {d['removed']}"
    changed_paths = [c["cell_path"] for c in d["changed"]]
    assert "drivers.2026Y.gross_margin_pct" in changed_paths, f"diff missed driver change: {changed_paths}"
    print("OK: model_diff detects driver change")


if __name__ == "__main__":
    test_diff_single_driver_change()
    print("OK: smoke_model_diff passed")
    sys.exit(0)
