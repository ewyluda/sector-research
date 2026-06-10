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
    shares_now = _avg_window(income, "weightedAverageShsOutDil", 0)   # stock, not flow — average the window
    shares_prior = _avg_window(income, "weightedAverageShsOutDil", 4)  # stock, not flow — average the window
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


# ── Altman Z-score (original 1968 formula; non-financials only) ──────────────

def build_altman_z(income: list[dict], balance: list[dict], profile: dict) -> dict:
    if _is_financial(profile):
        return {"z": None, "zone": None,
                "not_applicable_reason": "Altman Z is not meaningful for financial-sector companies"}
    b0 = balance[0] if balance else None
    ta0 = _f(b0, "totalAssets")
    ca0 = _f(b0, "totalCurrentAssets")
    cl0 = _f(b0, "totalCurrentLiabilities")
    mcap = _f(profile, "marketCap")
    if mcap is None:
        mcap = _f(profile, "mktCap")

    a = _div(None if ca0 is None or cl0 is None else ca0 - cl0, ta0)
    b = _div(_f(b0, "retainedEarnings"), ta0)
    # FMP serves ebit on /stable/ income statements; fall back to the
    # operatingIncome proxy if a payload omits it.
    ebit_ttm = _ttm(income, "ebit")
    if ebit_ttm is None:
        ebit_ttm = _ttm(income, "operatingIncome")
    c = _div(ebit_ttm, ta0)
    d = _div(mcap, _f(b0, "totalLiabilities"))
    e = _div(_ttm(income, "revenue"), ta0)
    if any(v is None for v in (a, b, c, d, e)):
        return {"z": None, "zone": None, "not_applicable_reason": None}
    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    zone = "safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress")
    return {"z": round(z, 4), "zone": zone, "not_applicable_reason": None}


# ── Beneish M-score (8-ratio; non-financials only) ───────────────────────────

def build_beneish_m(income: list[dict], balance: list[dict],
                    cashflow: list[dict], profile: dict) -> dict:
    base = {"m": None, "zone": None, "ratios": {},
            "inputs_missing": [], "not_applicable_reason": None}
    if _is_financial(profile):
        base["not_applicable_reason"] = "Beneish M is not meaningful for financial-sector companies"
        return base

    b0 = balance[0] if balance else None
    b4 = balance[4] if len(balance) > 4 else None
    ta0, ta4 = _f(b0, "totalAssets"), _f(b4, "totalAssets")
    rev_ttm, rev_prior = _ttm(income, "revenue"), _prior_ttm(income, "revenue")
    ni_ttm = _ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    da_ttm = _ttm(cashflow, "depreciationAndAmortization")
    da_prior = _prior_ttm(cashflow, "depreciationAndAmortization")
    sga_ttm = _ttm(income, "sellingGeneralAndAdministrativeExpenses")
    sga_prior = _prior_ttm(income, "sellingGeneralAndAdministrativeExpenses")
    gm_now = _div(_ttm(income, "grossProfit"), rev_ttm)
    gm_prior = _div(_prior_ttm(income, "grossProfit"), rev_prior)

    def asset_quality(b: dict | None, ta: float | None) -> float | None:
        # AQ = 1 - (CA + PPE + securities)/TA. longTermInvestments is the
        # securities term; short-term investments already sit inside CA.
        ca, ppe, lti = (_f(b, "totalCurrentAssets"),
                        _f(b, "propertyPlantEquipmentNet"),
                        _f(b, "longTermInvestments"))
        if None in (ca, ppe, lti) or not ta or ta < 0:
            return None
        return 1 - (ca + ppe + lti) / ta

    def leverage(b: dict | None, ta: float | None) -> float | None:
        ltd, cl = _f(b, "longTermDebt"), _f(b, "totalCurrentLiabilities")
        if None in (ltd, cl) or not ta or ta < 0:
            return None
        return (ltd + cl) / ta

    def dep_rate(da: float | None, b: dict | None) -> float | None:
        ppe = _f(b, "propertyPlantEquipmentNet")
        if da is None or ppe is None or (da + ppe) == 0:
            return None
        return da / (da + ppe)

    ratios = {
        "dsri": _div(_div(_f(b0, "netReceivables"), rev_ttm),
                     _div(_f(b4, "netReceivables"), rev_prior)),
        "gmi": _div(gm_prior, gm_now),
        "aqi": _div(asset_quality(b0, ta0), asset_quality(b4, ta4)),
        "sgi": _div(rev_ttm, rev_prior),
        "depi": _div(dep_rate(da_prior, b4), dep_rate(da_ttm, b0)),
        "sgai": _div(_div(sga_ttm, rev_ttm), _div(sga_prior, rev_prior)),
        "lvgi": _div(leverage(b0, ta0), leverage(b4, ta4)),
        "tata": _div(None if ni_ttm is None or cfo_ttm is None else ni_ttm - cfo_ttm, ta0),
    }
    base["ratios"] = {k: _round(v) for k, v in ratios.items()}
    missing = [k for k, v in ratios.items() if v is None]
    if missing:
        base["inputs_missing"] = missing
        return base

    m = (-4.84 + 0.92 * ratios["dsri"] + 0.528 * ratios["gmi"]
         + 0.404 * ratios["aqi"] + 0.892 * ratios["sgi"] + 0.115 * ratios["depi"]
         - 0.172 * ratios["sgai"] + 4.679 * ratios["tata"] - 0.327 * ratios["lvgi"])
    base["m"] = round(m, 4)
    base["zone"] = "flag" if m > -1.78 else ("caution" if m >= -2.22 else "unlikely")
    return base


# ── SBC dilution + margin slopes ─────────────────────────────────────────────

def build_sbc(income: list[dict], cashflow: list[dict]) -> dict:
    pct = _div(_ttm(cashflow, "stockBasedCompensation"), _ttm(income, "revenue"))
    growth = _div(_avg_window(income, "weightedAverageShsOutDil", 0),
                  _avg_window(income, "weightedAverageShsOutDil", 4))
    return {
        "sbc_pct_revenue": _round(pct * 100, 2) if pct is not None else None,
        "share_growth_yoy_pct": _round((growth - 1) * 100, 2) if growth is not None else None,
    }


def build_margin_slopes(income: list[dict]) -> dict:
    # Dropped quarters get no gap in x — the slope is pp-per-RETAINED-quarter,
    # not pp-per-calendar-quarter. `quarters` in the output is the retained count.
    def margin_series(numerator: str) -> list[float]:
        pts = []
        for stmt in reversed(income):  # chronological, oldest first
            rev, num = _f(stmt, "revenue"), _f(stmt, numerator)
            if rev and num is not None:  # skip None revenue and zero-revenue (avoid /0)
                pts.append(num / rev * 100)
        return pts

    out = {}
    for label, numerator in (("gross", "grossProfit"),
                             ("operating", "operatingIncome"),
                             ("net", "netIncome")):
        pts = margin_series(numerator)
        out[label] = {
            "slope_pp_per_quarter": _round(_ols_slope(pts)),
            "quarters": len(pts),
        }
    return out


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

    ni_ttm = _ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    ta0 = _f(balance[0] if balance else None, "totalAssets")
    ta4 = _f(balance[4] if len(balance) > 4 else None, "totalAssets")
    # Avg of window endpoints when the year-ago balance exists; TA[0] otherwise
    # (meta.quarters_available makes the fallback interpretable downstream).
    accrual_den = (ta0 + ta4) / 2 if ta0 is not None and ta4 is not None else ta0
    if accrual_den is not None and accrual_den <= 0:
        # negative/zero TA would sign-invert the ratio — same guard as Beneish
        accrual_den = None
    accruals = _div(None if ni_ttm is None or cfo_ttm is None else ni_ttm - cfo_ttm,
                    accrual_den)
    fcf_conv = _div(_ttm(cashflow, "freeCashFlow"), ni_ttm) \
        if ni_ttm is not None and ni_ttm > 0 else None

    return QuantFingerprint(
        piotroski=build_piotroski(income, balance, cashflow),
        altman_z=build_altman_z(income, balance, profile),
        beneish_m=build_beneish_m(income, balance, cashflow, profile),
        accruals_ratio=_round(accruals),
        fcf_conversion=_round(fcf_conv),
        sbc=build_sbc(income, cashflow),
        margin_slopes=build_margin_slopes(income),
        meta={
            "quarters_available": min(len(income), len(balance), len(cashflow)),
            "basis": "ttm_vs_prior_ttm",
            "sector": profile.get("sector") or "",
        },
    )
