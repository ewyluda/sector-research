"""FRED API client — fetches macro economic time series from the St. Louis Fed.

Mirrors the FMP client pattern: async, cached, every method returns tuple[data, Citation].
All series cached 24 hours. 10-second timeout with 3 retries.
"""

import time
import hashlib
import json
import logging
from datetime import date, timedelta
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.models.citation import Citation

logger = logging.getLogger(__name__)

TTL_MACRO = 86400  # 24 hours
MAX_RETRIES = 3
BASE_TIMEOUT = 10.0
BASE_URL = "https://api.stlouisfed.org/fred"

SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "treasury_10y": "DGS10",
    "treasury_2y": "DGS2",
    "yield_curve_spread": "T10Y2Y",
    "cpi": "CPIAUCSL",
    "unemployment": "UNRATE",
    "gdp_growth": "A191RL1Q225SBEA",
    "m2_money_supply": "M2SL",
    "nonfarm_payrolls": "PAYEMS",
}

DAILY_SERIES = {"DGS10", "DGS2", "T10Y2Y"}


class FREDClientError(Exception):
    pass


class FREDClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._api_key = settings.fred_api_key
        self._cache: dict[str, tuple[Any, float]] = {}
        self._http = httpx.AsyncClient(timeout=BASE_TIMEOUT)

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _cache_key(self, series_id: str, params: dict) -> str:
        raw = f"fred:{series_id}:{json.dumps(params, sort_keys=True)}"
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

    async def _request(self, endpoint: str, params: dict) -> Any:
        params["api_key"] = self._api_key
        params["file_type"] = "json"
        cache_key = self._cache_key(endpoint, {k: v for k, v in params.items() if k != "api_key"})

        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug("FRED cache hit: %s", endpoint)
            return cached

        url = f"{BASE_URL}/{endpoint}"
        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                self._set_cached(cache_key, data, TTL_MACRO)
                return data
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning("FRED %s attempt %d/%d failed: %s. Retrying in %ds...", endpoint, attempt + 1, MAX_RETRIES, e, wait)
                import asyncio
                await asyncio.sleep(wait)

        raise FREDClientError(f"FRED {endpoint} failed after {MAX_RETRIES} attempts: {last_error}")

    def _make_citation(self, series_id: str, series_name: str) -> Citation:
        return Citation(
            value=series_id,
            metric=series_name,
            source_name=f"FRED /{series_id}",
            source_url=f"https://fred.stlouisfed.org/series/{series_id}",
            tier=1,
        )

    @staticmethod
    def _downsample_weekly(observations: list[dict]) -> list[dict]:
        weekly: dict[str, dict] = {}
        for obs in observations:
            d = obs["date"]
            try:
                dt = date.fromisoformat(d)
                week_key = f"{dt.isocalendar()[0]}-W{dt.isocalendar()[1]:02d}"
                weekly[week_key] = obs
            except ValueError:
                continue
        return list(weekly.values())

    @staticmethod
    def _parse_observations(raw: list[dict], downsample: bool = False) -> list[dict]:
        points = []
        for obs in raw:
            val_str = obs.get("value", ".")
            if val_str == "." or val_str is None:
                continue
            try:
                points.append({"date": obs["date"], "value": float(val_str)})
            except (ValueError, KeyError):
                continue
        if downsample:
            points = FREDClient._downsample_weekly(points)
        return points

    async def get_series(self, series_id: str, observation_start: str | None = None, observation_end: str | None = None) -> tuple[list[dict], Citation]:
        if not self._api_key:
            return [], self._make_citation(series_id, series_id)

        today = date.today()
        start = observation_start or (today - timedelta(days=730)).isoformat()
        end = observation_end or today.isoformat()

        params = {"series_id": series_id, "observation_start": start, "observation_end": end}
        data = await self._request("series/observations", params)
        observations = data.get("observations", [])
        downsample = series_id in DAILY_SERIES
        parsed = self._parse_observations(observations, downsample=downsample)

        name = next((k for k, v in SERIES.items() if v == series_id), series_id)
        citation = self._make_citation(series_id, name)
        return parsed, citation

    async def get_all_macro(self) -> tuple[dict[str, list[dict]], list[Citation]]:
        import asyncio
        tasks = {name: self.get_series(sid) for name, sid in SERIES.items()}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        indicators: dict[str, list[dict]] = {}
        citations: list[Citation] = []

        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("FRED %s failed: %s", name, result)
                indicators[name] = []
            else:
                data, citation = result
                indicators[name] = data
                citations.append(citation)

        return indicators, citations
