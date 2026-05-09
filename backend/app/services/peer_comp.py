"""Peer comparison table builder — fetches FMP data and computes median/delta metrics."""
from __future__ import annotations

import asyncio
from statistics import median
from typing import Any

from backend.app.models.workspace_schemas import PeerCompTable, PeerCompRow, PeerError

METRIC_FIELDS = (
    "pe",
    "ev_ebitda",
    "p_b",
    "p_fcf",
    "p_s",
    "roe",
    "revenue_yoy",
    "eps_yoy",
    "gross_margin",
    "ebitda_margin",
)


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
    results = await asyncio.gather(
        *(_fetch_one(t, fmp) for t in tickers),
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
    """Fetch key_metrics and financial_growth for one ticker, return PeerCompRow."""
    km, _ = await fmp.get_key_metrics_ttm(ticker)
    fg, _ = await fmp.get_financial_growth(ticker)

    # Map FMP wire-format names to schema-side names.
    # key_metrics_ttm endpoint field names.
    metrics_dict = {
        "pe": _safe(km, "peRatioTTM"),
        "ev_ebitda": _safe(km, "enterpriseValueOverEBITDATTM"),
        "p_b": _safe(km, "priceToBookRatioTTM"),
        "p_fcf": _safe(km, "priceToFreeCashFlowsRatioTTM"),
        "p_s": _safe(km, "priceToSalesRatioTTM"),
        "roe": _safe(km, "roeTTM"),
    }

    # financial_growth endpoint: returns list of dicts. Use most recent (index 0).
    fg_row = fg[0] if isinstance(fg, list) and fg else {}
    metrics_dict.update(
        {
            "revenue_yoy": _safe(fg_row, "revenueGrowth"),
            "eps_yoy": _safe(fg_row, "epsGrowth") or _safe(fg_row, "epsgrowth"),
            "gross_margin": None,  # Not available in financial_growth
            "ebitda_margin": None,  # Not available in financial_growth
        }
    )

    return PeerCompRow(ticker=ticker, **metrics_dict)


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
