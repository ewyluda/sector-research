"""services/universe: resolvers over mocked sessions — seeds ∪ active theses,
uppercasing, duplicate-thesis handling, per-theme bucketing.

Migrated from test_calendar_events.py::GetUniverseTests when the
calendar_events re-export shim was retired (post-PR-#62 follow-up).
"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.universe import resolve_universe, resolve_universe_by_theme
from backend.tests.db_mocks import FakeResult as _Result


def _theme(theme_id: str, seeds) -> SimpleNamespace:
    return SimpleNamespace(id=theme_id, seed_tickers=seeds)


class ResolveUniverseTests(unittest.IsolatedAsyncioTestCase):
    async def test_union_of_seeds_and_active_theses_uppercased(self):
        db = AsyncMock()
        db.execute.side_effect = [
            # select(Theme) rows
            _Result([
                _theme("t1", ["nvda", "ASML"]),
                _theme("t2", ["amd"]),
                _theme("t3", None),  # legacy non-list JSONB → treated as empty
            ]),
            # latest-runs CTE rows (status board semantics)
            _Result([
                {"ticker": "NVDA", "id": "run-nvda-1"},
                {"ticker": "pltr", "id": "run-pltr-1"},
            ]),
        ]

        universe = await resolve_universe(db)

        self.assertEqual(universe.tickers, {"NVDA", "ASML", "AMD", "PLTR"})
        self.assertEqual(
            universe.thesis_runs,
            {"NVDA": "run-nvda-1", "PLTR": "run-pltr-1"},
        )

    async def test_duplicate_thesis_ticker_keeps_first_run(self):
        # DISTINCT ON (ticker, theme_id) can emit one row per theme for the
        # same ticker; the first row wins (setdefault).
        db = AsyncMock()
        db.execute.side_effect = [
            _Result([]),
            _Result([
                {"ticker": "NVDA", "id": "run-a"},
                {"ticker": "NVDA", "id": "run-b"},
            ]),
        ]

        universe = await resolve_universe(db)

        self.assertEqual(universe.thesis_runs, {"NVDA": "run-a"})


class ResolveUniverseByThemeTests(unittest.IsolatedAsyncioTestCase):
    async def test_seeds_and_theses_bucketed_per_theme(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _Result([_theme("t1", ["nvda"]), _theme("t2", [])]),
            _Result([
                {"ticker": "pltr", "id": "run-1", "theme_id": "t2"},
            ]),
        ]

        out = await resolve_universe_by_theme(db)

        self.assertEqual(out, {"t1": {"NVDA"}, "t2": {"PLTR"}})


if __name__ == "__main__":
    unittest.main()
