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


from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from backend.app.clients.fmp import FMPClient  # noqa: E402
from backend.app.models.transcript_delta import TranscriptDelta  # noqa: E402
from backend.app.services.edgar_transcripts_relationships import fetch_recent_transcripts  # noqa: E402

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
