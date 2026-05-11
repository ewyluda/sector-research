"""Tests for backend.app.services.transcript_delta."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SAAsyncSession
from sqlalchemy.orm import sessionmaker


class TestFingerprint(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        from backend.app.services.transcript_delta import compute_fingerprint
        window_a = [{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}]
        window_b = [{"year": 2025, "quarter": 3}, {"year": 2025, "quarter": 4}]
        # Order independent
        self.assertEqual(compute_fingerprint(window_a), compute_fingerprint(window_b))

    def test_fingerprint_differs_on_new_quarter(self):
        from backend.app.services.transcript_delta import compute_fingerprint
        a = [{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}]
        b = [{"year": 2026, "quarter": 1}, {"year": 2025, "quarter": 4}]
        self.assertNotEqual(compute_fingerprint(a), compute_fingerprint(b))


_DDL_TRANSCRIPT_DELTAS = """
CREATE TABLE IF NOT EXISTS transcript_deltas (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    transcripts_window TEXT NOT NULL,
    transcripts_fingerprint TEXT NOT NULL,
    axes TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    UNIQUE (ticker, transcripts_fingerprint)
)
"""

_DDL_TRANSCRIPT_DELTAS_IDX = """
CREATE INDEX IF NOT EXISTS ix_transcript_deltas_ticker_computed_at
ON transcript_deltas (ticker, computed_at)
"""


def _build_async_test_session():
    """In-memory async sqlite engine + session.

    Uses raw DDL (mirrors test_outcome_tracker.py) to avoid:
    - counterparty_aliases duplicate-index bug in Base.metadata.create_all.
    - Transitive FK deps pulling in unrelated tables.
    JSONB columns become TEXT in sqlite; ORM round-trip works fine.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _setup():
        async with engine.begin() as conn:
            await conn.execute(text(_DDL_TRANSCRIPT_DELTAS))
            await conn.execute(text(_DDL_TRANSCRIPT_DELTAS_IDX))

    asyncio.run(_setup())
    Session = sessionmaker(engine, class_=SAAsyncSession, expire_on_commit=False)
    return engine, Session


class TestComputeDeltaShortCircuits(unittest.TestCase):
    def test_insufficient_transcripts_raises(self):
        from backend.app.services.transcript_delta import (
            compute_delta, InsufficientTranscriptsError,
        )
        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(return_value=([], None))

        engine, Session = _build_async_test_session()

        async def go():
            async with Session() as db:
                with self.assertRaises(InsufficientTranscriptsError):
                    await compute_delta(ticker="NVDA", db=db, fmp=fmp, force=False)
            await engine.dispose()

        asyncio.run(go())

    def test_cache_hit_returns_existing_row_without_calling_llm(self):
        from datetime import datetime as dt
        from backend.app.services.transcript_delta import (
            compute_delta, compute_fingerprint,
        )
        from backend.app.models.transcript_delta import TranscriptDelta

        # Determine the two quarters fetch_recent_transcripts will return first
        # (walks back from current date: skip empty quarters, collect first two
        # that return data).  We stamp them with the years/quarters the walker
        # will request so the fingerprint matches what compute_delta derives.
        now = dt.utcnow()
        y, q = now.year, ((now.month - 1) // 3) + 1
        # Build a list of (year, quarter) for the next TRANSCRIPT_WINDOW slots
        slots = []
        ty, tq = y, q
        for _ in range(8):
            slots.append((ty, tq))
            tq -= 1
            if tq == 0:
                tq = 4
                ty -= 1

        # Return data for the first two slots, empty for the rest
        t0 = {"year": slots[0][0], "quarter": slots[0][1], "content": "..."}
        t1 = {"year": slots[1][0], "quarter": slots[1][1], "content": "..."}
        side_effects = [
            ([t0], None),
            ([t1], None),
        ] + [([], None)] * 6

        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(side_effect=side_effects)

        engine, Session = _build_async_test_session()
        window = [{"year": t0["year"], "quarter": t0["quarter"]},
                  {"year": t1["year"], "quarter": t1["quarter"]}]
        fingerprint = compute_fingerprint(window)

        async def go():
            async with Session() as db:
                # Seed an existing row with the matching fingerprint
                db.add(TranscriptDelta(
                    id=str(uuid4()),
                    ticker="NVDA",
                    transcripts_window=window,
                    transcripts_fingerprint=fingerprint,
                    axes={"business_quality": None, "risk_assessment": None,
                          "growth_earnings": None, "sentiment_narrative": None,
                          "management_governance": None, "future_durability": None,
                          "macro_regime": None, "financial_health": None,
                          "valuation_stage": None},
                    computed_at=datetime.now(timezone.utc),
                ))
                await db.commit()

                # Cache hit returns before reaching the NotImplementedError
                # that guards the LLM path (Task 6).
                result = await compute_delta(
                    ticker="NVDA", db=db, fmp=fmp, force=False,
                )
                self.assertEqual(result.ticker, "NVDA")
                self.assertEqual(result.transcripts_fingerprint, fingerprint)
            await engine.dispose()

        asyncio.run(go())


class TestComputeDeltaPersistsAndTrims(unittest.TestCase):
    def test_persists_new_row_after_llm_call(self):
        from backend.app.services.transcript_delta import compute_delta
        from backend.app.models.transcript_delta import TranscriptDelta
        from sqlalchemy import select as sa_select

        # Determine the two quarters fetch_recent_transcripts will walk to first.
        from datetime import datetime as dt
        now = dt.utcnow()
        y, q = now.year, ((now.month - 1) // 3) + 1
        slots = []
        ty, tq = y, q
        for _ in range(8):
            slots.append((ty, tq))
            tq -= 1
            if tq == 0:
                tq = 4
                ty -= 1

        t0 = {"year": slots[0][0], "quarter": slots[0][1], "content": "Q0 transcript"}
        t1 = {"year": slots[1][0], "quarter": slots[1][1], "content": "Q1 transcript"}
        side_effects = [([t0], None), ([t1], None)] + [([], None)] * 6

        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(side_effect=side_effects)

        llm_payload = (
            '{"axes":{"business_quality":null,"risk_assessment":null,'
            '"growth_earnings":{"direction":"softening","magnitude":"material",'
            '"summary":"Mgmt walked guidance down.","quotes":[]},'
            '"sentiment_narrative":null,"management_governance":null,'
            '"future_durability":null,"macro_regime":null,'
            '"financial_health":null,"valuation_stage":null}}'
        )

        engine, Session = _build_async_test_session()

        async def go():
            async with Session() as db:
                with patch(
                    "backend.app.services.transcript_delta.complete",
                    new=AsyncMock(return_value=llm_payload),
                ):
                    row = await compute_delta(
                        ticker="NVDA", db=db, fmp=fmp, force=False,
                    )
                self.assertEqual(row.ticker, "NVDA")
                self.assertEqual(row.axes["growth_earnings"]["direction"], "softening")
                # Persisted
                count = (await db.execute(
                    sa_select(TranscriptDelta).where(TranscriptDelta.ticker == "NVDA")
                )).all()
                self.assertEqual(len(count), 1)
            await engine.dispose()

        asyncio.run(go())

    def test_history_cap_trims_oldest(self):
        from backend.app.services.transcript_delta import (
            compute_delta, HISTORY_CAP,
        )
        from backend.app.models.transcript_delta import TranscriptDelta
        from sqlalchemy import select as sa_select

        engine, Session = _build_async_test_session()
        llm_payload = (
            '{"axes":{"business_quality":null,"risk_assessment":null,'
            '"growth_earnings":null,"sentiment_narrative":null,'
            '"management_governance":null,"future_durability":null,'
            '"macro_regime":null,"financial_health":null,"valuation_stage":null}}'
        )

        async def go():
            async with Session() as db:
                # Pre-seed HISTORY_CAP rows
                from datetime import timedelta
                for i in range(HISTORY_CAP):
                    db.add(TranscriptDelta(
                        id=str(uuid4()), ticker="NVDA",
                        transcripts_window=[{"year": 2020 + i, "quarter": 1}],
                        transcripts_fingerprint=f"seed-{i}",
                        axes={"business_quality": None, "risk_assessment": None,
                              "growth_earnings": None, "sentiment_narrative": None,
                              "management_governance": None, "future_durability": None,
                              "macro_regime": None, "financial_health": None,
                              "valuation_stage": None},
                        computed_at=datetime.now(timezone.utc) - timedelta(days=HISTORY_CAP - i),
                    ))
                await db.commit()

                # Determine the two slots fetch_recent_transcripts will use
                from datetime import datetime as dt
                now = dt.utcnow()
                y, q = now.year, ((now.month - 1) // 3) + 1
                slots = []
                ty, tq = y, q
                for _ in range(8):
                    slots.append((ty, tq))
                    tq -= 1
                    if tq == 0:
                        tq = 4
                        ty -= 1

                t0 = {"year": slots[0][0], "quarter": slots[0][1], "content": "x"}
                t1 = {"year": slots[1][0], "quarter": slots[1][1], "content": "y"}
                side_effects = [([t0], None), ([t1], None)] + [([], None)] * 6

                fmp = MagicMock()
                fmp.get_earnings_transcript = AsyncMock(side_effect=side_effects)
                with patch(
                    "backend.app.services.transcript_delta.complete",
                    new=AsyncMock(return_value=llm_payload),
                ):
                    await compute_delta(ticker="NVDA", db=db, fmp=fmp, force=False)

                rows = (await db.execute(
                    sa_select(TranscriptDelta).where(TranscriptDelta.ticker == "NVDA")
                )).scalars().all()
                self.assertEqual(len(rows), HISTORY_CAP)  # cap respected
                # Oldest seed evicted
                fingerprints = {r.transcripts_fingerprint for r in rows}
                self.assertNotIn("seed-0", fingerprints)
            await engine.dispose()

        asyncio.run(go())


    def test_force_recompute_updates_existing_row_in_place(self):
        """force=True on same transcript window must not violate the
        (ticker, fingerprint) unique constraint — it should update in place."""
        from backend.app.services.transcript_delta import (
            compute_delta, compute_fingerprint,
        )
        from backend.app.models.transcript_delta import TranscriptDelta
        from sqlalchemy import select as sa_select
        from datetime import datetime as dt

        now = dt.utcnow()
        y, q = now.year, ((now.month - 1) // 3) + 1
        slots = []
        ty, tq = y, q
        for _ in range(8):
            slots.append((ty, tq))
            tq -= 1
            if tq == 0:
                tq = 4
                ty -= 1

        t0 = {"year": slots[0][0], "quarter": slots[0][1], "content": "Q0 content"}
        t1 = {"year": slots[1][0], "quarter": slots[1][1], "content": "Q1 content"}
        side_effects = [([t0], None), ([t1], None)] + [([], None)] * 6

        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(side_effect=side_effects)

        window = [{"year": t0["year"], "quarter": t0["quarter"]},
                  {"year": t1["year"], "quarter": t1["quarter"]}]
        fingerprint = compute_fingerprint(window)

        seeded_axes = {
            "business_quality": None, "risk_assessment": None,
            "growth_earnings": None, "sentiment_narrative": None,
            "management_governance": None, "future_durability": None,
            "macro_regime": None, "financial_health": None,
            "valuation_stage": None,
        }
        updated_llm_payload = (
            '{"axes":{"business_quality":null,"risk_assessment":null,'
            '"growth_earnings":{"direction":"strengthening","magnitude":"minor",'
            '"summary":"Guidance raised.","quotes":[]},'
            '"sentiment_narrative":null,"management_governance":null,'
            '"future_durability":null,"macro_regime":null,'
            '"financial_health":null,"valuation_stage":null}}'
        )

        engine, Session = _build_async_test_session()

        async def go():
            async with Session() as db:
                # Seed an existing row with the same fingerprint
                db.add(TranscriptDelta(
                    id=str(uuid4()),
                    ticker="NVDA",
                    transcripts_window=window,
                    transcripts_fingerprint=fingerprint,
                    axes=seeded_axes,
                    computed_at=datetime.now(timezone.utc),
                ))
                await db.commit()

                with patch(
                    "backend.app.services.transcript_delta.complete",
                    new=AsyncMock(return_value=updated_llm_payload),
                ):
                    result = await compute_delta(
                        ticker="NVDA", db=db, fmp=fmp, force=True,
                    )

                # No IntegrityError raised, and still exactly 1 row
                rows = (await db.execute(
                    sa_select(TranscriptDelta).where(TranscriptDelta.ticker == "NVDA")
                )).scalars().all()
                self.assertEqual(len(rows), 1)
                # axes reflects the new LLM payload, not the seeded one
                self.assertEqual(
                    result.axes["growth_earnings"]["direction"], "strengthening"
                )
            await engine.dispose()

        asyncio.run(go())


if __name__ == "__main__":
    unittest.main()
