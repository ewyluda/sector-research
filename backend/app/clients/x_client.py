"""X (Twitter) API v2 client for theme signal computation.

Computes three signals per ticker per theme:
  - velocity:   7d vs 30d mention ratio (accelerating / stable / decelerating)
  - narrative:  Claude Haiku summary of post clusters
  - discovery:  mention prominence within theme; ×1.5 boost for non-seed tickers

Rate limit: handled via token bucket.
Schedule:   Daily at 2 AM local — NOT on-demand.
Staleness:  Signals older than 36h are flagged is_stale=True.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from backend.app.config import get_settings
from backend.app.models.citation import Citation

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
STALE_THRESHOLD_HOURS = 36
VELOCITY_SURPRISE_MULTIPLIER = 2.0   # ratio spike that triggers SurpriseAlert
DISCOVERY_BOOST = 1.5                # applied to non-seed tickers

# X API v2 rate limit: ~15 requests / 15 min on Basic tier
# Token bucket: 1 token per 2 seconds = ~30 req/min (conservative)
TOKEN_BUCKET_RATE = 0.5   # tokens per second
TOKEN_BUCKET_MAX = 10     # max burst


class XRateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, rate: float = TOKEN_BUCKET_RATE, capacity: float = TOKEN_BUCKET_MAX):
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return

            wait = (1 - self._tokens) / self._rate
            logger.debug("X rate limiter: waiting %.2fs", wait)
            await asyncio.sleep(wait)


class XClientError(Exception):
    pass


def _x_error(e: httpx.HTTPStatusError) -> XClientError:
    """Rate-limit (429) and out-of-credits (402) responses raise instead of
    returning [] — an empty list used to be stored as a real "0 mentions,
    decelerating" signal, overwriting the last good value."""
    code = e.response.status_code
    if code == 429:
        return XClientError("X API rate limit (429)")
    if code == 402:
        return XClientError("X API credits depleted (402)")
    return XClientError(f"X API error: {e}")


VELOCITY_RECENT_DAYS = 3
VELOCITY_BASELINE_DAYS = 4


def velocity_from_daily_counts(daily: list[int]) -> dict:
    """Pure: velocity signal from daily counts (oldest first, last bucket partial)."""
    complete = daily[:-1] if len(daily) > 1 else daily
    recent = complete[-VELOCITY_RECENT_DAYS:]
    baseline = complete[-(VELOCITY_RECENT_DAYS + VELOCITY_BASELINE_DAYS):-VELOCITY_RECENT_DAYS]
    recent_avg = sum(recent) / len(recent) if recent else 0.0
    baseline_avg = sum(baseline) / len(baseline) if baseline else 0.0
    ratio = round(recent_avg / baseline_avg, 3) if baseline_avg > 0 else None
    if ratio is None:
        direction = "accelerating" if recent_avg > 0 else "stable"
    elif ratio > 1.3:
        direction = "accelerating"
    elif ratio < 0.7:
        direction = "decelerating"
    else:
        direction = "stable"
    return {
        "ratio": ratio,
        "count_7d": sum(complete[-7:]),
        "recent_daily_avg": round(recent_avg, 1),
        "baseline_daily_avg": round(baseline_avg, 1),
        "daily_counts": daily,
        "direction": direction,
    }


class XClient:
    """Async X API v2 client with rate limiting and signal computation."""

    def __init__(self) -> None:
        settings = get_settings()
        self._bearer = settings.x_bearer_token
        self._base_url = settings.x_base_url
        self._limiter = XRateLimiter()
        self._http = httpx.AsyncClient(
            timeout=15.0,
            headers={"Authorization": f"Bearer {self._bearer}"},
        )

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _search_recent(
        self,
        query: str,
        max_results: int = 100,
        start_time: datetime | None = None,
    ) -> list[dict]:
        """Search recent tweets (up to 7 days back on Basic tier)."""
        await self._limiter.acquire()

        params: dict[str, Any] = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics,author_id,text",
        }
        if start_time:
            params["start_time"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            resp = await self._http.get(
                f"{self._base_url}/tweets/search/recent", params=params
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except httpx.HTTPStatusError as e:
            raise _x_error(e) from e
        except Exception as e:
            raise XClientError(f"X request failed: {e}") from e

    async def _counts_recent(self, query: str) -> list[int]:
        """Daily post counts for the last 7 days, oldest first (the final
        bucket is today, partial). One request, no pagination, no 100 cap."""
        await self._limiter.acquire()
        try:
            resp = await self._http.get(
                f"{self._base_url}/tweets/counts/recent",
                params={"query": query, "granularity": "day"},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _x_error(e) from e
        except Exception as e:
            raise XClientError(f"X request failed: {e}") from e
        return [int(b.get("tweet_count", 0)) for b in resp.json().get("data", [])]

    def _build_ticker_query(self, ticker: str, company_name: str = "") -> str:
        """Build an X search query for a ticker."""
        parts = [f"${ticker}"]
        if company_name:
            # Strip common suffixes for cleaner search
            clean = (
                company_name.replace(" Inc.", "").replace(" Corp.", "")
                .replace(" Holdings", "").replace(" Ltd.", "").strip()
            )
            if clean and clean.lower() != ticker.lower():
                parts.append(f'"{clean}"')
        return f"({' OR '.join(parts)}) -is:retweet lang:en"

    def _build_theme_query(self, x_search_terms: list[str]) -> str:
        """Build an X search query for a full theme.

        Each term becomes one alternative in an OR list. Themes can mix:
        - bare keywords (`SMR`)              → emitted as-is
        - plain phrases (`AI capex`)         → wrapped in quotes
        - hashtags (`#DataCenterPower`)      → emitted as-is
        - cashtags (`$BE`)                   → emitted as-is
        - pre-quoted phrases (`"Grid Cliff"`)→ emitted as-is, no double-quote
        - rich expressions (`A OR "B"`)      → wrapped in `()` for precedence

        Naive double-quoting (the previous implementation) breaks themes
        that intentionally use X-search syntax — see Power & Energy theme
        which mixes quoted phrases, cashtags, and embedded OR operators.
        """
        if not x_search_terms:
            return ""

        parts: list[str] = []
        for raw in x_search_terms[:10]:
            t = (raw or "").strip()
            if not t:
                continue
            has_quote = '"' in t
            has_or = " OR " in f" {t.upper()} "
            starts_special = t[0] in ("#", "$", "(")
            if has_or:
                parts.append(f"({t})")
            elif has_quote or starts_special:
                parts.append(t)
            elif " " in t:
                parts.append(f'"{t}"')
            else:
                parts.append(t)

        if not parts:
            return ""
        return f"({' OR '.join(parts)}) -is:retweet lang:en"

    # ── Public signal computation ─────────────────────────────────────────────

    async def compute_velocity_signal(
        self,
        ticker: str,
        company_name: str = "",
    ) -> tuple[dict, Citation]:
        """Mention velocity from X's daily post counts.

        ratio = mean daily posts over the last 3 complete days / mean over the
        4 complete days before them (>1.3 accelerating, <0.7 decelerating).

        Replaces a computation that could only ever return 1.0: it scaled the
        7-day count by 4 and divided it back out, made a second identical
        (paid) search whose result it discarded, and capped counts at the
        100 posts of one search page.
        """
        query = self._build_ticker_query(ticker, company_name)
        daily = await self._counts_recent(query)
        signal_data = velocity_from_daily_counts(daily)

        citation = Citation(
            value=f"{signal_data['direction']} ({signal_data['count_7d']} posts/7d)",
            metric="X Velocity Signal",
            source_name="X API v2 /tweets/counts/recent",
            source_url=f"https://api.twitter.com/2/tweets/counts/recent?query={query[:60]}",
            tier=2,
        )
        return signal_data, citation

    async def compute_narrative_signal(
        self,
        ticker: str,
        company_name: str = "",
    ) -> tuple[dict, Citation]:
        """
        Fetch recent posts and return raw text for Haiku summarization.

        Returns:
          {
            "post_texts": list[str],   # up to 20 representative posts
            "post_count": int,
            "summary": None            # filled by Haiku in the pipeline
          }
        """
        now = datetime.now(timezone.utc)
        query = self._build_ticker_query(ticker, company_name)

        posts = await self._search_recent(
            query, max_results=50, start_time=now - timedelta(days=7)
        )

        # Sort by engagement (like_count + retweet_count) and take top 20
        def engagement(p: dict) -> int:
            m = p.get("public_metrics", {})
            return m.get("like_count", 0) + m.get("retweet_count", 0) * 3

        top_posts = sorted(posts, key=engagement, reverse=True)[:20]
        post_texts = [p.get("text", "") for p in top_posts]

        signal_data = {
            "post_texts": post_texts,
            "post_count": len(posts),
            "summary": None,  # filled by Claude Haiku in discovery service
        }

        citation = Citation(
            value=f"{len(posts)} posts analyzed",
            metric="X Narrative Signal",
            source_name="X API v2 /tweets/search/recent",
            source_url=f"https://api.twitter.com/2/tweets/search/recent?query={query[:60]}",
            tier=2,
        )

        return signal_data, citation

    async def compute_discovery_score(
        self,
        ticker: str,
        theme_x_search_terms: list[str],
        seed_tickers: list[str],
        company_name: str = "",
    ) -> tuple[dict, Citation]:
        """
        Discovery score = (ticker mentions within theme search / total theme mentions)
        × 1.5 if ticker NOT in seed list, × 1.0 if it is.

        Higher score = more prominent in theme discussion but less known to you.
        """
        now = datetime.now(timezone.utc)
        theme_query = self._build_theme_query(theme_x_search_terms)
        ticker_query = self._build_ticker_query(ticker, company_name)

        if not theme_query:
            signal_data = {"score": 0.0, "is_seed": ticker in seed_tickers, "reason": "no theme terms configured"}
            citation = Citation(
                value=0.0,
                metric="X Discovery Score",
                source_name="X API v2",
                source_url="https://api.twitter.com/2/tweets/search/recent",
                tier=2,
            )
            return signal_data, citation

        # Combined query: theme context + ticker mention
        combined_query = f"({theme_query}) ({ticker_query})"

        # Fetch co-mentions (ticker within theme context)
        co_mentions = await self._search_recent(
            combined_query, max_results=100, start_time=now - timedelta(days=7)
        )

        # Fetch total theme mentions
        theme_mentions = await self._search_recent(
            theme_query, max_results=100, start_time=now - timedelta(days=7)
        )

        total_theme = max(len(theme_mentions), 1)
        ticker_in_theme = len(co_mentions)
        is_seed = ticker.upper() in [s.upper() for s in seed_tickers]

        raw_score = ticker_in_theme / total_theme
        boost = 1.5 if not is_seed else 1.0
        final_score = round(raw_score * boost, 4)

        signal_data = {
            "score": final_score,
            "raw_score": round(raw_score, 4),
            "boost_applied": boost,
            "co_mentions_7d": ticker_in_theme,
            "total_theme_mentions_7d": total_theme,
            "is_seed": is_seed,
        }

        citation = Citation(
            value=final_score,
            metric="X Discovery Score",
            source_name="X API v2 /tweets/search/recent",
            source_url=f"https://api.twitter.com/2/tweets/search/recent?query={combined_query[:60]}",
            tier=2,
        )

        return signal_data, citation

    async def check_surprise_signal(
        self,
        ticker: str,
        prior_velocity_ratio: float,
        company_name: str = "",
    ) -> tuple[bool, float]:
        """
        Returns (is_surprise, current_ratio).
        A surprise fires when current_ratio > prior_ratio × VELOCITY_SURPRISE_MULTIPLIER.
        Only called by the scheduler after a fresh velocity computation.
        """
        velocity_data, _ = await self.compute_velocity_signal(ticker, company_name)
        current_ratio = velocity_data["ratio"]
        is_surprise = current_ratio > prior_velocity_ratio * VELOCITY_SURPRISE_MULTIPLIER
        return is_surprise, current_ratio

    async def close(self) -> None:
        await self._http.aclose()
