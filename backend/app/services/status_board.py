"""Status board aggregator.

Read-time aggregation, no caching. Pulls the latest completed run per
(ticker, theme), joins with catalysts and kill_criterion_states, and
returns one StatusBoardEntry per active thesis with computed health.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.catalysts import CatalystRow, nearest_catalyst
from backend.app.models import Catalyst, KillCriterionState, ResearchRun, Theme

logger = logging.getLogger(__name__)

STALE_DAYS = 90
IMMINENT_DAYS = 30

_HEALTH_SEVERITY = {
    "broken": 4,
    "triggered": 3,
    "stale": 2,
    "imminent": 1,
    "healthy": 0,
}


@dataclass
class KillCriteriaSummary:
    total: int
    triggered: int


@dataclass
class NextCatalyst:
    description: str
    type: str | None
    expected_date: date | None
    expected_window_end: date | None
    days_until: int | None


@dataclass
class StatusBoardEntry:
    ticker: str
    theme_id: str
    theme_name: str
    run_id: str
    thesis_status: str
    conviction_score: int | None
    completed_at: datetime
    days_since_update: int
    health: str
    health_reasons: list[str] = field(default_factory=list)
    next_catalyst: NextCatalyst | None = None
    kill_criteria_summary: KillCriteriaSummary = field(
        default_factory=lambda: KillCriteriaSummary(0, 0)
    )


@dataclass
class StatusBoardResponse:
    entries: list[StatusBoardEntry]
    total: int
    generated_at: datetime


def _to_catalyst_row(c: Catalyst) -> CatalystRow:
    return CatalystRow(
        id=str(c.id),
        run_id=str(c.run_id),
        ticker=c.ticker,
        ordinal=c.ordinal,
        timeframe=c.timeframe,
        description=c.description,
        type=c.type,
        signposts=c.signposts or [],
        linked_pillar=c.linked_pillar,
        expected_date=c.expected_date,
        expected_window_start=c.expected_window_start,
        expected_window_end=c.expected_window_end,
        date_source=c.date_source,
        created_at=c.created_at,
    )


def _build_next_catalyst(rows: list[CatalystRow], today: date) -> NextCatalyst | None:
    chosen = nearest_catalyst(rows, today)
    if chosen is None:
        return None
    if chosen.expected_date is not None:
        days = (chosen.expected_date - today).days
    elif chosen.expected_window_end is not None:
        days = (chosen.expected_window_end - today).days
    else:
        days = None
    return NextCatalyst(
        description=chosen.description,
        type=chosen.type,
        expected_date=chosen.expected_date,
        expected_window_end=chosen.expected_window_end,
        days_until=days,
    )


def _resolve_health(
    thesis_status: str,
    triggered_count: int,
    days_since_update: int,
    next_cat: NextCatalyst | None,
) -> tuple[str, list[str]]:
    """Return (health, reasons). Reasons accumulate every condition that fired."""
    reasons: list[str] = []

    if thesis_status == "BROKEN":
        reasons.append("Thesis marked BROKEN")
    if triggered_count > 0:
        reasons.append(
            f"{triggered_count} kill criteri{'on' if triggered_count == 1 else 'a'} triggered"
        )
    if days_since_update > STALE_DAYS:
        reasons.append(f"No re-run in {days_since_update}d")
    if (
        next_cat is not None
        and next_cat.days_until is not None
        and 0 <= next_cat.days_until <= IMMINENT_DAYS
    ):
        reasons.append(f"Catalyst in {next_cat.days_until}d")
    elif (
        next_cat is not None
        and next_cat.days_until is not None
        and next_cat.days_until < 0
        and next_cat.expected_window_end is not None
    ):
        # window already started but not ended
        reasons.append("Catalyst window in progress")

    if thesis_status == "BROKEN":
        return "broken", reasons
    if triggered_count > 0:
        return "triggered", reasons
    if days_since_update > STALE_DAYS:
        return "stale", reasons
    if (
        next_cat is not None
        and next_cat.days_until is not None
        and 0 <= next_cat.days_until <= IMMINENT_DAYS
        and (
            next_cat.expected_window_end is None
            or next_cat.expected_window_end >= datetime.now(timezone.utc).date()
        )
    ):
        return "imminent", reasons
    return "healthy", reasons


async def build_status_board(
    db: AsyncSession,
    *,
    theme_id: str | None = None,
    include_archived: bool = False,
) -> StatusBoardResponse:
    """Compute the fleet view from current DB state."""
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)

    # Latest completed/watchlist run per (ticker, theme_id) that isn't archived.
    # Use DISTINCT ON for the per-pair latest selection.
    where_archived = "" if include_archived else "AND r.archived_at IS NULL"
    where_theme = "AND r.theme_id = :theme_id" if theme_id else ""
    params: dict[str, str] = {}
    if theme_id:
        params["theme_id"] = theme_id

    sql = f"""
        SELECT DISTINCT ON (r.ticker, r.theme_id)
            r.id, r.ticker, r.theme_id, r.status, r.state, r.updated_at, r.created_at
        FROM research_runs r
        WHERE r.status IN ('completed', 'watchlist')
          {where_archived}
          {where_theme}
        ORDER BY r.ticker, r.theme_id, r.updated_at DESC
    """
    result = await db.execute(text(sql), params)
    run_rows = result.mappings().all()

    if not run_rows:
        return StatusBoardResponse(entries=[], total=0, generated_at=now)

    run_ids = [str(row["id"]) for row in run_rows]
    theme_ids = list({str(row["theme_id"]) for row in run_rows})

    # Theme name lookup
    theme_result = await db.execute(select(Theme).where(Theme.id.in_(theme_ids)))
    themes_by_id = {t.id: t.name for t in theme_result.scalars()}

    # All catalysts for these runs
    cat_result = await db.execute(select(Catalyst).where(Catalyst.run_id.in_(run_ids)))
    catalysts_by_run: dict[str, list[CatalystRow]] = {}
    for c in cat_result.scalars():
        catalysts_by_run.setdefault(str(c.run_id), []).append(_to_catalyst_row(c))

    # All kill-criterion states for these runs
    kc_result = await db.execute(
        select(KillCriterionState).where(KillCriterionState.run_id.in_(run_ids))
    )
    kc_by_run: dict[str, list[KillCriterionState]] = {}
    for s in kc_result.scalars():
        kc_by_run.setdefault(str(s.run_id), []).append(s)

    entries: list[StatusBoardEntry] = []
    for row in run_rows:
        run_id = str(row["id"])
        state = row["state"] or {}
        phase_outputs = state.get("phase_outputs", {}) if isinstance(state, dict) else {}
        thesis = phase_outputs.get("thesis") or {}
        structured = thesis.get("structured") if isinstance(thesis, dict) else None
        if not isinstance(structured, dict):
            logger.warning(
                "status_board.skip_run",
                extra={"run_id": run_id, "reason": "no thesis structured output"},
            )
            continue

        kill_criteria = structured.get("kill_criteria") or []
        thesis_status = state.get("thesis_status") or "PENDING"
        conviction_score = state.get("conviction_score")
        completed_at = row["updated_at"] or row["created_at"]
        days_since_update = (now - completed_at).days

        rows_for_run = catalysts_by_run.get(run_id, [])
        next_cat = _build_next_catalyst(rows_for_run, today)

        kc_total = len(kill_criteria)
        kc_triggered = sum(
            1
            for s in kc_by_run.get(run_id, [])
            if s.status == "triggered" and 0 <= s.ordinal < kc_total
        )

        health, reasons = _resolve_health(
            thesis_status, kc_triggered, days_since_update, next_cat
        )

        entries.append(
            StatusBoardEntry(
                ticker=row["ticker"],
                theme_id=str(row["theme_id"]),
                theme_name=themes_by_id.get(str(row["theme_id"]), ""),
                run_id=run_id,
                thesis_status=thesis_status,
                conviction_score=conviction_score,
                completed_at=completed_at,
                days_since_update=days_since_update,
                health=health,
                health_reasons=reasons,
                next_catalyst=next_cat,
                kill_criteria_summary=KillCriteriaSummary(
                    total=kc_total, triggered=kc_triggered
                ),
            )
        )

    entries.sort(
        key=lambda e: (
            -_HEALTH_SEVERITY[e.health],
            e.next_catalyst.days_until if e.next_catalyst and e.next_catalyst.days_until is not None else 1_000_000,
            -int(e.completed_at.timestamp()),
        )
    )

    return StatusBoardResponse(entries=entries, total=len(entries), generated_at=now)
