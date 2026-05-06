"""Reverse-DCF solvers built atop the pure dcf() engine."""
from __future__ import annotations
from typing import Literal
from copy import deepcopy

from backend.app.models.model_state import ModelState
from backend.app.services.dcf import dcf

ImpliedDimension = Literal["revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"]

# Bisection bounds per dimension. Conservative wide ranges so any reasonable solution is bracketed.
BOUNDS: dict[str, tuple[float, float]] = {
    "revenue_growth_pct": (-0.50, 1.00),     # -50% to +100%
    "ebit_margin_pct":    (-0.50, 0.80),
    "terminal_multiple":  (0.5, 80.0),
}


def _apply_uniform_override(state: ModelState, dimension: ImpliedDimension, value: float) -> ModelState:
    """Return a deep-copied state with the chosen dimension overridden uniformly across forecast periods.
    For terminal_multiple, this overrides assumptions.terminal_multiple.
    For driver-style dimensions, the dimension is rewired into every forecast period's drivers — but the
    full driver→IS→CF recompute lives in model_balancing (Task 11+). For Task 7, we override directly
    on the line items the dcf() engine reads (ebitda for margin, free_cash_flow scaling for growth).
    This keeps the solver provable against the flat fixture; full integration with the recompute pipeline
    happens in Task 13."""
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]
    if dimension == "terminal_multiple":
        s.assumptions.terminal_multiple.value = value
        return s
    if dimension == "ebit_margin_pct":
        # For the flat fixture EBITDA proxy: scale EBITDA by (1 + value).
        # When recompute is integrated (Task 13), this branch will be replaced by:
        #   for p in forecast: s.drivers[p.label]["gross_margin_pct"].value = value
        #   then call services.model_balancing.recompute(s)
        for p in forecast:
            cell = s.income_statement["ebitda"][p.label]
            base = cell.value or 0.0
            cell.value = base * (1.0 + value)   # treat `value` as a delta to baseline margin
        return s
    if dimension == "revenue_growth_pct":
        # For the flat fixture: scale FCF by (1 + value)^t to simulate growth.
        # When recompute is integrated (Task 13), this branch sets the per-period revenue_growth_pct driver.
        for i, p in enumerate(forecast, start=1):
            cell = s.cash_flow["free_cash_flow"][p.label]
            base = cell.value or 0.0
            cell.value = base * ((1.0 + value) ** i)
        return s
    raise ValueError(f"unknown dimension {dimension}")


def solve_implied_driver(
    state: ModelState,
    *,
    dimension: ImpliedDimension,
    target_per_share: float,
    tolerance: float = 1e-3,
    max_iter: int = 60,
) -> float:
    """Bisection: find the value of `dimension` such that dcf(state).intrinsic_per_share == target_per_share."""
    lo, hi = BOUNDS[dimension]

    def evaluate(v: float) -> float:
        s = _apply_uniform_override(state, dimension, v)
        return dcf(s).intrinsic_per_share

    f_lo = evaluate(lo) - target_per_share
    f_hi = evaluate(hi) - target_per_share
    if f_lo * f_hi > 0:
        # Same sign at both bounds — target unreachable in this range
        raise ValueError(
            f"solve_implied_driver: target {target_per_share} unreachable in {dimension} range [{lo}, {hi}] "
            f"(f_lo={f_lo:.4f}, f_hi={f_hi:.4f})"
        )

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = evaluate(mid) - target_per_share
        if abs(f_mid) < tolerance:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)


def solve_implied_irr(
    state: ModelState,
    *,
    target_per_share: float,
    tolerance: float = 1e-4,
    max_iter: int = 80,
) -> float:
    """Bisection on discount_rate; returns the rate where intrinsic_per_share == target_per_share."""
    lo, hi = -0.05, 0.50
    def evaluate(r: float) -> float:
        return dcf(state, discount_rate=r).intrinsic_per_share
    f_lo = evaluate(lo) - target_per_share
    f_hi = evaluate(hi) - target_per_share
    if f_lo * f_hi > 0:
        raise ValueError(f"solve_implied_irr: target {target_per_share} unreachable in [{lo}, {hi}]")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = evaluate(mid) - target_per_share
        if abs(f_mid) < tolerance:
            return mid
        if f_lo * f_mid < 0:
            hi = mid; f_hi = f_mid
        else:
            lo = mid; f_lo = f_mid
    return 0.5 * (lo + hi)
