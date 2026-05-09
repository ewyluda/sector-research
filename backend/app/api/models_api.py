# backend/app/api/models_api.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.cell_path import (
    AssumptionPath,
    DriverPath,
    StatementCellPath,
    parse as parse_cell_path,
)
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
    ticker = ticker.upper()
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
    ticker = ticker.upper()
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
    """Mutate state JSON dict in place, returning the mutated dict.

    Raises ValueError on unknown cell_path shapes or registry keys.
    """
    path = parse_cell_path(edit.cell_path)
    now = datetime.utcnow().isoformat()
    if isinstance(path, DriverPath):
        state_dict["drivers"][path.period][path.key] = {
            "value": edit.value,
            "source": edit.source or "driver",
            "formula": None,
            "citation_id": None,
            "last_edited_at": now,
            "last_edited_by": "user",
        }
    elif isinstance(path, StatementCellPath):
        state_dict[path.statement.value][path.line][path.period] = {
            "value": edit.value,
            "source": edit.source or "override",
            "formula": None,
            "citation_id": None,
            "last_edited_at": now,
            "last_edited_by": "user",
        }
    elif isinstance(path, AssumptionPath):
        # AssumptionPath only accepts ModelCell-shaped keys (validated at parse).
        cur = state_dict["assumptions"][path.key]
        cur["value"] = edit.value
        cur["last_edited_at"] = now
        cur["last_edited_by"] = "user"
    return state_dict


@router.put("/{ticker}/draft")
async def put_draft(ticker: str, edit: DraftEditRequest, db: AsyncSession = Depends(get_db)) -> dict:
    ticker = ticker.upper()
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

    try:
        state_dict = _apply_edit(state_dict, edit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
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


# ---------------------------------------------------------------------------
# Task 20: POST /save + DELETE /draft
# ---------------------------------------------------------------------------

class SaveVersionRequest(_BM):
    label: str | None = None


@router.post("/{ticker}/save")
async def save_version(
    ticker: str, body: SaveVersionRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    ticker = ticker.upper()
    draft = (
        await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
    ).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="no draft to save")
    latest = (
        await db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ticker)
            .order_by(desc(TickerModel.version))
            .limit(1)
        )
    ).scalar_one_or_none()
    next_version = 1 if latest is None else latest.version + 1
    new_row = TickerModel(
        ticker=ticker,
        version=next_version,
        state=draft.state,
        label=body.label or f"v{next_version}",
        parent_research_run_id=getattr(latest, "parent_research_run_id", None),
    )
    db.add(new_row)
    await db.delete(draft)
    await db.commit()
    await db.refresh(new_row)
    return {
        "id": new_row.id,
        "ticker": ticker,
        "version": new_row.version,
        "label": new_row.label,
    }


@router.delete("/{ticker}/draft")
async def discard_draft(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    ticker = ticker.upper()
    draft = (
        await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
    ).scalar_one_or_none()
    if draft is not None:
        await db.delete(draft)
        await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Task 21: GET /reverse-dcf
# ---------------------------------------------------------------------------

from backend.app.services.reverse_dcf import (  # noqa: E402
    solve_implied_driver,
    solve_implied_irr,
    sensitivity_grid,
    thesis_vs_priced_in,
)


async def _fetch_live_price(fmp, ticker: str) -> float:
    """Pulls current price from FMP. Returns 0.0 on any error so caller can fall back to user override."""
    try:
        quote, _citation = await fmp.get_quote(ticker)
        return float((quote.get("price") if quote else 0.0) or 0.0)
    except Exception:
        return 0.0


def _safe_solve(state: ModelState, dim: str, target: float):
    try:
        return solve_implied_driver(state, dimension=dim, target_per_share=target)
    except (ValueError, Exception):
        return None


def _safe_solve_irr(state: ModelState, target: float):
    try:
        return solve_implied_irr(state, target_per_share=target)
    except (ValueError, Exception):
        return None


@router.get("/{ticker}/reverse-dcf")
async def get_reverse_dcf(
    ticker: str,
    request: Request,
    price: float | None = None,
    from_draft: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ticker = ticker.upper()
    state_dict: dict | None = None
    if from_draft:
        draft = (
            await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
        ).scalar_one_or_none()
        state_dict = draft.state if draft else None
    if state_dict is None:
        latest = (
            await db.execute(
                select(TickerModel)
                .where(TickerModel.ticker == ticker)
                .order_by(desc(TickerModel.version))
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="no model exists")
        state_dict = latest.state

    state = ModelState.model_validate(state_dict)
    target = price if price is not None else await _fetch_live_price(request.app.state.fmp, ticker)
    if not target:
        raise HTTPException(status_code=502, detail="no live price available")

    return {
        "price_used": target,
        "price_source": "user_override" if price is not None else "fmp_live",
        "implied_drivers": {
            "revenue_growth_pct": _safe_solve(state, "revenue_growth_pct", target),
            "ebit_margin_pct": _safe_solve(state, "ebit_margin_pct", target),
            "terminal_multiple": _safe_solve(state, "terminal_multiple", target),
        },
        "implied_irr": _safe_solve_irr(state, target),
        "sensitivity_grids": {
            "growth_margin": sensitivity_grid(
                state,
                x_dim="revenue_growth_pct",
                x_range=(-0.05, 0.20),
                y_dim="ebit_margin_pct",
                y_range=(-0.10, 0.40),
            ),
            "growth_multiple": sensitivity_grid(
                state,
                x_dim="revenue_growth_pct",
                x_range=(-0.05, 0.20),
                y_dim="terminal_multiple",
                y_range=(5.0, 25.0),
            ),
            "margin_multiple": sensitivity_grid(
                state,
                x_dim="ebit_margin_pct",
                x_range=(-0.10, 0.40),
                y_dim="terminal_multiple",
                y_range=(5.0, 25.0),
            ),
        },
        "thesis_vs_priced_in": thesis_vs_priced_in(state, target_per_share=target),
    }


# ---------------------------------------------------------------------------
# Version history + diff
# ---------------------------------------------------------------------------
from backend.app.services.model_diff import diff_states  # noqa: E402


@router.get("/{ticker}/versions")
async def list_versions(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    ticker = ticker.upper()
    rows = (
        await db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ticker)
            .order_by(desc(TickerModel.version))
        )
    ).scalars().all()
    return {
        "versions": [
            {
                "id": r.id,
                "version": r.version,
                "label": r.label,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.get("/{ticker}/versions/{version}/diff")
async def version_diff(
    ticker: str,
    version: int,
    against: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ticker = ticker.upper()
    a = (
        await db.execute(
            select(TickerModel).where(
                TickerModel.ticker == ticker, TickerModel.version == against
            )
        )
    ).scalar_one_or_none()
    b = (
        await db.execute(
            select(TickerModel).where(
                TickerModel.ticker == ticker, TickerModel.version == version
            )
        )
    ).scalar_one_or_none()
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="version not found")
    return diff_states(ModelState.model_validate(a.state), ModelState.model_validate(b.state))
