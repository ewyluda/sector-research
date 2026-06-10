"""Pins the /api/catalysts/calendar contract: route ordering ('calendar'
must NOT be swallowed by /catalysts/{catalyst_id} — same footgun as
peers /compare), range validation, and response pass-through."""
import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.catalysts import router
from backend.app.db import get_db
from backend.app.services.calendar_events import CalendarEvent, CalendarResponse


def make_client() -> tuple[TestClient, AsyncMock]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = AsyncMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.state.fmp = AsyncMock()
    return TestClient(app), app.state.fmp


def _fake_response() -> CalendarResponse:
    return CalendarResponse(
        events=[CalendarEvent(
            kind="earnings", date=date(2026, 6, 10), ticker="NVDA",
            title="NVDA", detail={"has_thesis": True, "run_id": "run-1"},
        )],
        universe_size=12,
        warnings=[],
    )


class CalendarRouteTests(unittest.TestCase):
    def test_calendar_not_shadowed_by_catalyst_id_route(self):
        # Without correct declaration order, GET /api/catalysts/calendar
        # hits /catalysts/{catalyst_id} with id='calendar'. With it, the
        # missing start/end query params produce a 422 from the calendar
        # route itself.
        client, _ = make_client()
        resp = client.get("/api/catalysts/calendar")
        self.assertEqual(resp.status_code, 422)
        detail = str(resp.json())
        self.assertIn("start", detail)
        self.assertIn("end", detail)

    def test_start_after_end_rejected(self):
        client, _ = make_client()
        resp = client.get("/api/catalysts/calendar?start=2026-06-22&end=2026-06-08")
        self.assertEqual(resp.status_code, 422)

    def test_range_over_120_days_rejected(self):
        client, _ = make_client()
        resp = client.get("/api/catalysts/calendar?start=2026-01-01&end=2026-06-01")
        self.assertEqual(resp.status_code, 422)

    def test_exactly_120_day_range_accepted(self):
        client, _ = make_client()
        with patch(
            "backend.app.api.catalysts.get_calendar_events",
            new=AsyncMock(return_value=_fake_response()),
        ):
            resp = client.get("/api/catalysts/calendar?start=2026-01-01&end=2026-05-01")
        self.assertEqual(resp.status_code, 200)

    def test_happy_path_passes_through_service_response(self):
        client, fmp = make_client()
        with patch(
            "backend.app.api.catalysts.get_calendar_events",
            new=AsyncMock(return_value=_fake_response()),
        ) as svc:
            resp = client.get("/api/catalysts/calendar?start=2026-06-08&end=2026-06-22")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["universe_size"], 12)
        self.assertEqual(body["events"][0]["kind"], "earnings")
        self.assertEqual(body["events"][0]["detail"]["run_id"], "run-1")
        # service received parsed dates and the shared FMP singleton
        args = svc.await_args.args
        self.assertEqual(args[2], date(2026, 6, 8))
        self.assertEqual(args[3], date(2026, 6, 22))
        self.assertIs(args[1], fmp)


if __name__ == "__main__":
    unittest.main()
