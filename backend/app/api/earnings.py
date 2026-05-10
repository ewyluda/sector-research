"""Earnings cycle navigator API.

Routes:
  GET   /api/earnings/board?window_days=14
  POST  /api/runs/{run_id}/earnings/{print_id}/brief
  POST  /api/runs/{run_id}/earnings/{print_id}/verdict
  GET   /api/earnings/prints/{ticker}
  POST  /api/earnings/refresh/{ticker}
"""
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.catalyst import Catalyst
from backend.app.models.earnings_print import EarningsPrint
from backend.app.models.thesis_print_verdict import ThesisPrintVerdict
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.services.earnings_brief import compute_brief
from backend.app.services.earnings_prints import index_earnings_prints
from backend.app.services.earnings_verdict import compute_verdict

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Response models ─────────────────────────────────────────────────────────


class EarningsPrintRow(BaseModel):
    id: str
    ticker: str
    fiscal_year: int
    fiscal_quarter: int
    earnings_date: date
    eps_estimated: Optional[float]
    eps_actual: Optional[float]
    revenue_estimated: Optional[float]
    revenue_actual: Optional[float]
    eps_surprise_pct: Optional[float]
    revenue_surprise_pct: Optional[float]
    guidance_direction: Optional[str]


class ThesisPrintVerdictRow(BaseModel):
    id: str
    run_id: str
    earnings_print_id: str
    verdict: str
    summary_md: str
    pillars_addressed: list[str]
    generated_at: datetime


class MatchedEarningsCatalyst(BaseModel):
    ordinal: int
    signposts: list[str]
    description: str


class EarningsBoardEntry(BaseModel):
    run_id: str
    ticker: str
    theme_id: str
    phase: str  # "pre" | "post" | "none"
    print: Optional[EarningsPrintRow]
    matched_catalyst: Optional[MatchedEarningsCatalyst]
    verdict: Optional[ThesisPrintVerdictRow]


class EarningsBoardResponse(BaseModel):
    entries: list[EarningsBoardEntry]


class BriefResponse(BaseModel):
    summary_md: str
    pillars_addressed: list[str]
    generated_at: datetime


# ── Conversion helpers ──────────────────────────────────────────────────────


def _print_to_pydantic(p: EarningsPrint) -> EarningsPrintRow:
    return EarningsPrintRow(
        id=str(p.id),
        ticker=p.ticker,
        fiscal_year=p.fiscal_year,
        fiscal_quarter=p.fiscal_quarter,
        earnings_date=p.earnings_date,
        eps_estimated=p.eps_estimated,
        eps_actual=p.eps_actual,
        revenue_estimated=p.revenue_estimated,
        revenue_actual=p.revenue_actual,
        eps_surprise_pct=p.eps_surprise_pct,
        revenue_surprise_pct=p.revenue_surprise_pct,
        guidance_direction=p.guidance_direction,
    )


def _verdict_to_pydantic(v: ThesisPrintVerdict) -> ThesisPrintVerdictRow:
    return ThesisPrintVerdictRow(
        id=str(v.id),
        run_id=str(v.run_id),
        earnings_print_id=str(v.earnings_print_id),
        verdict=v.verdict,
        summary_md=v.summary_md,
        pillars_addressed=list(v.pillars_addressed or []),
        generated_at=v.generated_at,
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/earnings/board", response_model=EarningsBoardResponse)
async def get_earnings_board(
    window_days: int = 14,
    db: AsyncSession = Depends(get_db),
) -> EarningsBoardResponse:
    """One entry per active status-board thesis with an upcoming print
    within window_days OR a past print within window_days. Empty array
    when no prints fall in window."""
    today = datetime.now(timezone.utc).date()
    lo = today - timedelta(days=window_days)
    hi = today + timedelta(days=window_days)

    sql = text(
        """
        SELECT DISTINCT ON (ticker, theme_id)
            id, ticker, theme_id
        FROM research_runs
        WHERE status = 'completed' AND archived_at IS NULL AND theme_id IS NOT NULL
        ORDER BY ticker, theme_id, updated_at DESC
        """
    )
    runs = (await db.execute(sql)).all()

    entries: list[EarningsBoardEntry] = []
    for run_row in runs:
        run_id = str(run_row.id)
        ticker = run_row.ticker.upper()
        theme_id = str(run_row.theme_id)

        prints_q = (
            select(EarningsPrint)
            .where(EarningsPrint.ticker == ticker)
            .where(EarningsPrint.earnings_date >= lo)
            .where(EarningsPrint.earnings_date <= hi)
            .order_by(EarningsPrint.earnings_date.desc())
        )
        candidates = (await db.execute(prints_q)).scalars().all()
        if not candidates:
            continue  # no print in window; skip row entirely

        # Pick the most recent post-print if any, else the nearest upcoming.
        post = next((p for p in candidates if p.eps_actual is not None), None)
        upcoming = next(
            (p for p in candidates if p.eps_actual is None and p.earnings_date >= today),
            None,
        )
        chosen = post or upcoming
        if chosen is None:
            continue

        phase = "post" if chosen.eps_actual is not None else "pre"

        cat_q = (
            select(Catalyst)
            .where(Catalyst.run_id == run_id)
            .where(Catalyst.type == "earnings")
            .order_by(Catalyst.ordinal)
            .limit(1)
        )
        matched = (await db.execute(cat_q)).scalars().first()
        matched_pyd: Optional[MatchedEarningsCatalyst] = None
        if matched is not None:
            matched_pyd = MatchedEarningsCatalyst(
                ordinal=matched.ordinal,
                signposts=list(matched.signposts or []),
                description=matched.description,
            )

        verdict_q = (
            select(ThesisPrintVerdict)
            .where(ThesisPrintVerdict.run_id == run_id)
            .where(ThesisPrintVerdict.earnings_print_id == chosen.id)
            .limit(1)
        )
        v = (await db.execute(verdict_q)).scalars().first()

        entries.append(
            EarningsBoardEntry(
                run_id=run_id,
                ticker=ticker,
                theme_id=theme_id,
                phase=phase,
                print=_print_to_pydantic(chosen),
                matched_catalyst=matched_pyd,
                verdict=_verdict_to_pydantic(v) if v is not None else None,
            )
        )

    # Sort: post-print first (most recent), then pre-print (nearest upcoming).
    def sort_key(e: EarningsBoardEntry) -> tuple[int, int]:
        if e.print is None:
            return (2, 0)
        ord_ = e.print.earnings_date.toordinal()
        return (0, -ord_) if e.phase == "post" else (1, ord_)
    entries.sort(key=sort_key)
    return EarningsBoardResponse(entries=entries)


@router.post(
    "/runs/{run_id}/earnings/{print_id}/brief",
    response_model=BriefResponse,
)
async def post_brief(
    run_id: str,
    print_id: str,
    db: AsyncSession = Depends(get_db),
) -> BriefResponse:
    try:
        out = await compute_brief(run_id, print_id, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("brief generation failed: run=%s print=%s", run_id, print_id)
        raise HTTPException(status_code=502, detail="brief generation failed")
    return BriefResponse(
        summary_md=out.summary_md,
        pillars_addressed=out.pillars_addressed,
        generated_at=datetime.now(timezone.utc),
    )


@router.post(
    "/runs/{run_id}/earnings/{print_id}/verdict",
    response_model=ThesisPrintVerdictRow,
)
async def post_verdict(
    run_id: str,
    print_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ThesisPrintVerdictRow:
    fmp = request.app.state.fmp
    try:
        row = await compute_verdict(run_id, print_id, fmp, db)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("verdict generation failed: run=%s print=%s", run_id, print_id)
        raise HTTPException(status_code=502, detail="verdict generation failed")
    return _verdict_to_pydantic(row)


@router.get("/earnings/prints/{ticker}", response_model=list[EarningsPrintRow])
async def get_prints_by_ticker(
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> list[EarningsPrintRow]:
    q = (
        select(EarningsPrint)
        .where(EarningsPrint.ticker == ticker)
        .order_by(EarningsPrint.earnings_date.desc())
        .limit(8)
    )
    rows = (await db.execute(q)).scalars().all()
    return [_print_to_pydantic(r) for r in rows]


@router.post("/earnings/refresh/{ticker}")
async def post_refresh(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> dict:
    fmp = request.app.state.fmp
    try:
        rows = await index_earnings_prints(ticker, fmp, db)
        await db.commit()
    except Exception:
        logger.exception("manual earnings refresh failed: %s", ticker)
        raise HTTPException(status_code=502, detail="refresh failed")
    return {"updated": len(rows), "ticker": ticker}
