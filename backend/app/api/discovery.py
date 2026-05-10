"""Discovery API endpoints.

GET /api/themes/{theme_id}/discover
  Runs the two-pass discovery (FMP screener + cached X signals).
  Returns ranked CompanySignalCards. Does NOT trigger on-demand X API calls.

POST /api/themes/{theme_id}/signals/refresh
  Manually trigger X signal refresh for a theme (admin use, rate-limit aware).
  Normally this runs on the daily scheduler.
"""

import dataclasses
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.theme import Theme
from backend.app.services.discovery import DiscoveryEngine, CompanySignalCard
from backend.app.services.signal_history import list_signal_history

logger = logging.getLogger(__name__)
router = APIRouter(tags=["discovery"])

ALLOWED_SIGNAL_TYPES = {"velocity", "narrative", "discovery"}
MAX_HISTORY_DAYS = 365


def _card_to_dict(card: CompanySignalCard) -> dict[str, Any]:
    """Serialize a CompanySignalCard to a JSON-safe dict."""
    return {
        "ticker": card.ticker,
        "company_name": card.company_name,
        "market_cap": card.market_cap,
        "sector": card.sector,
        "industry": card.industry,
        "signal_source_badge": card.signal_source_badge,
        "is_surprise": card.is_surprise,
        "is_seed": card.is_seed,
        "combined_score": card.combined_score,
        "fundamental_quality_score": card.fundamental_quality_score,
        "last_run_id": card.last_run_id,
        "last_conviction_score": card.last_conviction_score,
        "last_thesis_status": card.last_thesis_status,
        "fmp": {
            "roic": card.fmp.roic,
            "gross_margin": card.fmp.gross_margin,
            "revenue_growth_yoy": card.fmp.revenue_growth_yoy,
            "pe_ratio": card.fmp.pe_ratio,
            "market_cap": card.fmp.market_cap,
        },
        "x_signal": {
            "direction": card.x_signal.direction,
            "ratio": card.x_signal.ratio,
            "narrative_summary": card.x_signal.narrative_summary,
            "discovery_score": card.x_signal.discovery_score,
            "is_stale": card.x_signal.is_stale,
        },
        "citations": [
            {
                "metric": c.metric,
                "source_name": c.source_name,
                "source_url": c.source_url,
                "tier": c.tier,
                "value": str(c.value),
            }
            for c in card.citations
        ],
    }


@router.get("/themes/{theme_id}/discover")
async def discover_theme(
    theme_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    sort_by: str = "combined_score",  # combined_score | x_velocity | fundamental_quality | market_cap
    filter_surprise: bool = False,
    filter_researched: bool = False,
):
    """
    Run two-pass discovery for a theme.
    Returns ranked company signal cards.
    """
    # Load theme
    result = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = result.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    # Run discovery
    fmp = request.app.state.fmp
    x_client = request.app.state.x_client
    engine = DiscoveryEngine(fmp=fmp, x_client=x_client)

    cards = await engine.run(theme=theme, db=db)

    # Apply filters
    if filter_surprise:
        cards = [c for c in cards if c.is_surprise]
    if filter_researched:
        cards = [c for c in cards if c.last_run_id is not None]

    # Apply sort
    sort_map = {
        "combined_score": lambda c: c.combined_score,
        "x_velocity": lambda c: c.x_signal.ratio or 0.0,
        "fundamental_quality": lambda c: c.fundamental_quality_score,
        "market_cap": lambda c: c.market_cap or 0.0,
    }
    sort_fn = sort_map.get(sort_by, sort_map["combined_score"])
    cards.sort(key=sort_fn, reverse=True)

    # Count surprises for dashboard summary
    surprise_count = sum(1 for c in cards if c.is_surprise)
    accelerating_count = sum(1 for c in cards if c.x_signal.direction == "accelerating")
    has_stale = any(c.x_signal.is_stale for c in cards)

    return {
        "theme_id": theme_id,
        "theme_name": theme.name,
        "company_count": len(cards),
        "surprise_count": surprise_count,
        "accelerating_count": accelerating_count,
        "signal_status": "stale" if has_stale else "fresh",
        "companies": [_card_to_dict(c) for c in cards],
    }


@router.get("/themes/{theme_id}/signals/{ticker}/history")
async def get_signal_history_endpoint(
    theme_id: str,
    ticker: str,
    signal_type: str = "velocity",
    days: int = 90,
    db: AsyncSession = Depends(get_db),
):
    """Return time-series rows for one (ticker, theme_id, signal_type).

    Ordered oldest → newest. `days` clamped to [1, 365].
    `signal_type` ∈ {velocity, narrative, discovery}.

    Each `points[].value` is the JSONB payload written by the X client and
    is returned opaquely. Per `signal_type`, consumers can rely on:
    - `velocity`: `{"ratio": float, "direction": str}` — see `XSignalVelocity`
      in `frontend/lib/api.ts` for the canonical shape.
    - `narrative`: `{"summary": str, ...}`
    - `discovery`: `{"score": float, ...}`
    Source of truth for these shapes is `clients/x_client.py`. If a payload
    key changes, this docstring and any consumer indexing into `value` must
    be updated together.
    """
    if signal_type not in ALLOWED_SIGNAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"signal_type must be one of {sorted(ALLOWED_SIGNAL_TYPES)}",
        )
    days = max(1, min(days, MAX_HISTORY_DAYS))

    theme_lookup = await db.execute(select(Theme).where(Theme.id == theme_id))
    theme = theme_lookup.scalar_one_or_none()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    ticker_norm = ticker.upper()
    rows = await list_signal_history(
        db=db,
        ticker=ticker_norm,
        theme_id=theme_id,
        signal_type=signal_type,
        days=days,
    )

    return {
        "theme_id": theme_id,
        "ticker": ticker_norm,
        "signal_type": signal_type,
        "days": days,
        "points": [
            {
                "computed_at": row.computed_at.isoformat(),
                "value": row.value,
            }
            for row in rows
        ],
    }
