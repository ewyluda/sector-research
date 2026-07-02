"""Earnings prints indexer.

Walks active status-board tickers, pulls FMP earnings calendar, and
upserts EarningsPrint rows. Idempotent on (ticker, fiscal_year,
fiscal_quarter); newly-populated `epsActual` upgrades a row from
"estimates only" to "estimates + actuals."

This service does NOT fetch transcripts or compute guidance direction —
that's the scheduler's job (see services/earnings_scheduler.py).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.earnings_print import EarningsPrint
from backend.app.services.universe import latest_runs_sql

logger = logging.getLogger(__name__)


def _derive_fiscal_period(earnings_date: date) -> tuple[int, int]:
    """Best-effort fiscal year/quarter from a calendar earnings date.

    For non-calendar-year reporters, this is approximate — the unique
    constraint is on the inferred values, not on a pristine fiscal
    mapping. If FMP later exposes fiscal_year/fiscal_quarter in the
    earnings calendar response (it currently does not in /stable/earnings),
    swap this for the explicit values.
    """
    quarter = (earnings_date.month - 1) // 3 + 1
    return earnings_date.year, quarter


def _compute_surprise(estimated: float | None, actual: float | None) -> float | None:
    """(actual - estimated) / |estimated|. None when either side is None
    or estimated is zero."""
    if estimated is None or actual is None:
        return None
    if estimated == 0:
        return None
    return (actual - estimated) / abs(estimated)


async def fetch_active_board_tickers(db: AsyncSession) -> list[str]:
    """Distinct uppercased tickers with an active thesis — the same
    latest-run definition the status board / calendar / material-events
    scan use (services/universe.py::latest_runs_sql), so watchlist-verdict
    theses are included. Projected down to `ticker` here: the shared CTE
    selects full rows incl. the large `state` JSONB, which this caller
    would otherwise fetch only to discard."""
    sql, params = latest_runs_sql(theme_id=None, include_archived=False)
    rows = (await db.execute(text(f"SELECT ticker FROM ({sql}) active"), params)).all()
    return sorted({str(r[0]).upper() for r in rows})


async def index_earnings_prints(
    ticker: str,
    fmp: FMPClient,
    db: AsyncSession,
) -> list[EarningsPrint]:
    """Pull FMP earnings calendar for a ticker, upsert prints. Returns
    the affected ORM rows after refresh.

    FMP /stable/earnings shape per row:
        {symbol, date: 'YYYY-MM-DD', epsActual, epsEstimated,
         revenueActual, revenueEstimated, lastUpdated}

    epsActual is null for upcoming prints, populated post-print.
    The upsert deliberately does NOT clobber guidance_direction,
    transcript_year, transcript_quarter — those are populated by the
    scheduler's transcript pass and survive subsequent calendar refreshes.
    """
    try:
        rows, _ = await fmp.get_earnings_calendar(ticker, limit=4)
    except Exception as e:
        logger.warning("[%s] FMP earnings calendar fetch failed: %s", ticker, e)
        return []

    if not rows:
        return []

    affected: list[EarningsPrint] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        date_str = row.get("date")
        if not date_str:
            continue
        try:
            earnings_date = date.fromisoformat(date_str[:10])
        except ValueError:
            continue
        fy, fq = _derive_fiscal_period(earnings_date)

        eps_est = row.get("epsEstimated")
        eps_act = row.get("epsActual")
        rev_est = row.get("revenueEstimated")
        rev_act = row.get("revenueActual")

        values = dict(
            ticker=ticker.upper(),
            fiscal_year=fy,
            fiscal_quarter=fq,
            earnings_date=earnings_date,
            eps_estimated=eps_est,
            eps_actual=eps_act,
            revenue_estimated=rev_est,
            revenue_actual=rev_act,
            eps_surprise_pct=_compute_surprise(eps_est, eps_act),
            revenue_surprise_pct=_compute_surprise(rev_est, rev_act),
            ingested_at=datetime.now(timezone.utc),
        )

        stmt = pg_insert(EarningsPrint).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_earnings_prints_period",
            set_={
                "earnings_date": stmt.excluded.earnings_date,
                "eps_estimated": stmt.excluded.eps_estimated,
                "eps_actual": stmt.excluded.eps_actual,
                "revenue_estimated": stmt.excluded.revenue_estimated,
                "revenue_actual": stmt.excluded.revenue_actual,
                "eps_surprise_pct": stmt.excluded.eps_surprise_pct,
                "revenue_surprise_pct": stmt.excluded.revenue_surprise_pct,
                "ingested_at": stmt.excluded.ingested_at,
            },
        ).returning(EarningsPrint.id)
        result = await db.execute(stmt)
        row_id = result.scalar_one()
        loaded = await db.get(EarningsPrint, row_id)
        if loaded is not None:
            await db.refresh(loaded)
            affected.append(loaded)

    return affected
