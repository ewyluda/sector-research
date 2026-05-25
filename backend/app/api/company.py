"""Company workspace API.

Routes:
  GET /api/company/{ticker}/header   → live quote + identity for the shell header
"""
from fastapi import APIRouter, Request

from backend.app.services.company_snapshot import CompanyHeader, build_company_header

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/{ticker}/header", response_model=CompanyHeader)
async def get_company_header(ticker: str, request: Request) -> CompanyHeader:
    return await build_company_header(request.app.state.fmp, ticker)
