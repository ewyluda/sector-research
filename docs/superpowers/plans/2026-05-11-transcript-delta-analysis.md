# Transcript Delta Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect QoQ shifts in management's transcript language across 9 deep-dive categories, persist with idempotent fingerprinting, surface as a "What changed" panel on the deep-dive page and as a prompt input to Workspace Step 2.

**Architecture:** New table `transcript_deltas` (one row per ticker × fingerprint of input transcripts). Service `compute_delta()` fetches 4 most recent transcripts via the existing `fetch_recent_transcripts()` helper, returns cached row on fingerprint hit, otherwise issues one Haiku structured-output call across the 9 nullable category axes. Three GET/POST endpoints, plus inline integration into `workspace_steps.step_research` and a new `WhatChangedPanel` deep-dive section above Management & Governance.

**Tech Stack:** SQLAlchemy 2.x async + Alembic, FastAPI, Pydantic v2, Anthropic Haiku 4.5 via `backend.app.graph.llm`, React 19 + Next.js 16 App Router, Tailwind v4. Backend tests via stdlib `unittest`.

Spec: `docs/superpowers/specs/2026-05-11-transcript-delta-analysis-design.md`

---

## File map

**Backend — new files:**
- `backend/migrations/versions/<rev>_transcript_deltas.py` — Alembic migration (auto-generated revision id)
- `backend/app/models/transcript_delta.py` — `TranscriptDelta` ORM
- `backend/app/models/transcript_delta_schemas.py` — `QuoteRef`, `AxisDelta`, `AxesDelta`, `TranscriptDeltaRead` Pydantic
- `backend/app/services/transcript_delta.py` — `compute_delta()`, fingerprint, prompt builder, history trim, exceptions
- `backend/app/api/transcripts_delta.py` — three endpoints
- `backend/tests/test_transcript_delta.py` — service tests
- `backend/tests/test_transcripts_delta_api.py` — endpoint tests

**Backend — modified:**
- `backend/app/main.py` — register the new router
- `backend/app/services/workspace_steps.py` — wire `compute_delta()` into research step

**Frontend — new files:**
- `frontend/components/deep-dive/sections/WhatChangedPanel.tsx`

**Frontend — modified:**
- `frontend/lib/api.ts` — types + `transcriptDeltaApi` client
- `frontend/components/deep-dive/DeepDiveDashboard.tsx` — slot panel above Management & Governance
- `frontend/components/deep-dive/sections.ts` — registry entry

---

### Task 1: ORM model

**Files:**
- Create: `backend/app/models/transcript_delta.py`

- [ ] **Step 1: Write the ORM class**

```python
"""TranscriptDelta ORM — caches Haiku-extracted QoQ language deltas per ticker."""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class TranscriptDelta(Base):
    __tablename__ = "transcript_deltas"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    transcripts_window: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    transcripts_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    axes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "ticker", "transcripts_fingerprint",
            name="uq_transcript_deltas_ticker_fingerprint",
        ),
        Index(
            "ix_transcript_deltas_ticker_computed_at",
            "ticker", "computed_at",
        ),
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/transcript_delta.py
git commit -m "feat(transcript-delta): TranscriptDelta ORM"
```

---

### Task 2: Pydantic schemas

**Files:**
- Create: `backend/app/models/transcript_delta_schemas.py`

- [ ] **Step 1: Write the schemas**

```python
"""Pydantic schemas for transcript delta analysis."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AxisDirection = Literal["softening", "strengthening", "stable"]
AxisMagnitude = Literal["minor", "material", "regime_change"]

CATEGORY_KEYS: tuple[str, ...] = (
    "business_quality",
    "risk_assessment",
    "growth_earnings",
    "sentiment_narrative",
    "management_governance",
    "future_durability",
    "macro_regime",
    "financial_health",
    "valuation_stage",
)


class QuoteRef(BaseModel):
    year: int = Field(ge=2000, le=2100)
    quarter: int = Field(ge=1, le=4)
    role: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=300)


class AxisDelta(BaseModel):
    direction: AxisDirection
    magnitude: AxisMagnitude
    summary: str = Field(min_length=1, max_length=600)
    quotes: list[QuoteRef] = Field(default_factory=list, max_length=3)


class AxesDelta(BaseModel):
    business_quality: AxisDelta | None = None
    risk_assessment: AxisDelta | None = None
    growth_earnings: AxisDelta | None = None
    sentiment_narrative: AxisDelta | None = None
    management_governance: AxisDelta | None = None
    future_durability: AxisDelta | None = None
    macro_regime: AxisDelta | None = None
    financial_health: AxisDelta | None = None
    valuation_stage: AxisDelta | None = None


class TranscriptWindowEntry(BaseModel):
    year: int
    quarter: int


class TranscriptDeltaRead(BaseModel):
    id: str
    ticker: str
    transcripts_window: list[TranscriptWindowEntry]
    axes: AxesDelta
    computed_at: datetime
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/transcript_delta_schemas.py
git commit -m "feat(transcript-delta): Pydantic schemas (QuoteRef, AxisDelta, AxesDelta)"
```

---

### Task 3: Alembic migration

**Files:**
- Create: `backend/migrations/versions/<rev>_transcript_deltas.py` (revision id generated)

- [ ] **Step 1: Generate revision**

Run from project root with venv active:

```bash
cd backend && PYTHONPATH=.. alembic revision --autogenerate -m "transcript_deltas"
```

This produces a file like `backend/migrations/versions/abc123def456_transcript_deltas.py`. Confirm it picks up the new `transcript_deltas` table; if autogen produced extra spurious diffs (column-default churn from older tables), keep only the new-table block.

- [ ] **Step 2: Hand-verify the migration body**

Open the new revision. Confirm `upgrade()` matches this body (edit if autogen differs):

```python
def upgrade() -> None:
    op.create_table(
        "transcript_deltas",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("transcripts_window", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("transcripts_fingerprint", sa.String(), nullable=False),
        sa.Column("axes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("ticker", "transcripts_fingerprint",
                            name="uq_transcript_deltas_ticker_fingerprint"),
    )
    op.create_index(
        "ix_transcript_deltas_ticker_computed_at",
        "transcript_deltas", ["ticker", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_deltas_ticker_computed_at",
                  table_name="transcript_deltas")
    op.drop_table("transcript_deltas")
```

- [ ] **Step 3: Apply the migration**

```bash
cd backend && PYTHONPATH=.. alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, transcript_deltas`.

- [ ] **Step 4: Verify table exists**

```bash
cd /Users/ericwyluda/Development/projects/sector-research && source backend/venv/bin/activate && python -c "
import asyncio
from sqlalchemy import text
from backend.app.db import async_session
async def main():
    async with async_session() as db:
        r = await db.execute(text('SELECT COUNT(*) FROM transcript_deltas'))
        print('transcript_deltas rows:', r.scalar())
asyncio.run(main())
"
```

Expected: `transcript_deltas rows: 0`.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/versions/*_transcript_deltas.py
git commit -m "feat(db): migration for transcript_deltas table"
```

---

### Task 4: Fingerprint helper + tests

**Files:**
- Create: `backend/app/services/transcript_delta.py`
- Test: `backend/tests/test_transcript_delta.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for backend.app.services.transcript_delta."""
from __future__ import annotations

import unittest


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, confirm failure**

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: `ModuleNotFoundError: No module named 'backend.app.services.transcript_delta'`.

- [ ] **Step 3: Write minimal service skeleton**

```python
"""Transcript delta analysis — Haiku-extracted QoQ language deltas."""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)


class InsufficientTranscriptsError(Exception):
    """Raised when fewer than 2 transcripts are available — no delta possible."""


def compute_fingerprint(window: list[dict]) -> str:
    """SHA-1 of sorted (year, quarter) tuples. Order independent.

    Window entries: {"year": int, "quarter": int, ...}. Extra keys ignored.
    """
    pairs = sorted((int(w["year"]), int(w["quarter"])) for w in window)
    payload = ",".join(f"{y}Q{q}" for (y, q) in pairs)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: `Ran 2 tests in ...s OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcript_delta.py backend/tests/test_transcript_delta.py
git commit -m "feat(transcript-delta): service skeleton + fingerprint helper (2 tests)"
```

---

### Task 5: compute_delta — cache-hit + insufficient-transcripts paths

**Files:**
- Modify: `backend/app/services/transcript_delta.py`
- Modify: `backend/tests/test_transcript_delta.py`

- [ ] **Step 1: Write the failing tests**

Add to `test_transcript_delta.py` (keep existing class, add a new one):

```python
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as SAAsyncSession
from sqlalchemy.orm import sessionmaker


def _build_async_test_session():
    """In-memory async sqlite engine + session — mirrors test_outcome_tracker."""
    from backend.app.models.base import Base
    from backend.app.models.transcript_delta import TranscriptDelta  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)

    async def _create_all():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    import asyncio
    asyncio.get_event_loop().run_until_complete(_create_all())
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

        import asyncio
        asyncio.get_event_loop().run_until_complete(go())

    def test_cache_hit_returns_existing_row_without_calling_llm(self):
        from backend.app.services.transcript_delta import (
            compute_delta, compute_fingerprint,
        )
        from backend.app.models.transcript_delta import TranscriptDelta

        transcripts = [
            {"year": 2025, "quarter": 4, "content": "..."},
            {"year": 2025, "quarter": 3, "content": "..."},
        ]
        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(side_effect=[
            ([transcripts[0]], None), ([transcripts[1]], None),
            ([], None), ([], None), ([], None), ([], None),  # exhaust lookback
        ])

        engine, Session = _build_async_test_session()
        fingerprint = compute_fingerprint(transcripts)

        async def go():
            async with Session() as db:
                # Seed an existing row
                db.add(TranscriptDelta(
                    id=str(uuid4()),
                    ticker="NVDA",
                    transcripts_window=[{"year": 2025, "quarter": 4},
                                         {"year": 2025, "quarter": 3}],
                    transcripts_fingerprint=fingerprint,
                    axes={"business_quality": None, "risk_assessment": None,
                          "growth_earnings": None, "sentiment_narrative": None,
                          "management_governance": None, "future_durability": None,
                          "macro_regime": None, "financial_health": None,
                          "valuation_stage": None},
                    computed_at=datetime.now(timezone.utc),
                ))
                await db.commit()

                with patch(
                    "backend.app.services.transcript_delta.complete",
                    new=AsyncMock(side_effect=AssertionError("LLM should not be called on cache hit")),
                ):
                    result = await compute_delta(
                        ticker="NVDA", db=db, fmp=fmp, force=False,
                    )
                self.assertEqual(result.ticker, "NVDA")
                self.assertEqual(result.transcripts_fingerprint, fingerprint)
            await engine.dispose()

        import asyncio
        asyncio.get_event_loop().run_until_complete(go())
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: `ImportError: cannot import name 'compute_delta'`.

- [ ] **Step 3: Implement compute_delta short-circuit paths**

Append to `backend/app/services/transcript_delta.py`:

```python
from typing import TYPE_CHECKING
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.transcript_delta import TranscriptDelta
from backend.app.services.edgar_transcripts_relationships import fetch_recent_transcripts


TRANSCRIPT_WINDOW = 4
MIN_TRANSCRIPTS_FOR_DELTA = 2


def _window_from_transcripts(transcripts: list[dict]) -> list[dict]:
    """Project transcripts list down to {year, quarter} entries for storage."""
    return [{"year": int(t["year"]), "quarter": int(t["quarter"])} for t in transcripts]


async def compute_delta(
    *,
    ticker: str,
    db: AsyncSession,
    fmp: FMPClient,
    force: bool = False,
) -> TranscriptDelta:
    """Fetch the latest TRANSCRIPT_WINDOW transcripts, compute or return cached delta."""
    transcripts, _citation = await fetch_recent_transcripts(
        fmp, ticker, limit=TRANSCRIPT_WINDOW,
    )
    if len(transcripts) < MIN_TRANSCRIPTS_FOR_DELTA:
        raise InsufficientTranscriptsError(
            f"{ticker}: only {len(transcripts)} transcript(s) available — need at least {MIN_TRANSCRIPTS_FOR_DELTA}"
        )

    window = _window_from_transcripts(transcripts)
    fingerprint = compute_fingerprint(window)

    if not force:
        existing = (await db.execute(
            select(TranscriptDelta).where(
                TranscriptDelta.ticker == ticker,
                TranscriptDelta.transcripts_fingerprint == fingerprint,
            )
        )).scalar_one_or_none()
        if existing is not None:
            return existing

    # LLM path lands in the next task; raise to keep the contract honest.
    raise NotImplementedError("LLM extraction lands in Task 6")
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: `Ran 4 tests in ...s OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcript_delta.py backend/tests/test_transcript_delta.py
git commit -m "feat(transcript-delta): compute_delta cache-hit + insufficient-transcripts short-circuits"
```

---

### Task 6: Haiku call + persistence + history cap

**Files:**
- Modify: `backend/app/services/transcript_delta.py`
- Modify: `backend/tests/test_transcript_delta.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_transcript_delta.py`:

```python
class TestComputeDeltaPersistsAndTrims(unittest.TestCase):
    def test_persists_new_row_after_llm_call(self):
        from backend.app.services.transcript_delta import compute_delta
        from backend.app.models.transcript_delta import TranscriptDelta

        transcripts = [
            {"year": 2025, "quarter": 4, "content": "Q4 transcript"},
            {"year": 2025, "quarter": 3, "content": "Q3 transcript"},
        ]
        fmp = MagicMock()
        fmp.get_earnings_transcript = AsyncMock(side_effect=[
            ([transcripts[0]], None), ([transcripts[1]], None),
            ([], None), ([], None), ([], None), ([], None), ([], None), ([], None),
        ])

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
                    select(TranscriptDelta).where(TranscriptDelta.ticker == "NVDA")
                )).all()
                self.assertEqual(len(count), 1)
            await engine.dispose()

        import asyncio
        asyncio.get_event_loop().run_until_complete(go())

    def test_history_cap_trims_oldest(self):
        from backend.app.services.transcript_delta import (
            compute_delta, HISTORY_CAP,
        )
        from backend.app.models.transcript_delta import TranscriptDelta

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

                # Add one more
                fmp = MagicMock()
                fmp.get_earnings_transcript = AsyncMock(side_effect=[
                    ([{"year": 2030, "quarter": 1, "content": "x"}], None),
                    ([{"year": 2029, "quarter": 4, "content": "y"}], None),
                    ([], None), ([], None), ([], None), ([], None), ([], None), ([], None),
                ])
                with patch(
                    "backend.app.services.transcript_delta.complete",
                    new=AsyncMock(return_value=llm_payload),
                ):
                    await compute_delta(ticker="NVDA", db=db, fmp=fmp, force=False)

                rows = (await db.execute(
                    select(TranscriptDelta).where(TranscriptDelta.ticker == "NVDA")
                )).scalars().all()
                self.assertEqual(len(rows), HISTORY_CAP)  # cap respected
                # Oldest seed evicted
                fingerprints = {r.transcripts_fingerprint for r in rows}
                self.assertNotIn("seed-0", fingerprints)
            await engine.dispose()

        import asyncio
        asyncio.get_event_loop().run_until_complete(go())
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: 2 new tests fail with `NotImplementedError: LLM extraction lands in Task 6` (and `HISTORY_CAP` ImportError on the second one).

- [ ] **Step 3: Wire the LLM call + persistence + trim**

Edit `backend/app/services/transcript_delta.py`. Add these constants and prompt builders near the top, after imports:

```python
import json
from uuid import uuid4

from backend.app.graph.llm import HAIKU, complete
from backend.app.models.transcript_delta_schemas import AxesDelta, CATEGORY_KEYS


HISTORY_CAP = 8
TRANSCRIPT_BODY_CHAR_BUDGET = 12_000  # per-transcript truncation in prompt


_SYSTEM_PROMPT = """You analyze earnings call transcripts and emit per-category
language deltas. Compare the most recent transcript to prior quarters.

Output a single JSON object: {"axes": {<key>: AxisDelta | null, ...}}

Keys (use exactly these): business_quality, risk_assessment, growth_earnings,
sentiment_narrative, management_governance, future_durability, macro_regime,
financial_health, valuation_stage.

For each key, return null when the transcripts do not materially address that
axis. Prefer null over filler. Earnings calls rarely cover macro_regime,
financial_health, or valuation_stage directly — return null for these unless
management explicitly addresses them.

When you emit a delta, the value is:
  {
    "direction": "softening" | "strengthening" | "stable",
    "magnitude": "minor" | "material" | "regime_change",
    "summary": "1-2 sentences describing the shift",
    "quotes": [{"year": int, "quarter": int, "role": str, "text": str}]
  }

Quotes must be verbatim from the transcripts (max 300 chars each, 1-3 quotes
per axis). Role is the speaker role (CEO, CFO, IR, analyst, etc.). Do not
paraphrase quotes.

magnitude="minor" = subtle word choice shift. "material" = clear directional
move (e.g. "we're confident" -> "we're monitoring"). "regime_change" = the
narrative pillar itself has changed (e.g. growth -> capital discipline).
"""


def _build_user_prompt(transcripts: list[dict]) -> str:
    """Concatenate transcripts newest-first with explicit quarter separators."""
    parts: list[str] = []
    for t in transcripts:
        body = (t.get("content") or "")[:TRANSCRIPT_BODY_CHAR_BUDGET]
        parts.append(f"=== Q{t['quarter']} {t['year']} ===\n{body}")
    return "\n\n".join(parts)
```

Now replace the `NotImplementedError` block in `compute_delta` with the full LLM + persistence flow:

```python
async def compute_delta(
    *,
    ticker: str,
    db: AsyncSession,
    fmp: FMPClient,
    force: bool = False,
) -> TranscriptDelta:
    transcripts, _citation = await fetch_recent_transcripts(
        fmp, ticker, limit=TRANSCRIPT_WINDOW,
    )
    if len(transcripts) < MIN_TRANSCRIPTS_FOR_DELTA:
        raise InsufficientTranscriptsError(
            f"{ticker}: only {len(transcripts)} transcript(s) available — need at least {MIN_TRANSCRIPTS_FOR_DELTA}"
        )

    window = _window_from_transcripts(transcripts)
    fingerprint = compute_fingerprint(window)

    if not force:
        existing = (await db.execute(
            select(TranscriptDelta).where(
                TranscriptDelta.ticker == ticker,
                TranscriptDelta.transcripts_fingerprint == fingerprint,
            )
        )).scalar_one_or_none()
        if existing is not None:
            return existing

    raw = await complete(
        model=HAIKU,
        system=_SYSTEM_PROMPT,
        user=_build_user_prompt(transcripts),
        assistant_prefill='{"axes":',
        max_tokens=2500,
    )
    # complete() returns the assistant text without the prefill; prefix it back.
    payload_str = '{"axes":' + raw if not raw.lstrip().startswith("{") else raw
    parsed = json.loads(payload_str)
    axes = AxesDelta.model_validate(parsed["axes"]).model_dump()

    row = TranscriptDelta(
        id=str(uuid4()),
        ticker=ticker,
        transcripts_window=window,
        transcripts_fingerprint=fingerprint,
        axes=axes,
    )
    db.add(row)
    await db.flush()

    await _trim_history(ticker=ticker, db=db)
    return row


async def _trim_history(*, ticker: str, db: AsyncSession) -> None:
    """Keep the most recent HISTORY_CAP rows per ticker; delete the rest."""
    rows = (await db.execute(
        select(TranscriptDelta)
        .where(TranscriptDelta.ticker == ticker)
        .order_by(TranscriptDelta.computed_at.desc())
    )).scalars().all()
    for stale in rows[HISTORY_CAP:]:
        await db.delete(stale)
    await db.flush()
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
python -m unittest backend.tests.test_transcript_delta -v
```

Expected: `Ran 6 tests in ...s OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transcript_delta.py backend/tests/test_transcript_delta.py
git commit -m "feat(transcript-delta): Haiku extraction + persistence + 8-row history cap (4 tests)"
```

---

### Task 7: Read endpoint (latest + history)

**Files:**
- Create: `backend/app/api/transcripts_delta.py`
- Test: `backend/tests/test_transcripts_delta_api.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for backend.app.api.transcripts_delta."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestGetLatest(unittest.TestCase):
    def test_204_when_no_delta(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.transcripts_delta._fetch_latest",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app)
            r = client.get("/api/transcripts/delta/NVDA/latest")
            self.assertEqual(r.status_code, 204)

    def test_200_returns_existing(self):
        from backend.app.main import app

        payload = {
            "id": str(uuid4()),
            "ticker": "NVDA",
            "transcripts_window": [{"year": 2025, "quarter": 4},
                                    {"year": 2025, "quarter": 3}],
            "axes": {k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        with patch(
            "backend.app.api.transcripts_delta._fetch_latest",
            new=AsyncMock(return_value=payload),
        ):
            client = TestClient(app)
            r = client.get("/api/transcripts/delta/NVDA/latest")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test, confirm failure**

```bash
python -m unittest backend.tests.test_transcripts_delta_api -v
```

Expected: `ModuleNotFoundError: No module named 'backend.app.api.transcripts_delta'`.

- [ ] **Step 3: Write the router with read endpoints**

```python
"""GET /api/transcripts/delta/{ticker}/latest, GET /history, POST recompute."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from backend.app.db import async_session, unit_of_work
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.models.transcript_delta import TranscriptDelta
from backend.app.models.transcript_delta_schemas import TranscriptDeltaRead
from backend.app.services import transcript_delta

router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


def _orm_to_dict(row: TranscriptDelta) -> dict:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "transcripts_window": row.transcripts_window,
        "axes": row.axes,
        "computed_at": row.computed_at,
    }


async def _fetch_latest(*, ticker: str, db) -> dict | None:
    row = (await db.execute(
        select(TranscriptDelta)
        .where(TranscriptDelta.ticker == ticker)
        .order_by(TranscriptDelta.computed_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    return _orm_to_dict(row)


async def _fetch_history(*, ticker: str, db) -> list[dict]:
    rows = (await db.execute(
        select(TranscriptDelta)
        .where(TranscriptDelta.ticker == ticker)
        .order_by(TranscriptDelta.computed_at.asc())
    )).scalars().all()
    return [_orm_to_dict(r) for r in rows]


@router.get("/delta/{ticker}/latest")
async def get_latest(ticker: Ticker = TickerPath) -> Response:
    async with async_session() as db:
        payload = await _fetch_latest(ticker=ticker, db=db)
    if payload is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Response(
        content=TranscriptDeltaRead.model_validate(payload).model_dump_json(),
        media_type="application/json",
    )


@router.get("/delta/{ticker}/history", response_model=list[TranscriptDeltaRead])
async def get_history(ticker: Ticker = TickerPath) -> list[dict]:
    async with async_session() as db:
        return await _fetch_history(ticker=ticker, db=db)
```

- [ ] **Step 4: Register router in main.py**

Modify `backend/app/main.py` — add to the existing `from backend.app.api import ...` block:

```python
from backend.app.api import transcripts_delta as transcripts_delta_router
```

And in the section where other routers are included (search for `app.include_router`):

```python
app.include_router(transcripts_delta_router.router)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
python -m unittest backend.tests.test_transcripts_delta_api -v
```

Expected: `Ran 2 tests in ...s OK`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/transcripts_delta.py backend/app/main.py backend/tests/test_transcripts_delta_api.py
git commit -m "feat(api): GET /api/transcripts/delta/{ticker}/latest|history (2 tests)"
```

---

### Task 8: POST recompute endpoint

**Files:**
- Modify: `backend/app/api/transcripts_delta.py`
- Modify: `backend/tests/test_transcripts_delta_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_transcripts_delta_api.py`:

```python
class TestPostCompute(unittest.TestCase):
    def test_post_returns_200_and_payload(self):
        from backend.app.main import app
        from backend.app.models.transcript_delta import TranscriptDelta

        row = TranscriptDelta(
            id=str(uuid4()), ticker="NVDA",
            transcripts_window=[{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}],
            transcripts_fingerprint="abc",
            axes={k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            computed_at=datetime.now(timezone.utc),
        )
        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=AsyncMock(return_value=row),
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")

    def test_post_404_on_insufficient_transcripts(self):
        from backend.app.main import app
        from backend.app.services.transcript_delta import InsufficientTranscriptsError

        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=AsyncMock(side_effect=InsufficientTranscriptsError("NVDA: only 1")),
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA")
            self.assertEqual(r.status_code, 404)

    def test_post_force_param_forwarded(self):
        from backend.app.main import app
        from backend.app.models.transcript_delta import TranscriptDelta

        row = TranscriptDelta(
            id=str(uuid4()), ticker="NVDA",
            transcripts_window=[{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}],
            transcripts_fingerprint="abc",
            axes={k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            computed_at=datetime.now(timezone.utc),
        )
        compute_mock = AsyncMock(return_value=row)
        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=compute_mock,
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA?force=true")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(compute_mock.call_args.kwargs["force"])
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
python -m unittest backend.tests.test_transcripts_delta_api -v
```

Expected: 3 new tests fail with 404/405 (route not defined).

- [ ] **Step 3: Implement the POST route**

Append to `backend/app/api/transcripts_delta.py`:

```python
@router.post("/delta/{ticker}", response_model=TranscriptDeltaRead)
async def post_compute(
    request: Request,
    ticker: Ticker = TickerPath,
    force: bool = False,
) -> dict:
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        try:
            row = await transcript_delta.compute_delta(
                ticker=ticker, db=db, fmp=fmp, force=force,
            )
        except transcript_delta.InsufficientTranscriptsError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
    return _orm_to_dict(row)
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
python -m unittest backend.tests.test_transcripts_delta_api -v
```

Expected: `Ran 5 tests in ...s OK`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/transcripts_delta.py backend/tests/test_transcripts_delta_api.py
git commit -m "feat(api): POST /api/transcripts/delta/{ticker}?force (3 tests)"
```

---

### Task 9: Workspace Step 2 integration

**Files:**
- Modify: `backend/app/services/workspace_steps.py`

- [ ] **Step 1: Locate the research step**

```bash
grep -n "def step_research\|async def research\|def research_step\|step_2" backend/app/services/workspace_steps.py | head
```

Confirm the function name (likely `step_research` or `research_step`). Read the function body to find where the prompt is composed.

- [ ] **Step 2: Add the delta call before prompt composition**

In `step_research` (replace `<step_research>` with the actual name from Step 1), add after the function's existing data fetches and before the prompt string is built:

```python
from backend.app.services import transcript_delta as transcript_delta_svc

try:
    delta_row = await transcript_delta_svc.compute_delta(
        ticker=ticker, db=db, fmp=fmp, force=False,
    )
    transcript_delta_block = _format_transcript_delta(delta_row)
except transcript_delta_svc.InsufficientTranscriptsError:
    transcript_delta_block = ""
except Exception as exc:  # noqa: BLE001 — best-effort enrichment
    logger.warning("transcript_delta failed for %s: %r", ticker, exc)
    transcript_delta_block = ""
```

Add this helper near the top of the file (after other helper imports):

```python
def _format_transcript_delta(row) -> str:
    """Render the axes payload as a prompt-friendly markdown block."""
    populated = [(k, v) for (k, v) in row.axes.items() if v is not None]
    if not populated:
        return ""
    lines = ["Recent transcript-language deltas (anchors, not paraphrases):"]
    for key, ax in populated:
        lines.append(f"- {key}: {ax['direction']} ({ax['magnitude']}) — {ax['summary']}")
    return "\n".join(lines)
```

In the prompt-composition section, inject `transcript_delta_block` into the user-prompt template wherever supplementary context blocks already live (search for `{filing_excerpts}` or similar slot keys in this file to confirm placement convention).

- [ ] **Step 3: Run the workspace tests**

```bash
python -m unittest backend.tests.test_workspace -v 2>&1 | tail -10
```

If tests reference the function under test directly, none should break — the new branch is best-effort and returns `""` on any failure. If any test does break, mock `transcript_delta_svc.compute_delta` to `AsyncMock(side_effect=InsufficientTranscriptsError(...))` in that test.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/workspace_steps.py
git commit -m "feat(workspace): Step 2 (Research) consumes transcript_delta as prompt input"
```

---

### Task 10: Frontend typed client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Locate the workspace API client and add types below it**

```bash
grep -n "workspaceApi\|outcomesApi" frontend/lib/api.ts | head
```

Note the line where `outcomesApi` ends (or the file's end). Insert below it:

```typescript
// ── Transcript delta ────────────────────────────────────────────────────────

export type TranscriptAxisDirection = "softening" | "strengthening" | "stable";
export type TranscriptAxisMagnitude = "minor" | "material" | "regime_change";

export interface TranscriptQuoteRef {
  year: number;
  quarter: number;
  role: string;
  text: string;
}

export interface TranscriptAxisDelta {
  direction: TranscriptAxisDirection;
  magnitude: TranscriptAxisMagnitude;
  summary: string;
  quotes: TranscriptQuoteRef[];
}

export interface TranscriptAxesDelta {
  business_quality: TranscriptAxisDelta | null;
  risk_assessment: TranscriptAxisDelta | null;
  growth_earnings: TranscriptAxisDelta | null;
  sentiment_narrative: TranscriptAxisDelta | null;
  management_governance: TranscriptAxisDelta | null;
  future_durability: TranscriptAxisDelta | null;
  macro_regime: TranscriptAxisDelta | null;
  financial_health: TranscriptAxisDelta | null;
  valuation_stage: TranscriptAxisDelta | null;
}

export interface TranscriptDeltaRead {
  id: string;
  ticker: string;
  transcripts_window: { year: number; quarter: number }[];
  axes: TranscriptAxesDelta;
  computed_at: string;
}

export const transcriptDeltaApi = {
  async getLatest(ticker: string): Promise<TranscriptDeltaRead | null> {
    const r = await fetch(`${API_BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}/latest`);
    if (r.status === 204) return null;
    if (!r.ok) throw new Error(`getLatest ${ticker}: ${r.status}`);
    return r.json();
  },
  async getHistory(ticker: string): Promise<TranscriptDeltaRead[]> {
    return apiFetch(`/api/transcripts/delta/${encodeURIComponent(ticker)}/history`);
  },
  async compute(ticker: string, opts: { force?: boolean } = {}): Promise<TranscriptDeltaRead> {
    const qs = opts.force ? "?force=true" : "";
    const r = await fetch(
      `${API_BASE}/api/transcripts/delta/${encodeURIComponent(ticker)}${qs}`,
      { method: "POST" },
    );
    if (r.status === 404) throw new Error(`No transcripts available for ${ticker}`);
    if (!r.ok) throw new Error(`compute ${ticker}: ${r.status}`);
    return r.json();
  },
};
```

- [ ] **Step 2: Verify lint**

```bash
cd frontend && npx --no-install eslint lib/api.ts 2>&1 | tail -5
```

Expected: clean (no errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): transcriptDeltaApi types + client"
```

---

### Task 11: WhatChangedPanel component

**Files:**
- Create: `frontend/components/deep-dive/sections/WhatChangedPanel.tsx`

- [ ] **Step 1: Write the component**

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  transcriptDeltaApi,
  type TranscriptAxisDelta,
  type TranscriptDeltaRead,
} from "@/lib/api";

const CATEGORY_LABELS: Record<string, string> = {
  business_quality: "Business Quality",
  risk_assessment: "Risk Assessment",
  growth_earnings: "Growth & Earnings",
  sentiment_narrative: "Sentiment & Narrative",
  management_governance: "Management & Governance",
  future_durability: "Future Durability",
  macro_regime: "Macro & Regime",
  financial_health: "Financial Health",
  valuation_stage: "Valuation & Stage",
};

function directionClass(d: TranscriptAxisDelta["direction"]): string {
  if (d === "softening") return "bg-red-100 text-red-800 border-red-200";
  if (d === "strengthening") return "bg-green-100 text-green-800 border-green-200";
  return "bg-[var(--surface-2)] text-[var(--text)] border-[var(--border)]";
}

function magnitudeLabel(m: TranscriptAxisDelta["magnitude"]): string {
  return { minor: "minor", material: "material", regime_change: "regime change" }[m];
}

export function WhatChangedPanel({ ticker }: { ticker: string }) {
  const [delta, setDelta] = useState<TranscriptDeltaRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const latest = await transcriptDeltaApi.getLatest(ticker);
        if (!cancelled) setDelta(latest);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [ticker]);

  const compute = async (force: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const fresh = await transcriptDeltaApi.compute(ticker, { force });
      setDelta(fresh);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <section id="what-changed" className="px-4 py-6 border-b border-[var(--border)]" />;
  }

  if (!delta) {
    return (
      <section id="what-changed" className="px-4 py-6 border-b border-[var(--border)]">
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-2">What changed</h2>
        <p className="text-sm text-[var(--text-muted)] mb-3">
          Detect QoQ shifts in management's transcript language across the 9 deep-dive categories.
        </p>
        <button
          type="button"
          onClick={() => compute(false)}
          disabled={busy}
          data-print-hide="true"
          className="px-3 py-1.5 text-sm rounded bg-[var(--primary)] text-white disabled:opacity-50"
        >
          {busy ? "Computing…" : "Compute transcript delta"}
        </button>
        {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      </section>
    );
  }

  const populated = (Object.entries(delta.axes) as [keyof typeof CATEGORY_LABELS, TranscriptAxisDelta | null][])
    .filter(([, v]) => v !== null) as [string, TranscriptAxisDelta][];

  return (
    <section id="what-changed" className="px-4 py-6 border-b border-[var(--border)]">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)]">
          What changed — last {delta.transcripts_window.length} quarters
        </h2>
        <button
          type="button"
          onClick={() => compute(true)}
          disabled={busy}
          data-print-hide="true"
          className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] disabled:opacity-50"
        >
          {busy ? "Recomputing…" : "Recompute"}
        </button>
      </div>

      {populated.length === 0 && (
        <p className="text-sm text-[var(--text-muted)]">
          No material language shifts detected across these {delta.transcripts_window.length} quarters.
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {populated.map(([key, ax]) => (
          <div key={key} className="border border-[var(--border)] rounded p-3 bg-[var(--surface)]">
            <div className="flex items-center justify-between mb-1.5">
              <div className="text-sm font-medium">{CATEGORY_LABELS[key]}</div>
              <span className={`px-2 py-0.5 text-xs rounded border ${directionClass(ax.direction)}`}>
                {ax.direction} · {magnitudeLabel(ax.magnitude)}
              </span>
            </div>
            <p className="text-sm text-[var(--text)] mb-2">{ax.summary}</p>
            {ax.quotes.length > 0 && (
              <details className="text-xs">
                <summary className="text-[var(--text-muted)] cursor-pointer">
                  {ax.quotes.length} verbatim quote{ax.quotes.length === 1 ? "" : "s"}
                </summary>
                <ul className="mt-1.5 space-y-1.5">
                  {ax.quotes.map((q, i) => (
                    <li key={i} className="border-l-2 border-[var(--border)] pl-2 text-[var(--text-muted)]">
                      <span className="font-medium">Q{q.quarter} {q.year} · {q.role}:</span>{" "}
                      "{q.text}"
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
    </section>
  );
}
```

- [ ] **Step 2: Verify lint**

```bash
cd frontend && npx --no-install eslint components/deep-dive/sections/WhatChangedPanel.tsx 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/sections/WhatChangedPanel.tsx
git commit -m "feat(deep-dive): WhatChangedPanel component"
```

---

### Task 12: Wire the panel into DeepDiveDashboard + sections registry

**Files:**
- Modify: `frontend/components/deep-dive/DeepDiveDashboard.tsx`
- Modify: `frontend/components/deep-dive/sections.ts`

- [ ] **Step 1: Locate the Management & Governance slot**

```bash
grep -n "Management" frontend/components/deep-dive/DeepDiveDashboard.tsx
```

- [ ] **Step 2: Insert the panel above Management & Governance**

In `DeepDiveDashboard.tsx`, at the top with other imports:

```typescript
import { WhatChangedPanel } from "@/components/deep-dive/sections/WhatChangedPanel";
```

Find the JSX block that renders the Management & Governance section. Immediately **above** that block, add:

```tsx
<WhatChangedPanel ticker={ticker} />
```

(The `ticker` prop is already in scope per the existing component contract; verify by reading the surrounding lines.)

- [ ] **Step 3: Register in sections.ts**

```bash
grep -n "management_governance\|management-governance\|Management" frontend/components/deep-dive/sections.ts
```

Add an entry immediately before the management entry:

```typescript
{ id: "what-changed", label: "What changed", group: "qualitative" },
```

Use whatever exact field names the existing entries use (`id` / `label` / `group` or similar — match the convention by reading 2-3 adjacent entries first).

- [ ] **Step 4: Verify lint**

```bash
cd frontend && npx --no-install eslint components/deep-dive/DeepDiveDashboard.tsx components/deep-dive/sections.ts 2>&1 | tail -5
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive/DeepDiveDashboard.tsx frontend/components/deep-dive/sections.ts
git commit -m "feat(deep-dive): slot WhatChangedPanel above Management & Governance + section registry"
```

---

### Task 13: Full-suite verification

- [ ] **Step 1: Run full backend test suite**

```bash
source backend/venv/bin/activate && python -m unittest discover -s backend/tests -p "test_*.py" 2>&1 | tail -5
```

Expected: `Ran 230+ tests in ...s OK` (33 outcome + ~3 verdict + 6 transcript_delta + 5 transcripts_delta_api + everything else; pre-existing 221 + the 11 added on this branch).

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: build succeeds; `/pipeline/[runId]` route still listed in the route table.

- [ ] **Step 3: Manual smoke test (one ticker)**

Start the backend (`uvicorn backend.app.main:app --reload` from project root) and the frontend (`npm run dev` from `frontend/`). Open a research run page for a ticker with at least 2 ingested transcripts (e.g. one used in the verdict-outcome backfill). Confirm the "What changed" CTA renders. Click it, confirm a delta computes and renders 3-6 populated axes within ~5-10 seconds. Click "Recompute" — confirm it re-runs and replaces the panel (or returns the same cached row, depending on whether new transcripts have appeared).

- [ ] **Step 4: Update TODO.md**

In `TODO.md`, remove the "Earnings call transcript delta analysis" bullet from `## Backlog / v3` and add a short summary to `## Done (recent)`:

```markdown
- **Earnings call transcript delta analysis.** Detects QoQ language shifts across the 4 most recent transcripts on the 9 deep-dive category axes; null axes when management doesn't materially address them. New `transcript_deltas` table keyed by `(ticker, sha1 of (year,quarter) tuples)` — cache hit on identical inputs is free; new transcript drops trigger a new row (history capped at 8 per ticker). Three endpoints under `/api/transcripts/delta/{ticker}` (POST compute, GET latest, GET history). Surfaces as a `WhatChangedPanel` immediately above Management & Governance on the deep-dive page; workspace Step 2 consumes it best-effort as a prompt input. ~11 new tests; full backend suite green.
```

- [ ] **Step 5: Commit**

```bash
git add TODO.md
git commit -m "docs: transcript delta analysis shipped — move from backlog to done"
```

---

## Self-review

- **Spec coverage:** Storage (Task 1, 3), Pydantic schemas (Task 2), service fingerprint + idempotency (Task 4, 5, 6), API endpoints (Task 7, 8), workspace integration (Task 9), frontend client (Task 10), frontend panel (Task 11, 12), full-suite verification (Task 13). All spec sections covered.
- **Placeholder scan:** none. Every step has runnable commands or complete code.
- **Type consistency:** `AxesDelta` field names align between Pydantic (Task 2), the LLM prompt (Task 6), the ORM JSONB shape (Task 1), the TS interface (Task 10), the component render (Task 11), and the workspace formatter (Task 9). `HISTORY_CAP=8` consistent between service (Task 6) and spec.
