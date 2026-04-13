"""FMP API client — one method per data type, every method returns tuple[data, Citation].

All endpoints target FMP's /stable/ API. The legacy v3/v4 endpoints were
deprecated for new subscriptions after 2025-08-31, and the /stable/ API uses
a different calling convention: ticker is passed as `symbol=X` query param
rather than a path segment.

Response caching with TTL:
  - Quote/price data: 5 minutes
  - Fundamental data: 24 hours
  - Options data: 15 minutes (currently unavailable in /stable/, stubbed)
  - Transcripts/filings: 7 days

All calls have a 10-second timeout with 2 retries (exponential backoff).
"""

import time
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.models.citation import Citation

logger = logging.getLogger(__name__)

# ── Cache TTLs in seconds ─────────────────────────────────────────────────────
TTL_QUOTE = 300          # 5 minutes
TTL_FUNDAMENTAL = 86400  # 24 hours
TTL_OPTIONS = 900        # 15 minutes
TTL_TRANSCRIPT = 604800  # 7 days

# ── Retry config ──────────────────────────────────────────────────────────────
MAX_RETRIES = 3
BASE_TIMEOUT = 10.0  # seconds


class FMPClientError(Exception):
    """Raised when FMP API calls fail after all retries."""
    pass


class FMPClient:
    """Async FMP API client with caching and citation generation."""

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.fmp_api_key
        self._base_url = settings.fmp_base_url
        self._cache: dict[str, tuple[Any, float]] = {}  # key -> (data, expiry_ts)
        self._http = httpx.AsyncClient(timeout=BASE_TIMEOUT)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _cache_key(self, endpoint: str, params: dict) -> str:
        raw = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Any | None:
        if key in self._cache:
            data, expiry = self._cache[key]
            if time.time() < expiry:
                return data
            del self._cache[key]
        return None

    def _set_cached(self, key: str, data: Any, ttl: int) -> None:
        self._cache[key] = (data, time.time() + ttl)

    async def _request(
        self, endpoint: str, params: dict | None = None, ttl: int = TTL_FUNDAMENTAL
    ) -> Any:
        """Make a cached, retrying GET request to FMP."""
        params = params or {}
        params["apikey"] = self._api_key
        cache_key = self._cache_key(endpoint, params)

        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("Cache hit: %s", endpoint)
            return cached

        url = f"{self._base_url}/{endpoint}"
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                self._set_cached(cache_key, data, ttl)
                return data
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "FMP %s attempt %d/%d failed: %s. Retrying in %ds...",
                    endpoint, attempt + 1, MAX_RETRIES, e, wait,
                )
                import asyncio
                await asyncio.sleep(wait)

        raise FMPClientError(
            f"FMP {endpoint} failed after {MAX_RETRIES} attempts: {last_error}"
        )

    def _make_citation(
        self, endpoint: str, metric: str, value: Any, params: dict | None = None
    ) -> Citation:
        """Build a Tier 1 citation pointing to the FMP endpoint."""
        query = f"?apikey=***"
        if params:
            for k, v in params.items():
                if k != "apikey":
                    query += f"&{k}={v}"
        return Citation(
            value=value,
            metric=metric,
            source_name=f"FMP /{endpoint}",
            source_url=f"{self._base_url}/{endpoint}{query}",
            tier=1,
        )

    # ── Public API: one method per data type ──────────────────────────────────

    async def get_screener(
        self,
        market_cap_more_than: int | None = None,
        market_cap_lower_than: int | None = None,
        sector: str | None = None,
        industry: str | None = None,
        exchange: str | None = None,
        limit: int = 100,
    ) -> tuple[list[dict], Citation]:
        """FMP stock screener. Returns matching companies."""
        params: dict[str, Any] = {"limit": limit}
        if market_cap_more_than:
            params["marketCapMoreThan"] = market_cap_more_than
        if market_cap_lower_than:
            params["marketCapLowerThan"] = market_cap_lower_than
        if sector:
            params["sector"] = sector
        if industry:
            params["industry"] = industry
        if exchange:
            params["exchange"] = exchange

        data = await self._request("company-screener", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "company-screener",
            "Stock Screener Results",
            f"{len(data)} companies",
            params,
        )
        return data, citation

    async def get_income_statement(
        self, ticker: str, period: str = "annual", limit: int = 4
    ) -> tuple[list[dict], Citation]:
        """Income statement (annual or quarterly)."""
        params = {"symbol": ticker, "period": period, "limit": limit}
        data = await self._request("income-statement", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "income-statement",
            "Income Statement",
            ticker,
            params,
        )
        return data, citation

    async def get_balance_sheet(
        self, ticker: str, period: str = "annual", limit: int = 4
    ) -> tuple[list[dict], Citation]:
        """Balance sheet (annual or quarterly)."""
        params = {"symbol": ticker, "period": period, "limit": limit}
        data = await self._request("balance-sheet-statement", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "balance-sheet-statement",
            "Balance Sheet",
            ticker,
            params,
        )
        return data, citation

    async def get_cash_flow(
        self, ticker: str, period: str = "annual", limit: int = 4
    ) -> tuple[list[dict], Citation]:
        """Cash flow statement (annual or quarterly)."""
        params = {"symbol": ticker, "period": period, "limit": limit}
        data = await self._request("cash-flow-statement", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "cash-flow-statement",
            "Cash Flow Statement",
            ticker,
            params,
        )
        return data, citation

    async def get_dcf(self, ticker: str) -> tuple[dict, Citation]:
        """Discounted cash flow valuation."""
        params = {"symbol": ticker}
        data = await self._request("discounted-cash-flow", params, ttl=TTL_FUNDAMENTAL)
        result = data[0] if isinstance(data, list) and data else data
        citation = self._make_citation(
            "discounted-cash-flow",
            "DCF Valuation",
            result.get("dcf", "N/A") if isinstance(result, dict) else "N/A",
            params,
        )
        return result, citation

    async def get_options_flow(
        self, ticker: str
    ) -> tuple[list[dict], Citation]:
        """Options activity / unusual options flow.

        NOTE: Not currently available in FMP /stable/ — v4/options-activity
        was a legacy endpoint. Returns an empty list so downstream pipeline
        phases degrade gracefully. Revisit if FMP publishes a /stable/ options
        endpoint or you add an alternative provider.
        """
        logger.info("get_options_flow(%s): no /stable/ equivalent, returning empty", ticker)
        citation = Citation(
            value="0 contracts",
            metric="Options Activity (unavailable)",
            source_name="FMP options-activity",
            source_url="https://site.financialmodelingprep.com/developer/docs",
            tier=2,
        )
        return [], citation

    async def get_earnings_transcript(
        self, ticker: str, year: int | None = None, quarter: int | None = None
    ) -> tuple[list[dict], Citation]:
        """Earnings call transcript. Fetches specific quarter or most recent.

        /stable/ uses numeric quarter (1-4), not "Q1" style.
        """
        if year and quarter:
            endpoint = "earning-call-transcript"
            params: dict[str, Any] = {"symbol": ticker, "year": year, "quarter": quarter}
        else:
            endpoint = "earning-call-transcript-latest"
            params = {"symbol": ticker}
            if year:
                params["year"] = year

        data = await self._request(endpoint, params, ttl=TTL_TRANSCRIPT)
        citation = self._make_citation(
            endpoint,
            "Earnings Transcript",
            ticker,
            params,
        )
        return data, citation

    async def get_analyst_estimates(
        self, ticker: str, period: str = "annual", limit: int = 4
    ) -> tuple[list[dict], Citation]:
        """Analyst consensus estimates."""
        params = {"symbol": ticker, "period": period, "limit": limit}
        data = await self._request("analyst-estimates", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "analyst-estimates",
            "Analyst Estimates",
            ticker,
            params,
        )
        return data, citation

    async def get_quote(self, ticker: str) -> tuple[dict, Citation]:
        """Real-time quote (short TTL)."""
        params = {"symbol": ticker}
        data = await self._request("quote", params, ttl=TTL_QUOTE)
        result = data[0] if isinstance(data, list) and data else data
        price = result.get("price", "N/A") if isinstance(result, dict) else "N/A"
        citation = self._make_citation(
            "quote", "Quote", price, params
        )
        return result, citation

    async def get_company_profile(self, ticker: str) -> tuple[dict, Citation]:
        """Company profile (sector, industry, description, etc.)."""
        params = {"symbol": ticker}
        data = await self._request("profile", params, ttl=TTL_FUNDAMENTAL)
        result = data[0] if isinstance(data, list) and data else data
        citation = self._make_citation(
            "profile", "Company Profile", ticker, params
        )
        return result, citation

    async def get_historical_price(
        self, ticker: str, from_date: str, to_date: str
    ) -> tuple[list[dict], Citation]:
        """Daily OHLCV price history (1 year of data).

        GET /stable/historical-price-eod/full?symbol=X&from=YYYY-MM-DD&to=YYYY-MM-DD
        Returns list of {date, open, high, low, close, volume, ...} newest first.
        """
        params = {"symbol": ticker, "from": from_date, "to": to_date}
        data = await self._request("historical-price-eod/full", params, ttl=TTL_FUNDAMENTAL)
        citation = self._make_citation(
            "historical-price-eod/full",
            "Historical Price",
            ticker,
            params,
        )
        return data if isinstance(data, list) else [], citation

    async def get_key_metrics_ttm(self, ticker: str) -> tuple[dict, Citation]:
        """Trailing-twelve-month key metrics — source for PE ratio since it's
        no longer on the /stable/ profile or quote endpoints."""
        params = {"symbol": ticker}
        data = await self._request("key-metrics-ttm", params, ttl=TTL_FUNDAMENTAL)
        result = data[0] if isinstance(data, list) and data else data
        citation = self._make_citation(
            "key-metrics-ttm", "Key Metrics TTM", ticker, params
        )
        return result, citation

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._http.aclose()
