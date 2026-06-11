"""Pins unit_of_work commit/rollback semantics with a mock session.

The behavior under test is pure control flow — yield, commit on clean exit,
rollback on exception, propagate. No real DB is needed; we patch the
async_session factory to return a recording mock.
"""
import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")


class _RecordingSession:
    """Stand-in for AsyncSession that records commit/rollback/close calls."""
    def __init__(self):
        self.events: list[str] = []

    async def commit(self):
        self.events.append("commit")

    async def rollback(self):
        self.events.append("rollback")


def _patched_session_factory(session: _RecordingSession):
    """Return a callable that yields an async-context-manager wrapping `session`."""

    @asynccontextmanager
    async def _factory():
        yield session

    def caller():
        return _factory()

    return caller


class UnitOfWorkTests(unittest.IsolatedAsyncioTestCase):
    async def test_commits_on_clean_exit(self):
        sess = _RecordingSession()
        with patch("backend.app.db.async_session", _patched_session_factory(sess)):
            from backend.app.db import unit_of_work
            async with unit_of_work() as db:
                self.assertIs(db, sess)
        self.assertEqual(sess.events, ["commit"])

    async def test_rolls_back_on_exception(self):
        sess = _RecordingSession()
        with patch("backend.app.db.async_session", _patched_session_factory(sess)):
            from backend.app.db import unit_of_work
            with self.assertRaises(RuntimeError):
                async with unit_of_work():
                    raise RuntimeError("boom")
        self.assertEqual(sess.events, ["rollback"])

    async def test_explicit_commit_then_clean_exit(self):
        # Caller may commit explicitly (e.g. needs db.refresh after). The
        # auto-commit at exit then runs against an empty transaction (no-op
        # in a real session; for this mock it just appends "commit" again).
        sess = _RecordingSession()
        with patch("backend.app.db.async_session", _patched_session_factory(sess)):
            from backend.app.db import unit_of_work
            async with unit_of_work() as db:
                await db.commit()
        self.assertEqual(sess.events, ["commit", "commit"])

    async def test_exception_after_explicit_commit_still_rolls_back(self):
        sess = _RecordingSession()
        with patch("backend.app.db.async_session", _patched_session_factory(sess)):
            from backend.app.db import unit_of_work
            with self.assertRaises(RuntimeError):
                async with unit_of_work() as db:
                    await db.commit()
                    raise RuntimeError("boom")
        # Real session: rollback after a commit is also a no-op.
        self.assertEqual(sess.events, ["commit", "rollback"])


if __name__ == "__main__":
    unittest.main()
