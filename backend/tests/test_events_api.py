"""Pins the /api/events contract: list filters, dismissal, 404s, and the
fire-and-forget scan trigger."""

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.events import router
from backend.app.db import get_db


def make_app() -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    db = MagicMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.state.edgar = MagicMock()
    app.state.fmp = MagicMock()
    return TestClient(app), db


def _event(**over):
    base = dict(
        id="ev-1", ticker="NVDA", event_type="guidance", materiality="high",
        headline="Guidance cut", summary="Cut FY outlook.", item_codes="2.02",
        filing_date=date(2026, 6, 8), dismissed_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class ListEventsTests(unittest.TestCase):
    def test_list_returns_events(self):
        client, db = make_app()
        result = MagicMock()
        result.all.return_value = [(_event(), "https://sec.gov/doc.htm")]
        db.execute = AsyncMock(return_value=result)

        resp = client.get("/api/events?since_days=14")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["events"][0]["ticker"], "NVDA")
        self.assertEqual(body["events"][0]["filing_date"], "2026-06-08")
        self.assertEqual(body["events"][0]["document_url"], "https://sec.gov/doc.htm")

    def test_since_days_validation(self):
        client, _ = make_app()
        self.assertEqual(client.get("/api/events?since_days=0").status_code, 422)
        self.assertEqual(client.get("/api/events?since_days=400").status_code, 422)


class DismissTests(unittest.TestCase):
    def test_dismiss_404_unknown(self):
        client, db = make_app()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result)
        resp = client.post("/api/events/nope/dismiss")
        self.assertEqual(resp.status_code, 404)

    def test_dismiss_sets_timestamp_and_commits(self):
        client, db = make_app()
        ev = _event()
        result = MagicMock()
        result.scalar_one_or_none.return_value = ev
        db.execute = AsyncMock(return_value=result)
        db.commit = AsyncMock()

        resp = client.post("/api/events/ev-1/dismiss")
        self.assertEqual(resp.status_code, 204)
        self.assertIsNotNone(ev.dismissed_at)
        db.commit.assert_awaited()


class ScanTriggerTests(unittest.TestCase):
    def test_scan_returns_202(self):
        client, _ = make_app()
        with patch(
            "backend.app.services.material_events_scheduler.run_daily_material_scan",
            new=AsyncMock(return_value={}),
        ):
            resp = client.post("/api/events/scan")
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json(), {"started": True})


if __name__ == "__main__":
    unittest.main()
