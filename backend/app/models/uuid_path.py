"""Shared guards for UUID-keyed resource ids in API params.

The UUID-PK tables (research_runs, journal_trades, material_events,
verdict_outcomes — all `UUID(as_uuid=False)` columns) make asyncpg cast the
bound parameter before any existence check runs, so a malformed id 500s at
the driver instead of 404ing. These guards reject non-UUID ids with the same
404 the row lookup would produce.

Use `Depends(<X>IdPath)` in route handlers for path params (the function's
arg name must match the path placeholder); call the guard directly for
body/query values — the same dual-use convention as models/ticker.py's
TickerPath.

Known still-unguarded: the theme routes (themes.id is also UUID) keep their
historical 500-on-malformed behavior — tracked in TODO.md.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException


def _uuid_or_404(value: str, detail: str) -> str:
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=404, detail=detail)
    return value


def RunIdPath(run_id: str) -> str:
    """404 on malformed research-run ids (api/pipeline.py + api/status.py)."""
    return _uuid_or_404(run_id, "Run not found")


def TradeIdPath(trade_id: str) -> str:
    """404 on malformed journal-trade ids."""
    return _uuid_or_404(trade_id, "trade not found")


def EventIdPath(event_id: str) -> str:
    """404 on malformed material-event ids."""
    return _uuid_or_404(event_id, "Event not found")


def OutcomeIdOr404(outcome_id: str) -> str:
    """Directly-callable variant for verdict-outcome ids in request bodies."""
    return _uuid_or_404(outcome_id, "outcome not found")
