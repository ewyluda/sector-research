# backend/app/api/models_api.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.ticker_model import TickerModel
from backend.app.models.ticker_model_draft import TickerModelDraft
from backend.app.models.model_state import ModelState
from backend.app.services.model_baseline import initialize_or_get_model
from backend.app.services.model_balancing import recompute, ModelBalanceError

router = APIRouter(prefix="/api/models", tags=["models"])


# ---------------------------------------------------------------------------
# Task 18: GET + POST /initialize
# ---------------------------------------------------------------------------

@router.get("/{ticker}")
async def get_model(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    stmt = (
        select(TickerModel)
        .where(TickerModel.ticker == ticker)
        .order_by(desc(TickerModel.version))
        .limit(1)
    )
    latest = (await db.execute(stmt)).scalar_one_or_none()
    if latest is None:
        return {"latest_version": None, "draft": None}
    draft = (
        await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
    ).scalar_one_or_none()
    return {
        "latest_version": {
            "id": latest.id,
            "ticker": latest.ticker,
            "version": latest.version,
            "label": latest.label,
            "state": latest.state,
            "created_at": latest.created_at.isoformat(),
        },
        "draft": (
            {
                "base_version_id": draft.base_version_id,
                "state": draft.state,
                "updated_at": draft.updated_at.isoformat(),
            }
            if draft
            else None
        ),
    }


@router.post("/{ticker}/initialize")
async def initialize(ticker: str, force: bool = False) -> dict:
    """Seed (or re-seed if force=true) a model for the ticker."""
    try:
        row = await initialize_or_get_model(ticker, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": row.id,
        "ticker": row.ticker,
        "version": row.version,
        "state": row.state,
        "label": row.label,
    }
