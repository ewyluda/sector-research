"""Theme CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.theme import Theme

router = APIRouter(tags=["themes"])


def _normalize_tickers(raw) -> list[str]:
    """Uppercase, strip, drop empties, dedupe (order-preserving).

    Tolerates list-of-strings or the legacy list-of-dicts shape (entries
    with a ``"ticker"`` key) — mirrors ``fanout.py``'s defensive read.
    """
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for entry in raw:
        if isinstance(entry, str):
            value = entry
        elif isinstance(entry, dict) and entry.get("ticker"):
            value = str(entry["ticker"])
        else:
            continue
        norm = value.strip().upper()
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


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


class TickerPayload(BaseModel):
    ticker: str


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
        seed_tickers=_normalize_tickers(payload.seed_tickers),
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
    theme.seed_tickers = _normalize_tickers(payload.seed_tickers)
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


@router.post("/themes/{theme_id}/tickers", response_model=ThemeResponse)
async def add_theme_ticker(
    theme_id: str,
    payload: TickerPayload,
    db: AsyncSession = Depends(get_db),
):
    """Append a ticker to ``seed_tickers`` (idempotent on duplicate)."""
    norm = payload.ticker.strip().upper()
    if not norm:
        raise HTTPException(status_code=400, detail="ticker must not be empty")

    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    current = _normalize_tickers(theme.seed_tickers)
    if norm not in current:
        # Reassign — JSONB mutations are not auto-detected by SQLAlchemy.
        theme.seed_tickers = current + [norm]
        await db.commit()
        await db.refresh(theme)
    return theme


@router.delete("/themes/{theme_id}/tickers/{ticker}", response_model=ThemeResponse)
async def remove_theme_ticker(
    theme_id: str,
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Drop a ticker from ``seed_tickers`` (idempotent on absent).

    Does NOT cascade-delete signals or signal_history rows for that ticker
    — historical data is preserved by design.
    """
    norm = ticker.strip().upper()

    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    current = _normalize_tickers(theme.seed_tickers)
    if norm in current:
        theme.seed_tickers = [t for t in current if t != norm]
        await db.commit()
        await db.refresh(theme)
    return theme
