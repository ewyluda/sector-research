"""Unified calendar read model: economic releases + universe earnings +
thesis catalysts, merged statelessly at request time.

No tables, no scheduler (spec Approach A). Read-only; never commits —
callers own the session. Spec:
docs/superpowers/specs/2026-06-09-unified-calendar-design.md
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation
# Private import is deliberate: the status board owns the "active thesis"
# semantics (completed/watchlist, non-archived, theme-attached). Duplicating
# that SQL here is the bigger hazard.
from backend.app.services.status_board import _build_latest_runs_sql

logger = logging.getLogger(__name__)


# ── Wire schemas ──────────────────────────────────────────────────────────────


class CitationOut(BaseModel):
    """JSON-safe projection of the Citation dataclass (value coerced to str
    to match the frontend Citation type)."""

    metric: str
    source_name: str
    source_url: str
    tier: int
    value: str


class CalendarEvent(BaseModel):
    kind: Literal["economic", "earnings", "catalyst"]
    date: date
    timestamp: datetime | None = None   # econ rows carry intraday UTC time
    ticker: str | None = None           # None for economic
    title: str
    detail: dict[str, Any]
    citation: CitationOut | None = None


class CalendarResponse(BaseModel):
    events: list[CalendarEvent]
    universe_size: int
    warnings: list[str]


@dataclass
class Universe:
    """Theme seeds ∪ active theses (spec decision #1)."""

    tickers: set[str]
    thesis_runs: dict[str, str]  # ticker -> latest active run_id


def _citation_out(c: Citation) -> CitationOut:
    return CitationOut(
        metric=c.metric,
        source_name=c.source_name,
        source_url=c.source_url,
        tier=c.tier,
        value=str(c.value),
    )


# ── Pure event builders ───────────────────────────────────────────────────────


def _econ_events(rows: list[dict], citation: Citation) -> list[CalendarEvent]:
    """US high-impact releases only (spec decision #2)."""
    out: list[CalendarEvent] = []
    cit = _citation_out(citation)
    for r in rows:
        if r.get("country") != "US" or r.get("impact") != "High":
            continue
        raw = r.get("date") or ""
        ts: datetime | None = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        if ts is None:
            continue
        out.append(CalendarEvent(
            kind="economic",
            date=ts.date(),
            timestamp=ts,
            ticker=None,
            title=r.get("event") or "Economic release",
            detail={
                "estimate": r.get("estimate"),
                "previous": r.get("previous"),
                "actual": r.get("actual"),
                "unit": r.get("unit"),
            },
            citation=cit,
        ))
    return out


def _earnings_events(
    rows: list[dict], universe: Universe, citation: Citation
) -> list[CalendarEvent]:
    """Firehose rows filtered to the universe; thesis tickers carry the
    run_id so the UI can deep-link the EarningsDrawer."""
    out: list[CalendarEvent] = []
    cit = _citation_out(citation)
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if sym not in universe.tickers:
            continue
        try:
            d = date.fromisoformat(str(r.get("date") or ""))
        except ValueError:
            continue
        run_id = universe.thesis_runs.get(sym)
        out.append(CalendarEvent(
            kind="earnings",
            date=d,
            ticker=sym,
            title=sym,
            detail={
                "eps_estimated": r.get("epsEstimated"),
                "eps_actual": r.get("epsActual"),
                "revenue_estimated": r.get("revenueEstimated"),
                "revenue_actual": r.get("revenueActual"),
                "has_thesis": run_id is not None,
                "run_id": run_id,
            },
            citation=cit,
        ))
    return out
