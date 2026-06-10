"""Peer comparison table builder — fetches FMP data and computes median/delta metrics.

Shared by three consumers: the /api/peers router, the /compare page (via that
router), and workspace step 5 (differentiation). One builder, one set of
numbers everywhere.
"""
from __future__ import annotations

import asyncio
from statistics import median
from typing import Any

from backend.app.models.peer_comp import PeerCompTable, PeerCompRow, PeerError

METRIC_FIELDS = (
    "pe",
    "ev_ebitda",
    "p_b",
    "p_fcf",
    "p_s",
    "peg",
    "revenue_yoy",
    "eps_yoy",
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "fcf_margin",
    "roe",
    "roic",
    "roa",
    "market_cap",
)

# Max tickers fetched concurrently (4 FMP calls each) — same reason
# DiscoveryEngine batches 10 at a time: don't hammer FMP with a
# 50-request burst on a full 13-ticker compare.
FETCH_CONCURRENCY = 10


async def build_peer_comp_table(
    *, focus_ticker: str, peer_tickers: list[str], fmp,
) -> tuple[PeerCompTable | None, list[PeerError]]:
    """Build a peer comparison table with median and delta metrics.

    Returns (None, []) when peer_tickers is empty.
    Returns (table, errors) where errors list per-peer failures (focus failure raises).
    """
    if not peer_tickers:
        return None, []

    tickers = [focus_ticker] + list(peer_tickers)

    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def _fetch_limited(t: str) -> PeerCompRow:
        async with sem:
            return await _fetch_one(t, fmp)

    results = await asyncio.gather(
        *(_fetch_limited(t) for t in tickers),
        return_exceptions=True,
    )

    rows: list[PeerCompRow] = []
    errors: list[PeerError] = []

    for ticker, res in zip(tickers, results):
        if isinstance(res, Exception):
            if ticker != focus_ticker:
                errors.append(
                    PeerError(peer_ticker=ticker, error_message=str(res))
                )
            else:
                # Focus failure is fatal — raise it.
                raise res
        else:
            rows.append(res)

    if len(rows) < 2:
        # Focus only with no peers retrieved successfully
        return None, errors

    peers_only = [r for r in rows if r.ticker != focus_ticker]
    median_row = _compute_median(peers_only)
    focus_row = next((r for r in rows if r.ticker == focus_ticker), None)
    if not focus_row:
        # Should not happen (focus succeeded) but be defensive
        return None, errors

    delta_row = _compute_delta(focus_row, median_row)

    return (
        PeerCompTable(
            focus_ticker=focus_ticker,
            rows=rows,
            median=median_row,
            delta_vs_median_pct=delta_row,
        ),
        errors,
    )


async def _fetch_one(ticker: str, fmp) -> PeerCompRow:
    """Fetch key-metrics, ratios, growth, and profile for one ticker.

    Wire-name notes (live-verified 2026-06-09): the /stable/ API serves the
    valuation multiples from ratios-ttm — the key-metrics-ttm spellings
    (peRatioTTM etc.) are no longer present there and are kept only as legacy
    fallbacks (graph/nodes.py mirrors this mapping). Returns (ROE/ROIC/ROA)
    come from key-metrics-ttm, margins from ratios-ttm, market cap from profile.
    """
    # Intentionally no return_exceptions here: partial data for a ticker is
    # worse than a clean per-ticker error — the outer gather in
    # build_peer_comp_table contains the failure (PeerError for peers,
    # raise for the focus ticker).
    (km, _), (ratios, _), (fg, _), (profile, _) = await asyncio.gather(
        fmp.get_key_metrics_ttm(ticker),
        fmp.get_ratios_ttm(ticker),
        fmp.get_financial_growth(ticker),
        fmp.get_company_profile(ticker),
    )
    fg_row = fg[0] if isinstance(fg, list) and fg else {}

    p_fcf = _first(
        (ratios, "priceToFreeCashFlowRatioTTM"),
        (km, "priceToFreeCashFlowsRatioTTM"),
    )
    p_s = _first((ratios, "priceToSalesRatioTTM"), (km, "priceToSalesRatioTTM"))

    # FMP /stable/ doesn't surface an FCF-margin field today (verified
    # 2026-06-09), so derive it: FCF/sales = (mcap/sales) ÷ (mcap/FCF)
    # = p_s ÷ p_fcf. A wire-served value takes precedence if FMP adds one.
    fcf_margin = _first((ratios, "freeCashFlowMarginTTM"))
    if fcf_margin is None and p_s is not None and p_fcf:
        fcf_margin = p_s / p_fcf

    return PeerCompRow(
        ticker=ticker,
        pe=_first((ratios, "priceToEarningsRatioTTM"), (km, "peRatioTTM")),
        ev_ebitda=_first(
            (ratios, "enterpriseValueMultipleTTM"),
            (km, "enterpriseValueOverEBITDATTM"),
        ),
        p_b=_first((ratios, "priceToBookRatioTTM"), (km, "priceToBookRatioTTM")),
        p_fcf=p_fcf,
        p_s=p_s,
        peg=_first((ratios, "priceToEarningsGrowthRatioTTM"), (km, "pegRatioTTM")),
        revenue_yoy=_first((fg_row, "revenueGrowth")),
        eps_yoy=_first((fg_row, "epsGrowth"), (fg_row, "epsgrowth")),
        gross_margin=_first((ratios, "grossProfitMarginTTM")),
        operating_margin=_first((ratios, "operatingProfitMarginTTM")),
        ebitda_margin=_first((ratios, "ebitdaMarginTTM")),
        fcf_margin=fcf_margin,
        roe=_first((km, "returnOnEquityTTM"), (km, "roeTTM")),
        roic=_first((km, "returnOnInvestedCapitalTTM"), (km, "roicTTM")),
        # returnOnAssetsTTM is on km (verified 2026-06-09); tangible-assets
        # variant is the last fallback in case a ticker is missing the true key.
        roa=_first(
            (km, "returnOnAssetsTTM"), (km, "returnOnTangibleAssetsTTM")
        ),
        market_cap=_first((profile, "marketCap"), (profile, "mktCap")),
    )


def _first(*candidates: tuple[Any, str]) -> float | None:
    """First non-None value across (dict, key) candidates.

    Distinct from `x or y` — a legitimate 0.0 value short-circuits correctly.
    """
    for d, key in candidates:
        v = _safe(d, key)
        if v is not None:
            return v
    return None


def _safe(d: Any, key: str) -> float | None:
    """Extract and cast a float from a dict, handling None and type errors."""
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compute_median(rows: list[PeerCompRow]) -> PeerCompRow:
    """Compute median across peer rows, returning a synthetic row."""
    out: dict = {"ticker": "__median__"}
    for field in METRIC_FIELDS:
        vals = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        out[field] = median(vals) if vals else None
    return PeerCompRow(**out)


def _compute_delta(focus: PeerCompRow, med: PeerCompRow) -> PeerCompRow:
    """Compute focus vs. median delta (%), returning a synthetic row."""
    out: dict = {"ticker": "__delta__"}
    for field in METRIC_FIELDS:
        fv = getattr(focus, field)
        mv = getattr(med, field)
        if fv is None or mv is None or mv == 0:
            out[field] = None
        else:
            out[field] = round(((fv - mv) / abs(mv)) * 100.0, 2)
    return PeerCompRow(**out)
