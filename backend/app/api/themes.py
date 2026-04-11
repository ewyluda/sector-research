"""Theme CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.theme import Theme

router = APIRouter(tags=["themes"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ThemeCreate(BaseModel):
    name: str
    description: str | None = None
    parent_theme_id: str | None = None
    seed_tickers: list[str] = []
    screener_criteria: dict = {}
    x_search_terms: list[str] = []
    signal_weights: dict = {
        "x_velocity": 0.40,
        "fundamental_quality": 0.40,
        "discovery": 0.20,
    }


class ThemeResponse(BaseModel):
    id: str
    name: str
    description: str | None
    parent_theme_id: str | None
    seed_tickers: list | dict
    screener_criteria: dict
    x_search_terms: list | dict
    signal_weights: dict

    class Config:
        from_attributes = True


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/themes", response_model=list[ThemeResponse])
async def list_themes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Theme).order_by(Theme.name))
    return result.scalars().all()


@router.post("/themes", response_model=ThemeResponse, status_code=201)
async def create_theme(payload: ThemeCreate, db: AsyncSession = Depends(get_db)):
    theme = Theme(
        name=payload.name,
        description=payload.description,
        parent_theme_id=payload.parent_theme_id,
        seed_tickers=payload.seed_tickers,
        screener_criteria=payload.screener_criteria,
        x_search_terms=payload.x_search_terms,
        signal_weights=payload.signal_weights,
    )
    db.add(theme)
    await db.commit()
    await db.refresh(theme)
    return theme


@router.get("/themes/{theme_id}", response_model=ThemeResponse)
async def get_theme(theme_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/themes/{theme_id}", response_model=ThemeResponse)
async def update_theme(
    theme_id: str, payload: ThemeCreate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    theme.name = payload.name
    theme.description = payload.description
    theme.parent_theme_id = payload.parent_theme_id
    theme.seed_tickers = payload.seed_tickers
    theme.screener_criteria = payload.screener_criteria
    theme.x_search_terms = payload.x_search_terms
    theme.signal_weights = payload.signal_weights

    await db.commit()
    await db.refresh(theme)
    return theme


@router.delete("/themes/{theme_id}", status_code=204)
async def delete_theme(theme_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    await db.delete(theme)
    await db.commit()
