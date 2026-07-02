"""The Universe — theme seed_tickers ∪ active-thesis tickers.

Single owner of "what counts as an active thesis": the latest completed/
watchlist, non-archived run per (ticker, theme). The status board (which
needs the full run rows), the unified calendar, and the daily material-events
scan all resolve the universe through this module instead of reaching into
each other.

Leaf module by design (sqlalchemy + Theme model + run_timestamps only), so
importing it never reopens the calendar↔status_board↔catalysts cycle that the
old deferred `_build_latest_runs_sql` imports were dodging. Change "what counts
as an active thesis" here and every daily surface inherits it by contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.theme import Theme
from backend.app.services.run_timestamps import completed_at_sql


def latest_runs_sql(
    *,
    theme_id: str | None,
    include_archived: bool,
) -> tuple[str, dict[str, str]]:
    """Latest completed/watchlist run per (ticker, theme), then optional
    archive filter.

    The single definition of "active thesis": every universe consumer and the
    status board read this CTE. The status board selects the full rows
    (`state`, `status`, timestamps); the universe resolvers below only read
    `ticker` / `theme_id` / `id` off it.
    """
    params: dict[str, str] = {}
    where_theme = ""
    if theme_id:
        params["theme_id"] = theme_id
        where_theme = "AND r.theme_id = :theme_id"

    completed_expr = completed_at_sql("r")
    where_archived = "" if include_archived else "WHERE archived_at IS NULL"

    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (r.ticker, r.theme_id)
                r.id,
                r.ticker,
                r.theme_id,
                r.status,
                r.state,
                r.created_at,
                r.archived_at,
                {completed_expr} AS completed_at
            FROM research_runs r
            WHERE r.status IN ('completed', 'watchlist')
              AND r.theme_id IS NOT NULL
              {where_theme}
            ORDER BY r.ticker, r.theme_id, {completed_expr} DESC, r.created_at DESC
        )
        SELECT *
        FROM latest
        {where_archived}
    """
    return sql, params


@dataclass
class Universe:
    """Theme seeds ∪ active theses."""

    tickers: set[str]
    thesis_runs: dict[str, str]  # ticker -> an active run_id (first CTE row wins)


async def _seed_tickers_by_theme(db: AsyncSession) -> dict[str, set[str]]:
    """themes.id -> uppercased seed set. The one place seed_tickers is read
    (tolerates legacy non-list JSONB shapes by treating them as empty)."""
    themes = (await db.execute(select(Theme))).scalars().all()
    return {
        str(t.id): {
            str(s).upper()
            for s in (t.seed_tickers if isinstance(t.seed_tickers, list) else [])
        }
        for t in themes
    }


async def resolve_universe(db: AsyncSession) -> Universe:
    """Global universe: every theme's seeds ∪ all active-thesis tickers."""
    tickers: set[str] = set()
    for seeds in (await _seed_tickers_by_theme(db)).values():
        tickers.update(seeds)

    sql, params = latest_runs_sql(theme_id=None, include_archived=False)
    run_rows = (await db.execute(text(sql), params)).mappings().all()
    thesis_runs: dict[str, str] = {}
    for r in run_rows:
        thesis_runs.setdefault(str(r["ticker"]).upper(), str(r["id"]))
    tickers.update(thesis_runs)

    return Universe(tickers=tickers, thesis_runs=thesis_runs)


async def resolve_universe_by_theme(db: AsyncSession) -> dict[str, set[str]]:
    """Per-theme universe: theme_id -> tickers (its seeds ∪ its active theses)."""
    out = await _seed_tickers_by_theme(db)

    sql, params = latest_runs_sql(theme_id=None, include_archived=False)
    for r in (await db.execute(text(sql), params)).mappings().all():
        out.setdefault(str(r["theme_id"]), set()).add(str(r["ticker"]).upper())
    return out
