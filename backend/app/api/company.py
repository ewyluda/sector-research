"""Company workspace API.

Routes:
  GET /api/company/{ticker}/header   → live quote + identity for the shell header
"""
from fastapi import APIRouter, Depends, Request

from backend.app.models.ticker import Ticker, TickerPath
from backend.app.services.company_snapshot import (
    CompanyFinancials,
    CompanyHeader,
    CompanyOverview,
    build_company_financials,
    build_company_header,
    build_company_overview,
)
from backend.app.services.company_transcripts import (
    Transcript,
    TranscriptList,
    TranscriptSummary,
    build_transcript,
    build_transcript_list,
    summarize_transcript,
)

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/{ticker}/header", response_model=CompanyHeader)
async def get_company_header(
    request: Request, ticker: Ticker = Depends(TickerPath)
) -> CompanyHeader:
    return await build_company_header(request.app.state.fmp, ticker)


@router.get("/{ticker}/overview", response_model=CompanyOverview)
async def get_company_overview(
    request: Request, ticker: Ticker = Depends(TickerPath)
) -> CompanyOverview:
    return await build_company_overview(request.app.state.fmp, ticker)


@router.get("/{ticker}/financials", response_model=CompanyFinancials)
async def get_company_financials(
    request: Request, ticker: Ticker = Depends(TickerPath), period: str = "quarter"
) -> CompanyFinancials:
    period = "annual" if period == "annual" else "quarter"
    return await build_company_financials(request.app.state.fmp, ticker, period=period)


@router.get("/{ticker}/transcripts", response_model=TranscriptList)
async def get_company_transcripts(
    request: Request, ticker: Ticker = Depends(TickerPath)
) -> TranscriptList:
    return await build_transcript_list(request.app.state.fmp, ticker)


@router.get("/{ticker}/transcripts/{year}/{quarter}", response_model=Transcript)
async def get_company_transcript(
    request: Request, year: int, quarter: int, ticker: Ticker = Depends(TickerPath)
) -> Transcript:
    return await build_transcript(request.app.state.fmp, ticker, year, quarter)


@router.post("/{ticker}/transcripts/{year}/{quarter}/summary", response_model=TranscriptSummary)
async def post_company_transcript_summary(
    request: Request, year: int, quarter: int, ticker: Ticker = Depends(TickerPath)
) -> TranscriptSummary:
    md = await summarize_transcript(request.app.state.fmp, ticker, year, quarter)
    return TranscriptSummary(summary_md=md)
