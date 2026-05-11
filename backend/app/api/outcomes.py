"""GET /api/outcomes/*, POST /api/outcomes/backfill."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.db import async_session, unit_of_work
from backend.app.models.outcome import VerdictOutcome
from backend.app.models.outcome_schemas import BackfillSummary, OutcomeDetail
from backend.app.services import outcome_tracker

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


# ── Serialization helper ──────────────────────────────────────────────────────

def _outcome_to_detail_dict(outcome: VerdictOutcome) -> dict:
    offset_order = ("1d", "1w", "1m", "3m", "6m")
    snaps = sorted(
        outcome.snapshots,
        key=lambda s: (
            offset_order.index(s.snapshot_offset)
            if s.snapshot_offset in offset_order
            else 999
        ),
    )
    return {
        "id": outcome.id,
        "source_type": outcome.source_type,
        "source_id": outcome.source_id,
        "ticker": outcome.ticker,
        "theme_id": outcome.theme_id,
        "verdict": outcome.verdict,
        "verdict_emitted_at": outcome.verdict_emitted_at,
        "entry_price_at": outcome.entry_price_at,
        "entry_price": outcome.entry_price,
        "sector_etf_ticker": outcome.sector_etf_ticker,
        "superseded_at": outcome.superseded_at,
        "closed_at": outcome.closed_at,
        "realized_ticker_return_pct": outcome.realized_ticker_return_pct,
        "realized_spy_excess_pct": outcome.realized_spy_excess_pct,
        "realized_sector_excess_pct": outcome.realized_sector_excess_pct,
        "realized_theme_basket_excess_pct": outcome.realized_theme_basket_excess_pct,
        "snapshots": [
            {
                "snapshot_offset": s.snapshot_offset,
                "snapshot_date": s.snapshot_date,
                "ticker_price": s.ticker_price,
                "spy_price": s.spy_price,
                "sector_etf_price": s.sector_etf_price,
                "theme_basket_value": s.theme_basket_value,
                "ticker_return_pct": s.ticker_return_pct,
                "spy_excess_pct": s.spy_excess_pct,
                "sector_excess_pct": s.sector_excess_pct,
                "theme_basket_excess_pct": s.theme_basket_excess_pct,
            }
            for s in snaps
        ],
        "theme_basket_constituents": outcome.theme_basket_constituents,
        "signal_snapshot": outcome.signal_snapshot,
    }


# ── Internal fetch helpers (module-level so tests can patch them) ─────────────

async def _get_outcome_by_source(*, source_type: str, source_id: str, db) -> dict | None:
    outcome = (
        await db.execute(
            select(VerdictOutcome)
            .where(
                VerdictOutcome.source_type == source_type,
                VerdictOutcome.source_id == source_id,
            )
            .options(selectinload(VerdictOutcome.snapshots))
        )
    ).scalar_one_or_none()
    if outcome is None:
        return None
    return _outcome_to_detail_dict(outcome)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED, response_model=BackfillSummary)
async def trigger_backfill(request: Request) -> BackfillSummary:
    """One-shot backfill of verdict_outcomes from completed research + workspace runs.

    Idempotent. Safe to call multiple times. Returns 202 with summary stats.
    """
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
    return summary


@router.get("/by-source/{source_type}/{source_id}", response_model=OutcomeDetail)
async def get_outcome_by_source(source_type: str, source_id: str) -> OutcomeDetail:
    """Fetch a single outcome by its originating run (source_type + source_id)."""
    if source_type not in ("research_run", "workspace_run"):
        raise HTTPException(status_code=400, detail="invalid source_type")
    async with async_session() as db:
        payload = await _get_outcome_by_source(
            source_type=source_type, source_id=source_id, db=db
        )
    if payload is None:
        raise HTTPException(status_code=404, detail="outcome not found")
    return payload
