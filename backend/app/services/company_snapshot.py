"""Company-workspace snapshot service.

Slice 1 surfaces only the header (live quote + identity from FMP). Later slices
add /overview, /financials, /transcripts to this module.
"""
from typing import Optional

from pydantic import BaseModel


class CompanyHeader(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    logo_url: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    delay_label: str = "15 min delay"


def _as_dict(value) -> dict:
    """FMP helpers return dicts, but degrade defensively to {} for [] / None."""
    return value if isinstance(value, dict) else {}


async def build_company_header(fmp, ticker: str) -> CompanyHeader:
    """Assemble the persistent header payload.

    `fmp` is the shared FMPClient (app.state.fmp). Quote feeds price/change;
    profile feeds identity. Missing data degrades to None — the shell never
    needs more than the ticker to render.
    """
    ticker = ticker.upper()

    try:
        quote, _ = await fmp.get_quote(ticker)
    except Exception:
        quote = {}
    try:
        profile, _ = await fmp.get_company_profile(ticker)
    except Exception:
        profile = {}

    quote = _as_dict(quote)
    profile = _as_dict(profile)

    price = quote.get("price")
    if price is None:
        price = profile.get("price")

    return CompanyHeader(
        ticker=ticker,
        name=profile.get("companyName"),
        exchange=profile.get("exchangeShortName"),
        logo_url=profile.get("image"),
        currency=profile.get("currency"),
        price=price,
        change=quote.get("change"),
        change_pct=quote.get("changePercentage"),
    )
