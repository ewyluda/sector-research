"""Health check endpoints."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "sector-research-app"}


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """Verify database connectivity."""
    result = await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}


@router.get("/health/fmp")
async def health_fmp(request: Request):
    """Verify FMP API connectivity with a lightweight call."""
    fmp = request.app.state.fmp
    try:
        quote, citation = await fmp.get_quote("AAPL")
        return {
            "status": "ok",
            "fmp": "connected",
            "sample_price": quote.get("price") if isinstance(quote, dict) else None,
            "citation": {
                "source": citation.source_name,
                "tier": citation.tier,
            },
        }
    except Exception as e:
        return {"status": "error", "fmp": str(e)}
