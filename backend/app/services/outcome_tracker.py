"""Verdict outcome tracking — alpha feedback loop.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.outcome import (
    SectorEtfMapping,
    VerdictOutcome,
    VerdictReturnSnapshot,
)
from backend.app.models.outcome_schemas import (
    BackfillSummary,
    EntryConstituent,
    EntryPriceBundle,
    RefreshSummary,
)

logger = logging.getLogger(__name__)


SNAPSHOT_OFFSETS: list[tuple[str, int]] = [
    ("1d", 1),
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
]

ENTRY_PRICE_LOOKAHEAD_DAYS = 7
SUPPORTED_SOURCE_TYPES = ("research_run", "workspace_run")


def calendar_target(entry_price_at: date, offset_key: str) -> date:
    """Return the calendar target date for a snapshot offset. Snapshot uses first trading day >= target."""
    for key, days in SNAPSHOT_OFFSETS:
        if key == offset_key:
            return entry_price_at + timedelta(days=days)
    raise ValueError(f"unknown offset {offset_key!r}")


def all_offset_keys() -> list[str]:
    return [k for (k, _) in SNAPSHOT_OFFSETS]
