"""Discovery Engine service.

Orchestrates two parallel passes when a theme is opened:
  1. FMP Screener Pass — structural companies matching theme criteria
  2. X Signal Pass     — velocity, narrative, discovery score per ticker

Produces a ranked list of CompanySignalCard objects with:
  - Combined signal score (configurable weights per theme)
  - Cold-start fallback when X signal is unavailable
  - FMP + X Signal vs FMP Only source badge
  - Staleness awareness
"""

import asyncio
import logging
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.clients.x_client import XClient, STALE_THRESHOLD_HOURS
from backend.app.models.citation import Citation
from backend.app.models.signal import Signal
from backend.app.models.theme import Theme
from backend.app.models.surprise_alert import SurpriseAlert
from backend.app.services.congress_signal import CONGRESS_STALE_HOURS
from backend.app.services.graph_centrality import CENTRALITY_STALE_HOURS
from backend.app.services.insider_signal import INSIDER_STALE_HOURS

logger = logging.getLogger(__name__)


# ── Output types ──────────────────────────────────────────────────────────────

@dataclass
class FMPSnapshot:
    """4 key FMP metrics for the company card."""
    roic: float | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None
    pe_ratio: float | None = None
    market_cap: float | None = None


@dataclass
class XSignalSnapshot:
    direction: str = "unknown"      # accelerating | stable | decelerating | unknown
    ratio: float | None = None
    narrative_summary: str | None = None
    discovery_score: float = 0.0
    is_stale: bool = False


@dataclass
class InsiderSnapshot:
    """Cached Form 4 signal as applied to this card. modifier is 0 when the
    signal is stale or absent (i.e., what was actually applied).

    NOTE: is_stale means "signal present but no modifier was applied" — it is
    True both for genuinely stale (>48h) signals AND for fresh signals whose
    modifier is legitimately 0 (no notable insider activity). Don't read it
    as a pure age check; the only current consumer is the modifier!=0 chip,
    which never reads it. Rename before giving it a second consumer."""
    modifier: int = 0
    buy_count: int = 0
    sell_count: int = 0
    cluster_buy: bool = False
    net_value: float | None = None
    is_stale: bool = True


@dataclass
class CongressSnapshot:
    """Cached congressional-trading signal as applied to this card.
    Same shape and is_stale overloading as InsiderSnapshot (see its NOTE)."""
    modifier: int = 0
    buy_count: int = 0
    sell_count: int = 0
    cluster_buy: bool = False
    net_value: float | None = None
    is_stale: bool = True


@dataclass
class CentralitySnapshot:
    """Cached graph-centrality signal as applied to this card.
    Same shape conventions and is_stale overloading as InsiderSnapshot (see its NOTE)."""
    modifier: int = 0
    betweenness: float | None = None
    eigenvector: float | None = None
    degree: int = 0
    is_hub: bool = False
    is_broker: bool = False
    is_stale: bool = True


def _wire_value(value: Any) -> Any:
    """Recursively project a card value to its JSON-safe wire form.

    `Citation` is special-cased (its `value` is coerced to str to match the
    frontend `Citation` type). Nested snapshot dataclasses recurse field by
    field, so the wire shape tracks the dataclass automatically — that is what
    keeps a newly-added snapshot from shipping invisible.
    """
    if isinstance(value, Citation):
        return {
            "metric": value.metric,
            "source_name": value.source_name,
            "source_url": value.source_url,
            "tier": value.tier,
            "value": str(value.value),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _wire_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, list):
        return [_wire_value(v) for v in value]
    return value


@dataclass
class CompanySignalCard:
    """The complete per-company object rendered in the Theme Detail view."""
    ticker: str
    company_name: str
    market_cap: float | None
    sector: str | None
    industry: str | None

    fmp: FMPSnapshot = field(default_factory=FMPSnapshot)
    x_signal: XSignalSnapshot = field(default_factory=XSignalSnapshot)
    insider: InsiderSnapshot = field(default_factory=InsiderSnapshot)
    congress: CongressSnapshot = field(default_factory=CongressSnapshot)
    centrality: CentralitySnapshot = field(default_factory=CentralitySnapshot)

    combined_score: float = 0.0
    fundamental_quality_score: float = 0.0

    # "FMP + X Signal" | "FMP Only (X signal pending)"
    signal_source_badge: str = "FMP Only (X signal pending)"

    # True if this ticker just crossed the surprise signal threshold
    is_surprise: bool = False

    citations: list[Citation] = field(default_factory=list)

    # Was this ticker in the theme's seed list?
    is_seed: bool = False

    # If previously researched, latest pipeline result
    last_run_id: str | None = None
    last_conviction_score: int | None = None
    last_thesis_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe wire shape, derived from the dataclass fields.

        A new field — a scalar or a whole new nested snapshot — reaches the
        frontend automatically; you opt one *out* by excluding it here. This
        inverts the old hand-enumerated serializer that silently dropped any
        unmapped field (both the congress and centrality chips shipped
        invisible that way). `api/discovery._card_to_dict` is a thin shim over
        this. New frontend type lives in `frontend/lib/api/themes.ts`.
        """
        return {f.name: _wire_value(getattr(self, f.name)) for f in fields(self)}


# ── Fundamental quality scorer ────────────────────────────────────────────────

def compute_fundamental_quality_score(
    roic: float | None,
    gross_margin: float | None,
    revenue_growth: float | None,
    pe_ratio: float | None,
) -> float:
    """
    0–100 score from FMP fundamentals alone.
    Used as fallback when X signal is unavailable, and as 40% of combined score.

    Scoring:
      ROIC (40 pts):         >20% = 40, >15% = 32, >10% = 24, >5% = 16, else 0
      Gross Margin (30 pts): >60% = 30, >40% = 24, >25% = 18, >15% = 10, else 0
      Revenue Growth (30 pts): >30% = 30, >20% = 24, >10% = 18, >0% = 10, else 0
    """
    score = 0.0

    if roic is not None:
        if roic > 0.20:
            score += 40
        elif roic > 0.15:
            score += 32
        elif roic > 0.10:
            score += 24
        elif roic > 0.05:
            score += 16

    if gross_margin is not None:
        if gross_margin > 0.60:
            score += 30
        elif gross_margin > 0.40:
            score += 24
        elif gross_margin > 0.25:
            score += 18
        elif gross_margin > 0.15:
            score += 10

    if revenue_growth is not None:
        if revenue_growth > 0.30:
            score += 30
        elif revenue_growth > 0.20:
            score += 24
        elif revenue_growth > 0.10:
            score += 18
        elif revenue_growth > 0.0:
            score += 10

    return round(score, 1)


def compute_velocity_score(direction: str, ratio: float | None) -> float:
    """Convert velocity direction to a 0–100 score for combined weighting."""
    if direction == "accelerating":
        return min(100.0, 60.0 + (ratio or 1.0) * 10)
    elif direction == "stable":
        return 50.0
    elif direction == "decelerating":
        return max(0.0, 50.0 - abs(1.0 - (ratio or 1.0)) * 20)
    return 0.0  # unknown


def compute_combined_score(
    fundamental_score: float,
    velocity_direction: str,
    velocity_ratio: float | None,
    discovery_score: float,
    weights: dict,
    has_x_signal: bool,
) -> float:
    """
    Weighted combination of fundamental quality, X velocity, and discovery.

    When X signal is unavailable:
      - fundamental weight bumped to 0.80
      - discovery_score (seed boost) gets 0.20
    """
    if not has_x_signal:
        return round(fundamental_score * 0.80 + discovery_score * 100 * 0.20, 1)

    w_vel = weights.get("x_velocity", 0.40)
    w_fund = weights.get("fundamental_quality", 0.40)
    w_disc = weights.get("discovery", 0.20)

    velocity_score = compute_velocity_score(velocity_direction, velocity_ratio)
    disc_normalized = min(discovery_score * 1000, 100)  # normalize 0–0.1 range to 0–100

    return round(
        velocity_score * w_vel
        + fundamental_score * w_fund
        + disc_normalized * w_disc,
        1,
    )


def _apply_cached_modifier(
    base_score: float, signal_data: dict, now: datetime, stale_hours: int
) -> tuple[float, int]:
    """Clamped combined-score adjustment from a cached bounded-modifier
    signal (insider / congress). Stale or absent → unchanged.
    Returns (adjusted_score, applied_modifier)."""
    if not signal_data:
        return base_score, 0
    raw = signal_data.get("computed_at")
    try:
        computed = datetime.fromisoformat(raw) if raw else None
    except (ValueError, TypeError):
        computed = None
    if computed is None or computed < now - timedelta(hours=stale_hours):
        return base_score, 0
    modifier = int(signal_data.get("modifier", 0) or 0)
    if modifier == 0:
        return base_score, 0
    return round(min(100.0, max(0.0, base_score + modifier)), 1), modifier


def apply_insider_modifier(
    base_score: float, insider_data: dict, now: datetime
) -> tuple[float, int]:
    """Clamped combined-score adjustment from the cached insider signal.

    Bounded modifier, NOT a 4th weight (spec): insider activity is sparse —
    a weight would multiply zeros most days and force a rework of per-theme
    weights and the cold-start collapse. Stale (>48h) or absent → unchanged.
    Returns (adjusted_score, applied_modifier).
    """
    return _apply_cached_modifier(base_score, insider_data, now, INSIDER_STALE_HOURS)


def apply_congress_modifier(
    base_score: float, congress_data: dict, now: datetime
) -> tuple[float, int]:
    """Same bounded-modifier semantics over the signal_type='congress'
    cache (third insider-adjacent signal — same rationale as above)."""
    return _apply_cached_modifier(base_score, congress_data, now, CONGRESS_STALE_HOURS)


def apply_centrality_modifier(
    base_score: float, centrality_data: dict, now: datetime
) -> tuple[float, int]:
    """Graph-derived bounded modifier from the signal_type='centrality' cache.

    Hub +3 / Broker +2 — larger wins, set upstream in graph_centrality.
    Deliberately NOT a 4th combined-score weight (same rationale as
    insider/congress): centrality is sparse and slow-moving; a weight would
    multiply zeros and force per-theme weight rework. Stale (>48h) or absent
    → unchanged. Returns (adjusted_score, applied_modifier).
    """
    return _apply_cached_modifier(base_score, centrality_data, now, CENTRALITY_STALE_HOURS)


# ── FMP data extraction helpers ───────────────────────────────────────────────

def _extract_roic(balance: list[dict], cashflow: list[dict]) -> float | None:
    """ROIC = NOPAT / Invested Capital. Approximated from available FMP fields."""
    try:
        if not balance or not cashflow:
            return None
        b = balance[0]
        cf = cashflow[0]
        invested_capital = (
            b.get("totalEquity", 0) + b.get("longTermDebt", 0)
        )
        nopat = cf.get("operatingCashFlow", 0)
        if not invested_capital:
            return None
        return round(nopat / invested_capital, 4)
    except Exception:
        logger.exception("_extract_roic failed on malformed FMP data")
        return None


def _extract_gross_margin(income: list[dict]) -> float | None:
    try:
        if not income:
            return None
        i = income[0]
        revenue = i.get("revenue", 0)
        gross_profit = i.get("grossProfit", 0)
        if not revenue:
            return None
        return round(gross_profit / revenue, 4)
    except Exception:
        logger.exception("_extract_gross_margin failed on malformed FMP data")
        return None


def _extract_revenue_growth(income: list[dict]) -> float | None:
    """YoY revenue growth from most recent two periods."""
    try:
        if len(income) < 2:
            return None
        curr = income[0].get("revenue", 0)
        prev = income[1].get("revenue", 0)
        if not prev:
            return None
        return round((curr - prev) / prev, 4)
    except Exception:
        logger.exception("_extract_revenue_growth failed on malformed FMP data")
        return None


# ── Discovery Engine ─────────────────────────────────────────────────────────

class DiscoveryEngine:
    """
    Orchestrates the two-pass discovery process for a theme.
    Designed to be called from the API layer via FastAPI dependency injection.
    """

    def __init__(self, fmp: FMPClient, x_client: XClient) -> None:
        self._fmp = fmp
        self._x = x_client

    async def run(
        self,
        theme: Theme,
        db: AsyncSession,
    ) -> list[CompanySignalCard]:
        """
        Run both discovery passes in parallel and return ranked company cards.

        1. FMP Screener Pass   → structural companies
        2. X Signal Pass       → cached signals from DB (scheduler writes these)

        Both passes run concurrently. Results are merged by ticker and ranked.
        """
        logger.info("Discovery run for theme: %s", theme.name)

        # Run FMP screener and load cached X signals concurrently
        fmp_task = asyncio.create_task(self._fmp_pass(theme))
        x_task = asyncio.create_task(self._load_cached_signals(theme, db))

        fmp_results, cached_signals = await asyncio.gather(
            fmp_task, x_task, return_exceptions=True
        )

        if isinstance(fmp_results, Exception):
            logger.error("FMP screener pass failed: %s", fmp_results)
            fmp_results = []

        if isinstance(cached_signals, Exception):
            logger.error("X signal load failed: %s", cached_signals)
            cached_signals = {}

        # Merge into CompanySignalCards
        cards = await self._merge_results(
            theme=theme,
            fmp_results=fmp_results,
            cached_signals=cached_signals,
            db=db,
        )

        # Sort by combined score descending
        cards.sort(key=lambda c: c.combined_score, reverse=True)

        logger.info("Discovery complete: %d companies for theme %s", len(cards), theme.name)
        return cards

    async def _fmp_pass(self, theme: Theme) -> list[dict]:
        """
        Run FMP screener + fetch income/balance/cashflow for each result.
        Returns raw FMP data dicts enriched with fundamentals.

        If the theme has no meaningful screener filters, the screener is
        skipped entirely — otherwise FMP returns a generic top-N universe
        (LLY, V, NFLX, etc.) that has nothing to do with the theme. Users can
        broaden their universe by adding sector / market-cap / industry filters
        to their theme's screener_criteria.
        """
        criteria = theme.screener_criteria or {}

        # A theme with only `limit` (or nothing) set is treated as "seed-only".
        # The real FMP filter keys are market_cap_*, sector, industry, exchange.
        filter_keys = (
            "market_cap_more_than",
            "market_cap_lower_than",
            "sector",
            "industry",
            "exchange",
        )
        has_real_filter = any(criteria.get(k) for k in filter_keys)

        screener_results: list[dict] = []
        if has_real_filter:
            screener_results, _ = await self._fmp.get_screener(
                market_cap_more_than=criteria.get("market_cap_more_than"),
                market_cap_lower_than=criteria.get("market_cap_lower_than"),
                sector=criteria.get("sector"),
                industry=criteria.get("industry"),
                exchange=criteria.get("exchange"),
                limit=criteria.get("limit", 50),
            )
        else:
            logger.info(
                "Theme %s has no screener filters — using seed tickers only",
                theme.name,
            )

        # Always include seed tickers
        seed_tickers = theme.seed_tickers if isinstance(theme.seed_tickers, list) else []
        screener_tickers = {r.get("symbol", "").upper() for r in screener_results}
        missing_seeds = [t for t in seed_tickers if t.upper() not in screener_tickers]

        enriched: list[dict] = []

        # Fetch fundamentals for all tickers concurrently (batched to avoid hammering FMP)
        all_tickers = list(screener_tickers) + missing_seeds
        batch_size = 10

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i : i + batch_size]
            tasks = [self._fetch_company_fundamentals(t) for t in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for ticker, result in zip(batch, results):
                if isinstance(result, Exception):
                    logger.warning("Fundamentals fetch failed for %s: %s", ticker, result)
                    # Include with minimal data from screener
                    screener_row = next(
                        (r for r in screener_results if r.get("symbol", "").upper() == ticker.upper()),
                        {"symbol": ticker, "companyName": ticker},
                    )
                    enriched.append({"ticker": ticker, "screener": screener_row, "fundamentals": None})
                else:
                    enriched.append(result)

        return enriched

    async def _fetch_company_fundamentals(self, ticker: str) -> dict:
        """Fetch income, balance sheet, and cash flow for a single ticker."""
        income_task = self._fmp.get_income_statement(ticker, period="annual", limit=4)
        balance_task = self._fmp.get_balance_sheet(ticker, period="annual", limit=2)
        cashflow_task = self._fmp.get_cash_flow(ticker, period="annual", limit=2)
        profile_task = self._fmp.get_company_profile(ticker)

        (income, inc_cit), (balance, bal_cit), (cashflow, cf_cit), (profile, prof_cit) = (
            await asyncio.gather(income_task, balance_task, cashflow_task, profile_task)
        )

        return {
            "ticker": ticker,
            "profile": profile,
            "income": income,
            "balance": balance,
            "cashflow": cashflow,
            "citations": [inc_cit, bal_cit, cf_cit, prof_cit],
        }

    async def _load_cached_signals(
        self, theme: Theme, db: AsyncSession
    ) -> dict[str, dict]:
        """
        Load cached signals from the signals table.
        Returns dict keyed by ticker: {"velocity": {...}, "narrative": {...}, "discovery": {...}}
        """
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(hours=STALE_THRESHOLD_HOURS)

        result = await db.execute(
            select(Signal).where(
                Signal.theme_id == theme.id,
            )
        )
        signals = result.scalars().all()

        by_ticker: dict[str, dict] = {}
        for sig in signals:
            if sig.ticker not in by_ticker:
                by_ticker[sig.ticker] = {}
            is_stale = sig.computed_at < stale_cutoff
            by_ticker[sig.ticker][sig.signal_type] = {
                **sig.value,
                "is_stale": is_stale,
                "computed_at": sig.computed_at.isoformat(),
            }

        return by_ticker

    async def _merge_results(
        self,
        theme: Theme,
        fmp_results: list[dict],
        cached_signals: dict[str, dict],
        db: AsyncSession,
    ) -> list[CompanySignalCard]:
        """Merge FMP fundamentals with cached X signals into CompanySignalCards."""
        seed_tickers = theme.seed_tickers if isinstance(theme.seed_tickers, list) else []
        seed_upper = {s.upper() for s in seed_tickers}
        weights = theme.signal_weights or {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}

        # Batch SurpriseAlert lookup: one IN() query for all tickers instead of N+1.
        all_tickers = [item.get("ticker", "").upper() for item in fmp_results if item.get("ticker")]
        surprise_result = await db.execute(
            select(SurpriseAlert.ticker).where(
                SurpriseAlert.theme_id == theme.id,
                SurpriseAlert.ticker.in_(all_tickers),
                SurpriseAlert.acknowledged_at.is_(None),
            )
        )
        surprise_tickers: set[str] = set(surprise_result.scalars().all())

        cards: list[CompanySignalCard] = []

        for item in fmp_results:
            ticker = item.get("ticker", "").upper()
            if not ticker:
                continue

            profile = item.get("profile") or {}
            income = item.get("income") or []
            balance = item.get("balance") or []
            cashflow = item.get("cashflow") or []
            item_citations = item.get("citations") or []

            # Build FMP snapshot
            fmp_snap = FMPSnapshot(
                roic=_extract_roic(balance, cashflow),
                gross_margin=_extract_gross_margin(income),
                revenue_growth_yoy=_extract_revenue_growth(income),
                # /stable/ profile no longer includes PE; compute from quote or
                # fetch via key-metrics-ttm if it becomes load-bearing.
                pe_ratio=None,
                market_cap=profile.get("marketCap") if isinstance(profile, dict) else None,
            )

            fund_score = compute_fundamental_quality_score(
                fmp_snap.roic,
                fmp_snap.gross_margin,
                fmp_snap.revenue_growth_yoy,
                fmp_snap.pe_ratio,
            )

            # Build X signal snapshot from cache
            ticker_signals = cached_signals.get(ticker, {})
            velocity_data = ticker_signals.get("velocity", {})
            narrative_data = ticker_signals.get("narrative", {})
            discovery_data = ticker_signals.get("discovery", {})

            has_x_signal = bool(velocity_data)
            is_stale = velocity_data.get("is_stale", False)

            x_snap = XSignalSnapshot(
                direction=velocity_data.get("direction", "unknown"),
                ratio=velocity_data.get("ratio"),
                narrative_summary=narrative_data.get("summary"),
                discovery_score=discovery_data.get("score", 0.0),
                is_stale=is_stale,
            )

            combined = compute_combined_score(
                fundamental_score=fund_score,
                velocity_direction=x_snap.direction,
                velocity_ratio=x_snap.ratio,
                discovery_score=x_snap.discovery_score,
                weights=weights,
                has_x_signal=has_x_signal and not is_stale,
            )

            insider_data = ticker_signals.get("insider", {})
            combined, applied_modifier = apply_insider_modifier(
                combined, insider_data, datetime.now(timezone.utc)
            )
            insider_snap = InsiderSnapshot(
                modifier=applied_modifier,
                buy_count=int(insider_data.get("buy_count", 0) or 0),
                sell_count=int(insider_data.get("sell_count", 0) or 0),
                cluster_buy=bool(insider_data.get("cluster_buy", False)),
                net_value=insider_data.get("net_value"),
                is_stale=applied_modifier == 0 and bool(insider_data),
            )

            congress_data = ticker_signals.get("congress", {})
            combined, congress_modifier = apply_congress_modifier(
                combined, congress_data, datetime.now(timezone.utc)
            )
            congress_snap = CongressSnapshot(
                modifier=congress_modifier,
                buy_count=int(congress_data.get("buy_count", 0) or 0),
                sell_count=int(congress_data.get("sell_count", 0) or 0),
                cluster_buy=bool(congress_data.get("cluster_buy", False)),
                net_value=congress_data.get("net_value"),
                is_stale=congress_modifier == 0 and bool(congress_data),
            )

            centrality_data = ticker_signals.get("centrality", {})
            combined, centrality_modifier = apply_centrality_modifier(
                combined, centrality_data, datetime.now(timezone.utc)
            )
            centrality_snap = CentralitySnapshot(
                modifier=centrality_modifier,
                betweenness=centrality_data.get("betweenness"),
                eigenvector=centrality_data.get("eigenvector"),
                degree=int(centrality_data.get("degree", 0) or 0),
                is_hub=bool(centrality_data.get("is_hub", False)),
                is_broker=bool(centrality_data.get("is_broker", False)),
                is_stale=centrality_modifier == 0 and bool(centrality_data),
            )

            badge = "FMP + X Signal" if (has_x_signal and not is_stale) else "FMP Only (X signal pending)"

            is_surprise = ticker in surprise_tickers

            card = CompanySignalCard(
                ticker=ticker,
                company_name=(
                    profile.get("companyName", ticker) if isinstance(profile, dict) else ticker
                ),
                market_cap=fmp_snap.market_cap,
                sector=profile.get("sector") if isinstance(profile, dict) else None,
                industry=profile.get("industry") if isinstance(profile, dict) else None,
                fmp=fmp_snap,
                x_signal=x_snap,
                insider=insider_snap,
                congress=congress_snap,
                centrality=centrality_snap,
                combined_score=combined,
                fundamental_quality_score=fund_score,
                signal_source_badge=badge,
                is_surprise=is_surprise,
                citations=item_citations,
                is_seed=ticker in seed_upper,
            )

            cards.append(card)

        return cards
