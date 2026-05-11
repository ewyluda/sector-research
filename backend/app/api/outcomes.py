"""GET /api/outcomes/*, POST /api/outcomes/backfill."""
from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.app.db import unit_of_work
from backend.app.models.outcome_schemas import BackfillSummary
from backend.app.services import outcome_tracker

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED, response_model=BackfillSummary)
async def trigger_backfill(request: Request) -> BackfillSummary:
    """One-shot backfill of verdict_outcomes from completed research + workspace runs.

    Idempotent. Safe to call multiple times. Returns 202 with summary stats.
    """
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
    return summary
