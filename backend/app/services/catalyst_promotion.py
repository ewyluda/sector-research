"""Promote parsed Catalyst objects from a thesis into first-class DB rows.

Called from node_thesis_construction immediately after parse_structured_output
succeeds. Per-run scoping: each call inserts a fresh set of rows; old
rows from prior runs of the same ticker remain as historical record.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.graph.state import ResearchState
from backend.app.models.catalyst import Catalyst
from backend.app.models.phase_schemas import ThesisOutput
from backend.app.services.catalyst_dates import ParsedDates, parse_timeframe

logger = logging.getLogger(__name__)

# Slack window for matching FMP earnings dates against parsed timeframes.
# A "Q2 2026" parsed window ends Jun 30, but the actual earnings print may
# fall a few weeks later (mid-July). Allow this much buffer past window_end.
_FMP_EARNINGS_SLACK_DAYS = 30


def _midpoint(parsed: ParsedDates) -> date | None:
    """Best single date for the calendar from a parsed window.

    Picks the midpoint when both ends are present, falls back to either
    end alone, returns None when both are None.
    """
    if parsed.window_start and parsed.window_end:
        delta_days = (parsed.window_end - parsed.window_start).days
        return date.fromordinal(parsed.window_start.toordinal() + delta_days // 2)
    return parsed.window_start or parsed.window_end


async def _try_fmp_earnings_override(
    fmp: FMPClient, ticker: str, parsed: ParsedDates
) -> date | None:
    """Fetch FMP earnings calendar; return the earliest upcoming earnings
    date that falls inside the parsed window (with a small slack), else None."""
    try:
        events, _ = await fmp.get_earnings_calendar(ticker)
    except Exception as e:  # network / FMP errors are non-fatal
        logger.warning("[%s] FMP earnings calendar fetch failed: %s", ticker, e)
        return None
    if not events:
        return None

    today = datetime.now(timezone.utc).date()

    # Build a window: prefer parsed window, else "next 365 days" as fallback
    if parsed.window_start and parsed.window_end:
        lower = max(parsed.window_start, today)
        upper = parsed.window_end + timedelta(days=_FMP_EARNINGS_SLACK_DAYS)
    else:
        lower = today
        upper = today + timedelta(days=365)

    candidates: list[date] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        # Only consider future events (epsActual is null for upcoming earnings)
        if ev.get("epsActual") is not None:
            continue
        raw = ev.get("date")
        if not raw:
            continue
        try:
            d = date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if lower <= d <= upper:
            candidates.append(d)
    if not candidates:
        return None
    return min(candidates)


async def promote_catalysts(
    state: ResearchState,
    parsed: ThesisOutput,
    fmp: FMPClient,
    db: AsyncSession,
    relative_anchor: datetime | None = None,
) -> int:
    """Insert one Catalyst row per parsed.catalysts entry. Returns count.

    Caller owns the transaction. This function adds rows and flushes,
    but does not commit — callers must commit (or rollback) the session
    they passed in.

    `relative_anchor` is the reference datetime for relative timeframes
    like "Next 1-3 mo". Live thesis runs should leave it None to use
    "now" (they run minutes after run creation, so the difference is
    negligible). The backfill script should pass the original run's
    created_at so historical relative timeframes anchor correctly.
    """
    if relative_anchor is None:
        relative_anchor = datetime.now(timezone.utc)
    inserted = 0

    for ordinal, c in enumerate(parsed.catalysts, start=1):
        parsed_dates = parse_timeframe(c.timeframe, relative_anchor)
        expected_date: date | None = _midpoint(parsed_dates)
        date_source = parsed_dates.source

        if c.type == "earnings":
            override = await _try_fmp_earnings_override(fmp, state.ticker, parsed_dates)
            if override is not None:
                expected_date = override
                date_source = "fmp_earnings"

        db.add(Catalyst(
            run_id=state.run_id,
            ticker=state.ticker,
            ordinal=ordinal,
            timeframe=c.timeframe,
            description=c.description,
            type=c.type,
            signposts=list(c.signposts or []),
            linked_pillar=c.linked_pillar,
            expected_date=expected_date,
            expected_window_start=parsed_dates.window_start,
            expected_window_end=parsed_dates.window_end,
            date_source=date_source,
        ))
        inserted += 1

    await db.flush()
    logger.info("[%s] promoted %d catalyst rows for run %s",
                state.ticker, inserted, state.run_id)
    return inserted
