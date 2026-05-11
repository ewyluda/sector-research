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
