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


# Real UUIDs: material_events.id is a UUID column, and EventIdPath now
# 404s synthetic ids like "ev-1" before the handler runs.
EV_1 = "8b6d3c2e-1f4a-4b9c-9d7e-0a1b2c3d4e5f"
EV_2 = "3f2e1d0c-9b8a-4756-8493-a2b1c0d9e8f7"


def _event(**over):
    base = dict(
        id=EV_1, ticker="NVDA", event_type="guidance", materiality="high",
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

    def test_groups_same_ticker_type_within_4_days(self):
        # two APLD financing events 2 days apart → one item, group_count=2,
        # primary = newest, member ids/headlines carry both
        client, db = make_app()
        newer = _event(
            id="ev-new", ticker="APLD", event_type="financing",
            headline="Raise A", filing_date=date(2026, 6, 8),
        )
        older = _event(
            id="ev-old", ticker="APLD", event_type="financing",
            headline="Raise B", filing_date=date(2026, 6, 6),
        )
        result = MagicMock()
        result.all.return_value = [(newer, "https://sec.gov/a.htm"), (older, "https://sec.gov/b.htm")]
        db.execute = AsyncMock(return_value=result)

        body = client.get("/api/events").json()
        self.assertEqual(body["total"], 1)
        item = body["events"][0]
        self.assertEqual(item["id"], "ev-new")
        self.assertEqual(item["group_count"], 2)
        self.assertEqual(set(item["group_member_ids"]), {"ev-new", "ev-old"})
        self.assertEqual(item["group_headlines"], ["Raise A", "Raise B"])
        self.assertEqual(item["document_url"], "https://sec.gov/a.htm")

    def test_does_not_group_across_type_or_window(self):
        client, db = make_app()
        financing = _event(id="e1", event_type="financing", filing_date=date(2026, 6, 8))
        guidance = _event(id="e2", event_type="guidance", filing_date=date(2026, 6, 8))
        far = _event(id="e3", event_type="financing", filing_date=date(2026, 6, 1))
        result = MagicMock()
        result.all.return_value = [(financing, None), (guidance, None), (far, None)]
        db.execute = AsyncMock(return_value=result)

        body = client.get("/api/events").json()
        self.assertEqual(body["total"], 3)
        self.assertTrue(all(e["group_count"] == 1 for e in body["events"]))


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

        resp = client.post(f"/api/events/{EV_1}/dismiss?group=false")
        self.assertEqual(resp.status_code, 204)
        self.assertIsNotNone(ev.dismissed_at)
        db.commit.assert_awaited()

    def test_dismiss_group_dismisses_members(self):
        # ?group=true (the default) sets dismissed_at on every undismissed
        # member within the (ticker, event_type, ±4d-of-primary) window
        client, db = make_app()
        primary = _event(id=EV_1)
        member = _event(id=EV_2, filing_date=date(2026, 6, 6))

        lookup = MagicMock()
        lookup.scalar_one_or_none.return_value = primary
        members = MagicMock()
        members.scalars.return_value.all.return_value = [primary, member]
        db.execute = AsyncMock(side_effect=[lookup, members])
        db.commit = AsyncMock()

        resp = client.post(f"/api/events/{EV_1}/dismiss")
        self.assertEqual(resp.status_code, 204)
        self.assertIsNotNone(primary.dismissed_at)
        self.assertIsNotNone(member.dismissed_at)
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
