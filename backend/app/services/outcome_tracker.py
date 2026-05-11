"""Verdict outcome tracking — alpha feedback loop.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.outcome import (
    SectorEtfMapping,
    VerdictOutcome,
    VerdictReturnSnapshot,
)
from backend.app.models.outcome_schemas import (
    BackfillSummary,
    EntryConstituent,
    EntryPriceBundle,
    RefreshSummary,
)

logger = logging.getLogger(__name__)


SNAPSHOT_OFFSETS: list[tuple[str, int]] = [
    ("1d", 1),
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
]

ENTRY_PRICE_LOOKAHEAD_DAYS = 7
SUPPORTED_SOURCE_TYPES = ("research_run", "workspace_run")


def calendar_target(entry_price_at: date, offset_key: str) -> date:
    """Return the calendar target date for a snapshot offset. Snapshot uses first trading day >= target."""
    for key, days in SNAPSHOT_OFFSETS:
        if key == offset_key:
            return entry_price_at + timedelta(days=days)
    raise ValueError(f"unknown offset {offset_key!r}")


def all_offset_keys() -> list[str]:
    return [k for (k, _) in SNAPSHOT_OFFSETS]


async def _resolve_entry_prices(
    *,
    ticker: str,
    verdict_emitted_at: datetime,
    theme_seed_tickers: list[str] | None,
    sector_etf_ticker: str | None,
    fmp: FMPClient,
) -> EntryPriceBundle:
    """Resolve entry-anchored prices for outcome creation.

    Entry day = first trading day STRICTLY AFTER verdict_emitted_at's calendar date.
    Fetches close price for ticker + SPY + (optional) sector ETF + theme constituents,
    all anchored to the same entry day for fair comparison.

    Uses FMPClient.get_historical_price_adjusted(ticker, from_date: str, to_date: str)
    which returns tuple[list[dict], Citation] with rows {date: str, close: float, ...}
    where close is split + dividend adjusted.
    """
    emitted_date = verdict_emitted_at.astimezone(timezone.utc).date()
    range_start = emitted_date + timedelta(days=1)
    range_end = emitted_date + timedelta(days=ENTRY_PRICE_LOOKAHEAD_DAYS)

    ticker_rows, _ = await fmp.get_historical_price_adjusted(
        ticker, range_start.isoformat(), range_end.isoformat()
    )
    if not ticker_rows:
        raise LookupError(
            f"no FMP price for {ticker} between {range_start} and {range_end}"
        )
    first = sorted(ticker_rows, key=lambda r: r["date"])[0]
    entry_day: date = date.fromisoformat(first["date"])
    ticker_price = Decimal(str(first["close"]))

    async def _close_on(symbol: str, target_day: date) -> Decimal | None:
        rows, _ = await fmp.get_historical_price_adjusted(
            symbol, target_day.isoformat(), target_day.isoformat()
        )
        if not rows:
            return None
        for r in rows:
            if r["date"] == target_day.isoformat():
                return Decimal(str(r["close"]))
        return None

    spy_price = await _close_on("SPY", entry_day)

    sector_price: Decimal | None = None
    if sector_etf_ticker:
        sector_price = await _close_on(sector_etf_ticker, entry_day)

    constituents: list[EntryConstituent] = []
    if theme_seed_tickers:
        for t in theme_seed_tickers:
            px = await _close_on(t, entry_day)
            if px is not None:
                constituents.append(EntryConstituent(ticker=t, entry_price=px))

    return EntryPriceBundle(
        entry_price_at=entry_day,
        ticker_price=ticker_price,
        spy_price=spy_price,
        sector_etf_ticker=sector_etf_ticker,
        sector_etf_price=sector_price,
        theme_basket_constituents=constituents,
    )
