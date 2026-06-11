"""SEC EDGAR client — ticker → CIK, filings index, XBRL company facts.

Endpoints used (all free, no API key required):
- https://www.sec.gov/files/company_tickers.json  (ticker → CIK map, cached)
- https://data.sec.gov/submissions/CIK{cik}.json  (filings history)
- https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json  (all XBRL facts)

SEC fair-use policy: rate limit to 10 req/s, identify with a User-Agent.

Every method returns tuple[data, Citation] to match the FMP/FRED convention.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.models.citation import Citation

logger = logging.getLogger(__name__)

BASE_SEC_URL = "https://www.sec.gov"
BASE_DATA_URL = "https://data.sec.gov"
REQUEST_INTERVAL_SEC = 0.11  # ~9 req/s, under SEC's 10 req/s cap
TIMEOUT_SEC = 15.0
TICKER_MAP_TTL = 86400  # 24h


class EdgarClientError(Exception):
    pass


class EdgarClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._http = httpx.AsyncClient(
            timeout=TIMEOUT_SEC,
            headers={"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"},
        )
        self._ticker_map_cache: tuple[dict[str, str], float] | None = None
        self._last_request_at: float = 0.0
        self._rate_lock = asyncio.Lock()

    async def _throttle(self) -> None:
        """Serialize requests to stay under SEC's 10 req/s limit."""
        async with self._rate_lock:
            now = time.monotonic()
            wait = REQUEST_INTERVAL_SEC - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.monotonic()

    async def _get(self, url: str) -> Any:
        await self._throttle()
        resp = await self._http.get(url)
        if resp.status_code == 404:
            raise EdgarClientError(f"EDGAR 404: {url}")
        resp.raise_for_status()
        return resp.json()

    async def _get_text(self, url: str) -> str:
        await self._throttle()
        resp = await self._http.get(url)
        if resp.status_code == 404:
            raise EdgarClientError(f"EDGAR 404: {url}")
        resp.raise_for_status()
        return resp.text

    async def get_ticker_to_cik(self, ticker: str) -> tuple[str | None, Citation]:
        """Resolve a ticker to a zero-padded 10-digit CIK string.

        Returns (cik, citation). cik is None if the ticker is unknown.
        """
        now = time.time()
        if self._ticker_map_cache and now < self._ticker_map_cache[1]:
            mapping = self._ticker_map_cache[0]
        else:
            data = await self._get(f"{BASE_SEC_URL}/files/company_tickers.json")
            # Shape: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "..."}, ...}
            mapping = {
                v["ticker"].upper(): str(v["cik_str"]).zfill(10)
                for v in data.values()
                if isinstance(v, dict) and "ticker" in v and "cik_str" in v
            }
            self._ticker_map_cache = (mapping, now + TICKER_MAP_TTL)

        cik = mapping.get(ticker.upper())
        citation = Citation(
            value=cik or "unknown",
            metric="ticker_to_cik_lookup",
            source_name="SEC /files/company_tickers.json",
            source_url=f"{BASE_SEC_URL}/files/company_tickers.json",
            tier=1,
        )
        return cik, citation

    async def get_company_facts(self, cik: str) -> tuple[dict, Citation]:
        """Fetch all XBRL facts for a CIK.

        Response shape:
          {"cik": 320193, "entityName": "...",
           "facts": {
               "us-gaap": {"Revenues": {"label": "...", "description": "...",
                                        "units": {"USD": [{"end": "2024-09-30",
                                                           "val": 391035000000,
                                                           "accn": "0000...",
                                                           "fy": 2024, "fp": "FY",
                                                           "form": "10-K",
                                                           "start": "2023-09-24", ...}]}}}}}
        """
        url = f"{BASE_DATA_URL}/api/xbrl/companyfacts/CIK{cik}.json"
        data = await self._get(url)
        # Use the entity name (or CIK fallback) as the citation "value" so
        # the Library pill reads, e.g. "[n] SEC EDGAR · XBRL filings (Oracle Corp)".
        entity_name = (data.get("entityName") if isinstance(data, dict) else None) or f"CIK{cik}"
        citation = Citation(
            value=entity_name,
            metric="XBRL filings",
            source_name="SEC EDGAR",
            source_url=url,
            tier=1,
        )
        return data, citation

    async def get_submissions(self, cik: str) -> tuple[dict, Citation]:
        """Fetch filing history for a CIK (used to list recent forms)."""
        url = f"{BASE_DATA_URL}/submissions/CIK{cik}.json"
        data = await self._get(url)
        citation = Citation(
            value=f"CIK{cik}",
            metric="sec_submissions",
            source_name="SEC /submissions",
            source_url=url,
            tier=1,
        )
        return data, citation

    async def get_filing_index(self, cik: str, accession_number: str) -> tuple[dict, Citation]:
        """Fetch the filing directory index as JSON.

        Response shape:
          {"directory": {"item": [{"name": "aapl-20240928.htm",
                                   "type": "10-K", "size": "...", "last-modified": "..."},
                                  ...]}}

        `cik` can be zero-padded or not; `accession_number` can be dashed or not.
        """
        cik_trimmed = str(int(cik))  # strip leading zeros for Archives URL
        accession_clean = accession_number.replace("-", "")
        url = f"{BASE_SEC_URL}/Archives/edgar/data/{cik_trimmed}/{accession_clean}/index.json"
        data = await self._get(url)
        citation = Citation(
            value=accession_number,
            metric="filing_index",
            source_name="SEC EDGAR Archives",
            source_url=url,
            tier=1,
        )
        return data, citation

    async def fetch_document(self, url: str) -> tuple[str, Citation]:
        """Fetch a raw filing document (HTML, plain text, or inline-XBRL HTML).

        Returns (document_text, citation).
        """
        text = await self._get_text(url)
        citation = Citation(
            value=url.rsplit("/", 1)[-1],
            metric="filing_document",
            source_name="SEC EDGAR",
            source_url=url,
            tier=1,
        )
        return text, citation

    async def close(self) -> None:
        await self._http.aclose()


# ── Concept whitelist for v1 ─────────────────────────────────────────────────
# Keep this tight — we only want facts we'll route into prompts, to avoid
# bloating xbrl_facts with every us-gaap concept a filer reports.

CONCEPT_WHITELIST: dict[str, list[str]] = {
    "us-gaap": [
        # RPO / backlog
        "RevenueRemainingPerformanceObligation",
        "RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPercentage",
        # Debt maturity schedule
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
        # NOTE: `ConcentrationRiskPercentage1` was previously listed here.
        # The SEC `companyfacts` endpoint only returns un-dimensioned parent
        # facts and this concept is always disclosed with axes
        # (`CustomerAxis`, `ProductAxis`), so it never returns data via this
        # API. Structured concentration intel comes from Phase B narrative
        # extraction (`Relationship.unnamed=true` rows). To recover it from
        # XBRL we'd need to parse the original instance documents — out of
        # scope for v1.
        # Credit bonuses
        "WeightedAverageInterestRate",
        "LongTermDebt",
        "LineOfCreditFacilityCurrentBorrowingCapacity",
    ],
    "dei": [
        "EntityCommonStockSharesOutstanding",
    ],
}


def iter_whitelisted_facts(companyfacts: dict) -> list[dict]:
    """Yield flattened fact dicts filtered to the whitelist.

    Each yielded dict has:
        taxonomy, concept, unit, value, period_start, period_end,
        fiscal_year, fiscal_period, form, accession_number
    """
    out: list[dict] = []
    facts = companyfacts.get("facts", {}) or {}
    for taxonomy, concepts in CONCEPT_WHITELIST.items():
        taxonomy_facts = facts.get(taxonomy, {}) or {}
        for concept in concepts:
            concept_data = taxonomy_facts.get(concept)
            if not concept_data:
                continue
            for unit, entries in (concept_data.get("units") or {}).items():
                for e in entries or []:
                    # `end` is always present; `start` only for duration concepts.
                    end = e.get("end")
                    start = e.get("start") or end
                    if not end:
                        continue
                    out.append({
                        "taxonomy": taxonomy,
                        "concept": f"{taxonomy}:{concept}",
                        "unit": unit,
                        "value": e.get("val"),
                        "period_start": start,
                        "period_end": end,
                        "fiscal_year": e.get("fy"),
                        "fiscal_period": e.get("fp"),
                        "form": e.get("form"),
                        "accession_number": e.get("accn"),
                        "filed": e.get("filed"),
                    })
    return out
