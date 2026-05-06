# backend/scripts/smoke_models_api.py
import sys
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.db import get_db


async def _null_db_override():
    """Async generator dependency override — yields a mock session returning None for all scalars."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    yield mock_session


def _patched_client():
    """TestClient with get_db overridden to return null results (no real DB needed)."""
    app.dependency_overrides[get_db] = _null_db_override
    return TestClient(app)


# ---------------------------------------------------------------------------
# Task 18 tests
# ---------------------------------------------------------------------------

def test_get_model_for_unknown_ticker():
    c = _patched_client()
    r = c.get("/api/models/UNKNOWNZZZ")
    app.dependency_overrides.clear()
    assert r.status_code == 200, f"expected 200, got {r.status_code}"
    body = r.json()
    assert body["latest_version"] is None
    assert body["draft"] is None
    print("OK: GET unknown ticker returns null payload")


# ---------------------------------------------------------------------------
# Task 19 tests
# ---------------------------------------------------------------------------

def test_apply_edit_driver():
    from backend.app.api.models_api import _apply_edit, DraftEditRequest
    state_dict = {
        "drivers": {"2026Y": {"gross_margin_pct": {"value": 0.50, "source": "driver"}}},
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "assumptions": {},
    }
    edit = DraftEditRequest(cell_path="drivers.2026Y.gross_margin_pct", value=0.55, source="driver")
    out = _apply_edit(state_dict, edit)
    assert out["drivers"]["2026Y"]["gross_margin_pct"]["value"] == 0.55
    assert out["drivers"]["2026Y"]["gross_margin_pct"]["source"] == "driver"
    print("OK: _apply_edit on driver cell")


def test_apply_edit_unknown_shape_raises():
    from backend.app.api.models_api import _apply_edit, DraftEditRequest
    edit = DraftEditRequest(cell_path="bogus.path", value=1.0)
    try:
        _apply_edit(
            {"drivers": {}, "income_statement": {}, "balance_sheet": {}, "cash_flow": {}, "assumptions": {}},
            edit,
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    print("OK: _apply_edit rejects unknown cell_path shape")


# ---------------------------------------------------------------------------
# Task 20 tests
# ---------------------------------------------------------------------------

def test_save_with_no_draft_returns_404():
    c = _patched_client()
    r = c.post("/api/models/UNKNOWN_NODRAFT/save", json={"label": "test"})
    app.dependency_overrides.clear()
    assert r.status_code == 404, f"expected 404, got {r.status_code}"
    print("OK: POST /save returns 404 when no draft exists")


if __name__ == "__main__":
    test_get_model_for_unknown_ticker()
    test_apply_edit_driver()
    test_apply_edit_unknown_shape_raises()
    test_save_with_no_draft_returns_404()
    print("OK: smoke_models_api (Task 20) passed")
    sys.exit(0)
