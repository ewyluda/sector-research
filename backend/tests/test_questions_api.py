import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.app.api import questions
from backend.app.models.question import Question
from backend.app.services.questions import by_ticker_rollup, list_questions


class QuestionsApiFilterTests(unittest.TestCase):
    def test_all_status_normalizes_to_unfiltered(self) -> None:
        self.assertIsNone(questions._normalize_status_filter("all"))

    def test_missing_status_keeps_default_open(self) -> None:
        self.assertEqual(questions._normalize_status_filter(None), "open")


# ── Snooze + bulk: real-SQL tests over in-memory sqlite ──────────────────────
#
# Raw DDL (not Base.metadata.create_all) for the same reasons as
# test_outcome_tracker.py: counterparty_aliases duplicate-index bug +
# FK resolution pulling transitive table deps. SQLite doesn't enforce FKs,
# so theme/research_run parents are safe to omit.

_DDL_QUESTIONS = """
CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    theme_id TEXT,
    category TEXT NOT NULL,
    question_text TEXT NOT NULL,
    priority INTEGER NOT NULL,
    auto_answerable INTEGER NOT NULL,
    status TEXT NOT NULL,
    answer_text TEXT,
    answer_source TEXT,
    created_run_id TEXT NOT NULL,
    resolved_run_id TEXT,
    resolved_at TIMESTAMP,
    dismissed_at TIMESTAMP,
    dismiss_note TEXT,
    snoozed_until TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_TEST_ENGINES = []


def _build_async_test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.execute(text(_DDL_QUESTIONS))

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


def _question(**over) -> Question:
    base = dict(
        id=str(uuid.uuid4()),
        ticker="CORZ",
        theme_id=None,
        category="Risk Assessment",
        question_text="What is the hosting-contract renewal risk?",
        priority=3,
        auto_answerable=False,
        status="open",
        created_run_id=str(uuid.uuid4()),
    )
    base.update(over)
    return Question(**base)


class SnoozeExclusionTests(unittest.TestCase):
    def test_snoozed_questions_excluded_from_open_list(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(_question(question_text="visible"))
                db.add(
                    _question(
                        question_text="snoozed",
                        snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                    )
                )
                await db.commit()

                rows = await list_questions(db, status="open")
                self.assertEqual([q.question_text for q in rows], ["visible"])

                rollup = await by_ticker_rollup(db)
                self.assertEqual(len(rollup), 1)
                self.assertEqual(rollup[0]["ticker"], "CORZ")
                self.assertEqual(rollup[0]["open_count"], 1)
                self.assertEqual(rollup[0]["p3_count"], 1)

        asyncio.run(_run())

    def test_snooze_expiry_reincludes(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(
                    _question(
                        question_text="expired snooze",
                        snoozed_until=datetime.now(timezone.utc) - timedelta(hours=1),
                    )
                )
                await db.commit()

                rows = await list_questions(db, status="open")
                self.assertEqual([q.question_text for q in rows], ["expired snooze"])

                rollup = await by_ticker_rollup(db)
                self.assertEqual(len(rollup), 1)
                self.assertEqual(rollup[0]["open_count"], 1)

        asyncio.run(_run())


class BulkActionTests(unittest.TestCase):
    def test_bulk_dismiss_by_filter(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                match_a = _question(priority=3)
                match_b = _question(priority=3)
                other_priority = _question(priority=1)
                other_ticker = _question(ticker="NVDA", priority=3)
                already_resolved = _question(priority=3, status="resolved_manual")
                for q in (match_a, match_b, other_priority, other_ticker, already_resolved):
                    db.add(q)
                await db.commit()

                body = questions.BulkBody(
                    filter=questions.BulkFilter(ticker="CORZ", priority=3),
                    action="dismiss",
                    note="bulk cleanup",
                )
                result = await questions.bulk_endpoint(body, db)
                self.assertEqual(result, {"affected": 2})

                for q in (match_a, match_b):
                    await db.refresh(q)
                    self.assertEqual(q.status, "dismissed")
                    self.assertIsNotNone(q.dismissed_at)
                    self.assertEqual(q.dismiss_note, "bulk cleanup")
                for q in (other_priority, other_ticker):
                    await db.refresh(q)
                    self.assertEqual(q.status, "open")
                await db.refresh(already_resolved)
                self.assertEqual(already_resolved.status, "resolved_manual")

        asyncio.run(_run())

    def test_bulk_snooze_by_ids(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                target_a = _question()
                target_b = _question()
                untouched = _question()
                for q in (target_a, target_b, untouched):
                    db.add(q)
                await db.commit()

                body = questions.BulkBody(
                    ids=[target_a.id, target_b.id],
                    action="snooze",
                    snooze_days=7,
                )
                result = await questions.bulk_endpoint(body, db)
                self.assertEqual(result, {"affected": 2})

                expected = datetime.now(timezone.utc) + timedelta(days=7)
                for q in (target_a, target_b):
                    await db.refresh(q)
                    self.assertEqual(q.status, "open")  # snooze does not change status
                    snoozed = q.snoozed_until
                    if snoozed.tzinfo is None:
                        snoozed = snoozed.replace(tzinfo=timezone.utc)
                    self.assertLess(abs((snoozed - expected).total_seconds()), 60)
                await db.refresh(untouched)
                self.assertIsNone(untouched.snoozed_until)

        asyncio.run(_run())

    def test_bulk_resolve_by_ids_matches_per_row_transitions(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                target = _question()
                db.add(target)
                await db.commit()

                body = questions.BulkBody(
                    ids=[target.id],
                    action="resolve",
                    answer_text="Renewals confirmed through 2028.",
                )
                result = await questions.bulk_endpoint(body, db)
                self.assertEqual(result, {"affected": 1})

                await db.refresh(target)
                self.assertEqual(target.status, "resolved_manual")
                self.assertEqual(target.answer_text, "Renewals confirmed through 2028.")
                self.assertEqual(target.answer_source, "manual")
                self.assertIsNotNone(target.resolved_at)

        asyncio.run(_run())

    def test_bulk_filter_rejects_bogus_status(self):
        with self.assertRaises(ValidationError):
            questions.BulkFilter(status="bogus_status")

    def test_bulk_validation_errors(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                # neither ids nor filter
                with self.assertRaises(HTTPException) as ctx:
                    await questions.bulk_endpoint(
                        questions.BulkBody(action="dismiss"), db
                    )
                self.assertEqual(ctx.exception.status_code, 422)

                # both ids and filter
                with self.assertRaises(HTTPException) as ctx:
                    await questions.bulk_endpoint(
                        questions.BulkBody(
                            ids=["x"],
                            filter=questions.BulkFilter(ticker="CORZ"),
                            action="dismiss",
                        ),
                        db,
                    )
                self.assertEqual(ctx.exception.status_code, 422)

                # resolve without answer_text
                with self.assertRaises(HTTPException) as ctx:
                    await questions.bulk_endpoint(
                        questions.BulkBody(ids=["x"], action="resolve"), db
                    )
                self.assertEqual(ctx.exception.status_code, 422)

        asyncio.run(_run())


class SnoozedFilterTests(unittest.TestCase):
    def test_snoozed_filter_returns_only_active_snoozes(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                db.add(_question(question_text="open-now"))
                db.add(_question(
                    question_text="active-snooze",
                    snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                ))
                db.add(_question(
                    question_text="expired-snooze",
                    snoozed_until=datetime.now(timezone.utc) - timedelta(days=1),
                ))
                db.add(_question(question_text="dismissed", status="dismissed"))
                db.add(_question(
                    question_text="dismissed-but-snoozed",
                    status="dismissed",
                    snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                ))
                await db.commit()

                rows = await list_questions(db, status="snoozed")
                self.assertEqual([q.question_text for q in rows], ["active-snooze"])

        asyncio.run(_run())


class UnsnoozeEndpointTests(unittest.TestCase):
    def test_unsnooze_clears_and_rejoins_open_list(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                q = _question(
                    question_text="snoozed",
                    snoozed_until=datetime.now(timezone.utc) + timedelta(days=7),
                )
                db.add(q)
                await db.commit()

                out = await questions.unsnooze_endpoint(q.id, db)
                self.assertIsNone(out.snoozed_until)
                rows = await list_questions(db, status="open")
                self.assertEqual([r.question_text for r in rows], ["snoozed"])

        asyncio.run(_run())

    def test_unsnooze_is_idempotent_on_never_snoozed(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                q = _question(question_text="plain-open")
                db.add(q)
                await db.commit()
                out = await questions.unsnooze_endpoint(q.id, db)
                self.assertIsNone(out.snoozed_until)

        asyncio.run(_run())

    def test_unsnooze_unknown_id_404s(self):
        _, Session = _build_async_test_session()

        async def _run():
            async with Session() as db:
                with self.assertRaises(HTTPException) as ctx:
                    await questions.unsnooze_endpoint(str(uuid.uuid4()), db)
                self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
