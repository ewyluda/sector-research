"""Deterministic quant fingerprint — pure functions over the FMP statement
payloads already fetched in `node_deep_dive`.

Pattern: `services/model_balancing.py` — synchronous, no I/O, unit-testable
on JSON fixtures. Every metric is independently nullable; a missing input
nulls that metric without affecting the others.

Conventions (see docs/superpowers/specs/2026-06-10-quant-fingerprint-design.md):
  - Statements arrive newest-first (FMP order).
  - Flow metrics: TTM = sum(quarters[0:4]); prior TTM = sum(quarters[4:8]).
    No partial sums — a missing key anywhere in a window yields None.
  - Point-in-time balance items compare index 0 vs index 4 (year-ago).
  - End-of-window total assets are used for ROA / asset turnover in both
    windows (the beginning-of-window variant would need a 9th quarter).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

FINANCIAL_SECTOR = "Financial Services"


# ── Low-level helpers ────────────────────────────────────────────────────────

def _f(stmt: dict | None, key: str) -> float | None:
    if not stmt:
        return None
    v = stmt.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _window(stmts: list[dict], key: str, start: int) -> float | None:
    """Sum a 4-quarter window; None unless all four quarters carry the key."""
    if len(stmts) < start + 4:
        return None
    vals = [_f(s, key) for s in stmts[start:start + 4]]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def _ttm(stmts: list[dict], key: str) -> float | None:
    return _window(stmts, key, 0)


def _prior_ttm(stmts: list[dict], key: str) -> float | None:
    return _window(stmts, key, 4)


def _avg_window(stmts: list[dict], key: str, start: int) -> float | None:
    total = _window(stmts, key, start)
    return total / 4 if total is not None else None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _ols_slope(values: list[float]) -> float | None:
    """Least-squares slope over x = 0..n-1. None with < 4 points."""
    n = len(values)
    if n < 4:
        return None
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    sxx = sum((i - x_mean) ** 2 for i in range(n))
    sxy = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    return sxy / sxx if sxx else None


def _round(v: float | None, places: int = 4) -> float | None:
    return round(v, places) if v is not None else None


def _is_financial(profile: dict | None) -> bool:
    return (profile or {}).get("sector") == FINANCIAL_SECTOR


# ── Piotroski F-score ────────────────────────────────────────────────────────

def build_piotroski(income: list[dict], balance: list[dict], cashflow: list[dict]) -> dict:
    b0 = balance[0] if balance else None
    b4 = balance[4] if len(balance) > 4 else None

    ni_ttm = _ttm(income, "netIncome")
    ni_prior = _prior_ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    rev_ttm = _ttm(income, "revenue")
    rev_prior = _prior_ttm(income, "revenue")
    ta0 = _f(b0, "totalAssets")
    ta4 = _f(b4, "totalAssets")

    roa_now = _div(ni_ttm, ta0)
    roa_prior = _div(ni_prior, ta4)
    lev_now = _div(_f(b0, "longTermDebt"), ta0)
    lev_prior = _div(_f(b4, "longTermDebt"), ta4)
    cr_now = _div(_f(b0, "totalCurrentAssets"), _f(b0, "totalCurrentLiabilities"))
    cr_prior = _div(_f(b4, "totalCurrentAssets"), _f(b4, "totalCurrentLiabilities"))
    shares_now = _avg_window(income, "weightedAverageShsOutDil", 0)
    shares_prior = _avg_window(income, "weightedAverageShsOutDil", 4)
    gm_now = _div(_ttm(income, "grossProfit"), rev_ttm)
    gm_prior = _div(_prior_ttm(income, "grossProfit"), rev_prior)
    ato_now = _div(rev_ttm, ta0)
    ato_prior = _div(rev_prior, ta4)

    def gt(a, b):
        return None if a is None or b is None else a > b

    def lte(a, b):
        return None if a is None or b is None else a <= b

    def detail(now, prior):
        if now is None or prior is None:
            return "insufficient data"
        return f"{now:.4g} now vs {prior:.4g} prior"

    components = [
        {"key": "roa_positive", "label": "ROA positive (TTM)",
         "passed": None if roa_now is None else roa_now > 0,
         "detail": "insufficient data" if roa_now is None else f"ROA {roa_now:.4g}"},
        {"key": "cfo_positive", "label": "Operating cash flow positive (TTM)",
         "passed": None if cfo_ttm is None else cfo_ttm > 0,
         "detail": "insufficient data" if cfo_ttm is None else f"CFO {cfo_ttm:.4g}"},
        {"key": "roa_delta", "label": "ROA improved YoY",
         "passed": gt(roa_now, roa_prior), "detail": detail(roa_now, roa_prior)},
        {"key": "accruals_quality", "label": "CFO exceeds net income (TTM)",
         "passed": None if cfo_ttm is None or ni_ttm is None else cfo_ttm > ni_ttm,
         "detail": detail(cfo_ttm, ni_ttm)},
        {"key": "leverage_delta", "label": "Long-term leverage flat or lower YoY",
         "passed": lte(lev_now, lev_prior), "detail": detail(lev_now, lev_prior)},
        {"key": "current_ratio_delta", "label": "Current ratio improved YoY",
         "passed": gt(cr_now, cr_prior), "detail": detail(cr_now, cr_prior)},
        {"key": "no_dilution", "label": "No net share issuance YoY",
         "passed": lte(shares_now, shares_prior), "detail": detail(shares_now, shares_prior)},
        {"key": "gross_margin_delta", "label": "Gross margin improved YoY",
         "passed": gt(gm_now, gm_prior), "detail": detail(gm_now, gm_prior)},
        {"key": "asset_turnover_delta", "label": "Asset turnover improved YoY",
         "passed": gt(ato_now, ato_prior), "detail": detail(ato_now, ato_prior)},
    ]
    return {
        "score": sum(1 for c in components if c["passed"] is True),
        "components_evaluated": sum(1 for c in components if c["passed"] is not None),
        "components": components,
    }


# ── Top-level ────────────────────────────────────────────────────────────────

@dataclass
class QuantFingerprint:
    """JSON-safe payload stored on CuratedFinancials.quant_fingerprint.

    No from_dict — nothing rehydrates it; the raw dict round-trips through
    CuratedFinancials the same way macro_indicators does.
    """
    piotroski: dict
    altman_z: dict
    beneish_m: dict
    accruals_ratio: float | None
    fcf_conversion: float | None
    sbc: dict
    margin_slopes: dict
    meta: dict

    def to_dict(self) -> dict:
        return asdict(self)


def build_quant_fingerprint(
    income: list[dict],
    balance: list[dict],
    cashflow: list[dict],
    profile: dict,
) -> QuantFingerprint:
    income = income or []
    balance = balance or []
    cashflow = cashflow or []
    profile = profile or {}

    return QuantFingerprint(
        piotroski=build_piotroski(income, balance, cashflow),
        altman_z={"z": None, "zone": None, "not_applicable_reason": None},
        beneish_m={"m": None, "zone": None, "ratios": {},
                   "inputs_missing": [], "not_applicable_reason": None},
        accruals_ratio=None,
        fcf_conversion=None,
        sbc={"sbc_pct_revenue": None, "share_growth_yoy_pct": None},
        margin_slopes={},
        meta={
            "quarters_available": min(len(income), len(balance), len(cashflow)),
            "basis": "ttm_vs_prior_ttm",
            "sector": profile.get("sector") or "",
        },
    )
