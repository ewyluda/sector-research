"""POST /api/runs/{run_id}/abandon — mark stuck pipeline runs abandoned.

Real-SQL tests over in-memory sqlite (raw DDL, same pattern as
test_questions_api.py). SQLite doesn't enforce FKs, so the theme parent
is safe to omit.
"""

import asyncio
import os
import unittest
import uuid

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api.pipeline import abandon_run
from backend.app.models.research_run import ResearchRun

_DDL_RESEARCH_RUNS = """
CREATE TABLE IF NOT EXISTS research_runs (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    theme_id TEXT,
    phase TEXT NOT NULL,
    status TEXT NOT NULL,
    state TEXT NOT NULL,
    loop_count INTEGER NOT NULL DEFAULT 0,
    archived_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_TEST_ENGINES = []


def _build_async_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.execute(text(_DDL_RESEARCH_RUNS))

    asyncio.run(_setup())
    _TEST_ENGINES.append(engine)
    Session = sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)
    return engine, Session


def tearDownModule():
    """Dispose engines so aiosqlite worker threads exit before interpreter
    shutdown (same hang-avoidance as test_outcome_tracker.py)."""

    async def _dispose():
        for engine in _TEST_ENGINES:
            await engine.dispose()

    asyncio.run(_dispose())
    _TEST_ENGINES.clear()


def _run_row(**over) -> ResearchRun:
    base = dict(
        id=str(uuid.uuid4()),
        ticker="ORCL",
        theme_id=None,
        phase="deep_dive",
        status="in_progress",
        state={},
        loop_count=0,
    )
    base.update(over)
    return ResearchRun(**base)


class AbandonRunTests(unittest.TestCase):
    def _abandon(self, status: str):
        """Insert a run with the given status, call the endpoint, return (result_or_exc, run)."""
        _, Session = _build_async_test_session()

        async def _go():
            async with Session() as db:
                run = _run_row(status=status)
                db.add(run)
                await db.commit()
                try:
                    result = await abandon_run(run.id, db)
                except HTTPException as exc:
                    result = exc
                refreshed = await db.get(ResearchRun, run.id)
                return result, refreshed

        return asyncio.run(_go())

    def test_abandon_in_progress_run(self):
        result, run = self._abandon("in_progress")
        self.assertEqual(result, {"run_id": run.id, "status": "abandoned"})
        self.assertEqual(run.status, "abandoned")

    def test_abandon_paused_run(self):
        result, run = self._abandon("paused")
        self.assertEqual(result, {"run_id": run.id, "status": "abandoned"})
        self.assertEqual(run.status, "abandoned")

    def test_abandon_completed_run_409(self):
        result, run = self._abandon("completed")
        self.assertIsInstance(result, HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(run.status, "completed")

    def test_abandon_watchlist_run_409(self):
        result, run = self._abandon("watchlist")
        self.assertIsInstance(result, HTTPException)
        self.assertEqual(result.status_code, 409)
        self.assertEqual(run.status, "watchlist")

    def test_abandon_missing_run_404(self):
        _, Session = _build_async_test_session()

        async def _go():
            async with Session() as db:
                try:
                    await abandon_run(str(uuid.uuid4()), db)
                except HTTPException as exc:
                    return exc
                return None

        exc = asyncio.run(_go())
        self.assertIsInstance(exc, HTTPException)
        self.assertEqual(exc.status_code, 404)


if __name__ == "__main__":
    unittest.main()
