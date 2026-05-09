"""Canonical ticker value object for the sector-research domain.

A `Ticker` is an uppercase, validated stock symbol. The whole codebase
stores tickers uppercase (`ticker_models`, `ticker_model_drafts`,
`research_runs`, `filings`, etc.), so case mismatches at the API
boundary previously led to silent wrong-row lookups.

Use `Ticker = Depends(TickerPath)` in FastAPI route handlers — it pulls
the `{ticker}` path param, normalizes, validates, and rejects garbage
with a 400 before any database work happens.

Internal callers (services, ORM queries) can still take `str` and
defensively `.upper()` — `Ticker` is a `NewType[str]`, runtime-identical
to a plain string.
"""
from __future__ import annotations

import re
from typing import NewType

from fastapi import HTTPException

# US tickers are 1-5 letters; some carry "." (BRK.A) or "-" (BRK-B). Keep
# the regex permissive but reject obvious garbage (whitespace, slashes, etc).
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

Ticker = NewType("Ticker", str)


def normalize_ticker(value: str) -> Ticker:
    """Normalize a ticker symbol from any source (LLM output, DB row, user input).

    Raises ValueError on input that can't plausibly be a ticker.
    """
    if not value or not value.strip():
        raise ValueError("ticker cannot be empty")
    upper = value.strip().upper()
    if not _TICKER_RE.match(upper):
        raise ValueError(f"invalid ticker symbol: {value!r}")
    return Ticker(upper)


def TickerPath(ticker: str) -> Ticker:  # noqa: N802 (named like a FastAPI dep, not a function)
    """FastAPI path-param dependency: normalize-or-400."""
    try:
        return normalize_ticker(ticker)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
