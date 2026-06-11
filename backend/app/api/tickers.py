"""GET /api/tickers — distinct known tickers for the global command palette.

Union of theme seed_tickers ∪ research_runs.ticker ∪ ticker_models.ticker.
Deliberately DB-only (no FMP) so the palette opens instantly."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.research_run import ResearchRun
from backend.app.models.theme import Theme
from backend.app.models.ticker_model import TickerModel

router = APIRouter(prefix="/api", tags=["tickers"])


@router.get("/tickers")
async def list_tickers(db: AsyncSession = Depends(get_db)) -> list[dict]:
    tickers: set[str] = set()

    for theme in (await db.execute(select(Theme))).scalars().all():
        for entry in theme.seed_tickers or []:
            if isinstance(entry, str):
                cleaned = entry.strip().upper()
                if cleaned:
                    tickers.add(cleaned)

    for (t,) in (await db.execute(select(ResearchRun.ticker).distinct())).all():
        if t:
            tickers.add(t.upper())

    for (t,) in (await db.execute(select(TickerModel.ticker).distinct())).all():
        if t:
            tickers.add(t.upper())

    return [{"ticker": t} for t in sorted(tickers)]
