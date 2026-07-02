"""Unified calendar read model: economic releases + universe earnings +
thesis catalysts, merged statelessly at request time.

No tables, no scheduler (spec Approach A). Read-only; never commits —
callers own the session. Spec:
docs/superpowers/specs/2026-06-09-unified-calendar-design.md
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation
from backend.app.services.universe import Universe, resolve_universe as get_universe

logger = logging.getLogger(__name__)

__all__ = ["Universe", "get_universe"]  # re-exported for callers/tests of this module


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
        raw = str(r.get("date") or "")
        ts: datetime | None = None
        has_time = False
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                ts = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
                has_time = fmt != "%Y-%m-%d"
                break
            except ValueError:
                continue
        if ts is None:
            continue
        out.append(CalendarEvent(
            kind="economic",
            date=ts.date(),
            timestamp=ts if has_time else None,
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


# ── Thesis catalysts ──────────────────────────────────────────────────────────

# Same "latest run with structured thesis" CTE as the List view
# (api/catalysts._build_list_catalysts_sql) — kept in sync by the pin test.
# Range filter happens in SQL: windowed rows by overlap, dated rows by BETWEEN.
# Undated rows are excluded by construction (spec: they live in the List view).
# A windowed row whose FMP-overridden expected_date (date_source='fmp_earnings',
# up to 30d outside the window) falls in range is included even when its
# window doesn't overlap — matches the List view, which buckets by expected_date.
CATALYST_RANGE_SQL = """
    WITH latest AS (
        SELECT DISTINCT ON (ticker) id, ticker, created_at
        FROM research_runs
        WHERE jsonb_typeof(state->'phase_outputs'->'thesis'->'structured') = 'object'
        ORDER BY ticker, created_at DESC
    )
    SELECT c.*
    FROM catalysts c
    JOIN latest l ON c.run_id = l.id
    WHERE (
        (c.expected_window_end IS NOT NULL
         AND (
            (COALESCE(c.expected_window_start, c.expected_date) <= :end_date
             AND c.expected_window_end >= :start_date)
            OR (c.expected_date IS NOT NULL
                AND c.expected_date BETWEEN :start_date AND :end_date)
         ))
        OR
        (c.expected_window_end IS NULL
         AND c.expected_date IS NOT NULL
         AND c.expected_date BETWEEN :start_date AND :end_date)
    )
    ORDER BY c.expected_date NULLS LAST, c.ticker, c.ordinal
"""


def _catalyst_events(rows: list[dict]) -> list[CalendarEvent]:
    out: list[CalendarEvent] = []
    for r in rows:
        windowed = r["expected_window_end"] is not None
        d = r["expected_date"] or r["expected_window_end"]
        out.append(CalendarEvent(
            kind="catalyst",
            date=d,
            ticker=r["ticker"],
            title=r["description"],
            detail={
                "run_id": str(r["run_id"]),
                "catalyst_id": str(r["id"]),
                "type": r["type"],
                "timeframe": r["timeframe"],
                "linked_pillar": r["linked_pillar"],
                "windowed": windowed,
                "window_start": r["expected_window_start"].isoformat()
                if r["expected_window_start"] else None,
                "window_end": r["expected_window_end"].isoformat()
                if r["expected_window_end"] else None,
            },
            citation=None,  # catalysts carry provenance via their run
        ))
    return out


# ── Merge orchestrator ────────────────────────────────────────────────────────

_KIND_ORDER = {"economic": 0, "earnings": 1, "catalyst": 2}


async def get_calendar_events(
    db: AsyncSession, fmp: FMPClient, start: date, end: date
) -> CalendarResponse:
    """Merge the three sources. FMP failures degrade to warnings — never
    500 on a partial outage (spec error-handling section)."""
    universe = await get_universe(db)
    events: list[CalendarEvent] = []
    warnings: list[str] = []

    try:
        rows, cit = await fmp.get_economic_calendar(start.isoformat(), end.isoformat())
        events.extend(_econ_events(rows, cit))
    except Exception:
        logger.exception("economic calendar fetch failed")
        warnings.append("Economic calendar unavailable (FMP error)")

    try:
        rows, cit = await fmp.get_earnings_calendar_range(start.isoformat(), end.isoformat())
        events.extend(_earnings_events(rows, universe, cit))
    except Exception:
        logger.exception("earnings calendar fetch failed")
        warnings.append("Earnings calendar unavailable (FMP error)")

    cat_rows = (await db.execute(
        text(CATALYST_RANGE_SQL), {"start_date": start, "end_date": end}
    )).mappings().all()
    events.extend(_catalyst_events(list(cat_rows)))

    events.sort(key=lambda e: (e.date, _KIND_ORDER[e.kind], e.ticker or ""))
    return CalendarResponse(
        events=events,
        universe_size=len(universe.tickers),
        warnings=warnings,
    )
