"""Transcript delta analysis — Haiku-extracted QoQ language deltas."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

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


from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from backend.app.clients.fmp import FMPClient  # noqa: E402
from backend.app.graph.llm import HAIKU, complete  # noqa: E402
from backend.app.models.transcript_delta import TranscriptDelta  # noqa: E402
from backend.app.models.transcript_delta_schemas import AxesDelta  # noqa: E402
from backend.app.services.edgar_transcripts_relationships import fetch_recent_transcripts  # noqa: E402

TRANSCRIPT_WINDOW = 4
MIN_TRANSCRIPTS_FOR_DELTA = 2
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

    existing = (await db.execute(
        select(TranscriptDelta).where(
            TranscriptDelta.ticker == ticker,
            TranscriptDelta.transcripts_fingerprint == fingerprint,
        )
    )).scalar_one_or_none()

    if existing is not None and not force:
        return existing

    raw = await complete(
        model=HAIKU,
        system=_SYSTEM_PROMPT,
        user=_build_user_prompt(transcripts),
        assistant_prefill='{"axes":',
        max_tokens=2500,
    )
    payload_str = raw
    parsed = json.loads(payload_str)
    axes = AxesDelta.model_validate(parsed["axes"]).model_dump()

    if existing is not None:
        # force=True path: refresh in place — avoids unique constraint violation
        existing.axes = axes
        existing.computed_at = datetime.now(timezone.utc)
        await db.flush()
        return existing

    # New fingerprint: insert
    row = TranscriptDelta(
        id=str(uuid4()),
        ticker=ticker,
        transcripts_window=window,
        transcripts_fingerprint=fingerprint,
        axes=axes,
        computed_at=datetime.now(timezone.utc),
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
