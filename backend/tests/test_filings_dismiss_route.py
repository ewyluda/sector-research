"""Pins the /api/filings/relationships/dismiss route contract.

Specifically: a double-dismiss race (two in-flight requests both pass the
existence check; the second hits the alias_normalized unique constraint at
commit time) must return 200 idempotently, not 500.
"""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from backend.app.api.filings import router
from backend.app.db import get_db
from backend.app.services.counterparty_resolver import normalize_name


def make_app(db) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.edgar = MagicMock()
    app.state.fanout = MagicMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


class TestDoubleDismissIdempotent(unittest.TestCase):
    def test_integrity_error_on_commit_returns_200(self):
        """Simulates the race: dismiss_counterparty succeeds (no pre-existing
        alias found), but commit raises IntegrityError (the loser of a
        concurrent double-click). Expect HTTP 200 with dismissed=True."""
        norm = normalize_name("OpenAI")

        db = AsyncMock()
        db.add = MagicMock()
        db.rollback = AsyncMock()

        # _existing_alias_for returns None → dismiss_counterparty succeeds
        alias_result = MagicMock()
        alias_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=alias_result)

        # commit raises the unique-constraint IntegrityError (loser of the race)
        db.commit = AsyncMock(
            side_effect=IntegrityError("unique violation", {}, Exception())
        )

        client = make_app(db)
        resp = client.post(
            "/api/relationships/dismiss",
            json={"counterparty_name": "OpenAI"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["dismissed"])
        self.assertEqual(body["alias_normalized"], norm)
        # rollback must have been called to clean up the failed transaction
        db.rollback.assert_awaited_once()

    def test_normal_dismiss_still_works(self):
        """Happy-path regression: a fresh dismiss with no race returns 200."""
        norm = normalize_name("PrivateCo")

        db = AsyncMock()
        db.add = MagicMock()
        db.rollback = AsyncMock()

        alias_result = MagicMock()
        alias_result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=alias_result)
        db.commit = AsyncMock()  # succeeds normally

        client = make_app(db)
        resp = client.post(
            "/api/relationships/dismiss",
            json={"counterparty_name": "PrivateCo"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["dismissed"])
        self.assertEqual(body["alias_normalized"], norm)
        db.rollback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
