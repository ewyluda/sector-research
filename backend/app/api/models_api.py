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


# ---------------------------------------------------------------------------
# Task 19: PUT /draft (cell edit + recompute)
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402
from pydantic import BaseModel as _BM  # noqa: E402


class DraftEditRequest(_BM):
    cell_path: str           # "drivers.2026Y.gross_margin_pct" | "income_statement.revenue.2026Q1"
    value: float | None
    source: str | None = None  # "driver" | "override"; ignored for assumption cells


def _apply_edit(state_dict: dict, edit: DraftEditRequest) -> dict:
    """Mutate state JSON dict in place, returning the mutated dict."""
    parts = edit.cell_path.split(".")
    if parts[0] == "drivers" and len(parts) == 3:
        period, key = parts[1], parts[2]
        state_dict["drivers"][period][key] = {
            "value": edit.value,
            "source": edit.source or "driver",
            "formula": None,
            "citation_id": None,
            "last_edited_at": datetime.utcnow().isoformat(),
            "last_edited_by": "user",
        }
    elif parts[0] in ("income_statement", "balance_sheet", "cash_flow") and len(parts) == 3:
        stmt, line, period = parts
        state_dict[stmt][line][period] = {
            "value": edit.value,
            "source": edit.source or "override",
            "formula": None,
            "citation_id": None,
            "last_edited_at": datetime.utcnow().isoformat(),
            "last_edited_by": "user",
        }
    elif parts[0] == "assumptions" and len(parts) == 2:
        key = parts[1]
        cur = state_dict["assumptions"][key]
        if isinstance(cur, dict):
            cur["value"] = edit.value
            cur["last_edited_at"] = datetime.utcnow().isoformat()
            cur["last_edited_by"] = "user"
        else:
            state_dict["assumptions"][key] = edit.value
    else:
        raise ValueError(f"unknown cell_path shape: {edit.cell_path}")
    return state_dict


@router.put("/{ticker}/draft")
async def put_draft(ticker: str, edit: DraftEditRequest, db: AsyncSession = Depends(get_db)) -> dict:
    # Get current state: existing draft, else latest version
    draft = (
        await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
    ).scalar_one_or_none()
    if draft is None:
        latest = (
            await db.execute(
                select(TickerModel)
                .where(TickerModel.ticker == ticker)
                .order_by(desc(TickerModel.version))
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="no model exists for ticker")
        state_dict = dict(latest.state)
        base_version_id = latest.id
    else:
        state_dict = dict(draft.state)
        base_version_id = draft.base_version_id

    state_dict = _apply_edit(state_dict, edit)
    # Recompute
    try:
        state = ModelState.model_validate(state_dict)
        state = recompute(state)
        state_dict = state.model_dump()
    except ModelBalanceError as e:
        raise HTTPException(status_code=409, detail=f"BS imbalance: {e}")

    if draft is None:
        draft = TickerModelDraft(
            ticker=ticker, base_version_id=base_version_id, state=state_dict
        )
        db.add(draft)
    else:
        draft.state = state_dict
    await db.commit()
    await db.refresh(draft)
    return {
        "ticker": ticker,
        "base_version_id": draft.base_version_id,
        "state": draft.state,
        "updated_at": draft.updated_at.isoformat(),
    }
