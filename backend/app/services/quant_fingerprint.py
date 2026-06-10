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


def _is_financial(profile: dict) -> bool:
    return (profile or {}).get("sector") == FINANCIAL_SECTOR


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
        piotroski={"score": 0, "components_evaluated": 0, "components": []},
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
