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


if __name__ == "__main__":
    test_get_model_for_unknown_ticker()
    print("OK: smoke_models_api (Task 18) passed")
    sys.exit(0)
