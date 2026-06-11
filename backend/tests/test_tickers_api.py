"""Pins GET /api/tickers contract: distinct upper-cased tickers from
theme seed_tickers ∪ research_runs.ticker ∪ ticker_models.ticker, sorted."""

import os
import unittest
from types import SimpleNamespace
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

from backend.app.api.tickers import router
from backend.app.db import get_db


def make_app() -> tuple[TestClient, MagicMock]:
    app = FastAPI()
    app.include_router(router)
    db = MagicMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app), db


def _db_with_three_sources() -> MagicMock:
    """Three execute() calls in order: themes, research_runs, ticker_models."""
    db = MagicMock()

    # Theme with seed_tickers=["NVDA"]
    theme = SimpleNamespace(seed_tickers=["NVDA"])
    themes_result = MagicMock()
    themes_result.scalars.return_value.all.return_value = [theme]

    # research_run ticker = "ORCL"
    runs_result = MagicMock()
    runs_result.all.return_value = [("ORCL",)]

    # ticker_model ticker = "MSFT"
    models_result = MagicMock()
    models_result.all.return_value = [("MSFT",)]

    db.execute = AsyncMock(side_effect=[themes_result, runs_result, models_result])
    return db


class ListTickersTests(unittest.TestCase):
    def test_returns_all_three_sources_sorted(self):
        app = FastAPI()
        app.include_router(router)
        db = _db_with_three_sources()

        async def _fake_db():
            yield db

        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp = client.get("/api/tickers")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        tickers = [r["ticker"] for r in body]
        # All three present, sorted alphabetically
        self.assertEqual(tickers, ["MSFT", "NVDA", "ORCL"])

    def test_duplicate_ticker_across_sources_appears_once(self):
        """Same ticker in research_run AND ticker_model → deduplicated."""
        app = FastAPI()
        app.include_router(router)
        db = MagicMock()

        theme = SimpleNamespace(seed_tickers=[])
        themes_result = MagicMock()
        themes_result.scalars.return_value.all.return_value = [theme]

        runs_result = MagicMock()
        runs_result.all.return_value = [("NVDA",)]

        models_result = MagicMock()
        models_result.all.return_value = [("NVDA",)]

        db.execute = AsyncMock(side_effect=[themes_result, runs_result, models_result])

        async def _fake_db():
            yield db

        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp = client.get("/api/tickers")
        tickers = [r["ticker"] for r in resp.json()]
        self.assertEqual(tickers, ["NVDA"])

    def test_lowercase_stored_values_are_uppercased(self):
        """Tickers stored lower-case in the DB are returned upper-case."""
        app = FastAPI()
        app.include_router(router)
        db = MagicMock()

        theme = SimpleNamespace(seed_tickers=["nvda"])
        themes_result = MagicMock()
        themes_result.scalars.return_value.all.return_value = [theme]

        runs_result = MagicMock()
        runs_result.all.return_value = [("orcl",)]

        models_result = MagicMock()
        models_result.all.return_value = [("msft",)]

        db.execute = AsyncMock(side_effect=[themes_result, runs_result, models_result])

        async def _fake_db():
            yield db

        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp = client.get("/api/tickers")
        tickers = [r["ticker"] for r in resp.json()]
        self.assertEqual(tickers, ["MSFT", "NVDA", "ORCL"])

    def test_legacy_dict_entries_in_seed_tickers_are_skipped(self):
        """Legacy JSONB rows may contain dicts like {"ticker": "NVDA"} — skip them."""
        app = FastAPI()
        app.include_router(router)
        db = MagicMock()

        theme = SimpleNamespace(seed_tickers=[{"ticker": "nvda"}, "AMD", {"other": "x"}])
        themes_result = MagicMock()
        themes_result.scalars.return_value.all.return_value = [theme]

        runs_result = MagicMock()
        runs_result.all.return_value = []

        models_result = MagicMock()
        models_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[themes_result, runs_result, models_result])

        async def _fake_db():
            yield db

        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp = client.get("/api/tickers")
        # dict entries skipped, "AMD" string entry kept
        tickers = [r["ticker"] for r in resp.json()]
        self.assertEqual(tickers, ["AMD"])

    def test_empty_sources_returns_empty_list(self):
        app = FastAPI()
        app.include_router(router)
        db = MagicMock()

        themes_result = MagicMock()
        themes_result.scalars.return_value.all.return_value = []

        runs_result = MagicMock()
        runs_result.all.return_value = []

        models_result = MagicMock()
        models_result.all.return_value = []

        db.execute = AsyncMock(side_effect=[themes_result, runs_result, models_result])

        async def _fake_db():
            yield db

        app.dependency_overrides[get_db] = _fake_db
        client = TestClient(app)

        resp = client.get("/api/tickers")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])


if __name__ == "__main__":
    unittest.main()
