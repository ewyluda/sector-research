"""Reverse-DCF solvers built atop the pure dcf() engine."""
from __future__ import annotations
from typing import Literal
from copy import deepcopy

from backend.app.models.model_state import ModelState
from backend.app.services.dcf import dcf
from backend.app.services.model_balancing import recompute

ImpliedDimension = Literal["revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"]

# Bisection bounds per dimension. Conservative wide ranges so any reasonable solution is bracketed.
BOUNDS: dict[str, tuple[float, float]] = {
    "revenue_growth_pct": (-0.50, 1.00),     # -50% to +100%
    "ebit_margin_pct":    (-0.50, 0.80),
    "terminal_multiple":  (0.5, 80.0),
}


def _apply_uniform_override(state: ModelState, dimension: ImpliedDimension, value: float) -> ModelState:
    """Return a deep-copied state with the chosen dimension overridden uniformly across forecast periods.
    For terminal_multiple, overrides assumptions.terminal_multiple directly.
    For driver-style dimensions (revenue_growth_pct, ebit_margin_pct), sets the driver on every
    forecast period and re-runs recompute() so the IS/CF/BS are fully consistent."""
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]
    if dimension == "terminal_multiple":
        s.assumptions.terminal_multiple.value = value
        return s
    if dimension == "ebit_margin_pct":
        for p in forecast:
            expense_drag = sum(
                (s.drivers[p.label].get(key).value if s.drivers[p.label].get(key) else 0.0) or 0.0
                for key in ("sga_pct_revenue", "rd_pct_revenue", "other_opex_pct_revenue", "da_pct_revenue")
            )
            cell = s.drivers[p.label].get("gross_margin_pct")
            if cell is None:
                from backend.app.models.model_state import ModelCell
                s.drivers[p.label]["gross_margin_pct"] = ModelCell(value=value + expense_drag, source="driver")
            else:
                cell.value = value + expense_drag
        return recompute(s)
    if dimension == "revenue_growth_pct":
        for p in forecast:
            cell = s.drivers[p.label].get("revenue_growth_pct")
            if cell is None:
                from backend.app.models.model_state import ModelCell
                s.drivers[p.label]["revenue_growth_pct"] = ModelCell(value=value, source="driver")
            else:
                cell.value = value
            # Disable absolute-revenue override if previously set
            abs_cell = s.drivers[p.label].get("revenue_absolute")
            if abs_cell:
                abs_cell.value = None
        return recompute(s)
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


def sensitivity_grid(
    state: ModelState,
    *,
    x_dim: ImpliedDimension,
    x_range: tuple[float, float],
    y_dim: ImpliedDimension,
    y_range: tuple[float, float],
    size: int = 21,
) -> dict:
    """Evaluate intrinsic_per_share over a size x size grid of (x_dim, y_dim) overrides."""
    if x_dim == y_dim:
        raise ValueError("sensitivity_grid: x_dim and y_dim must differ")
    xs = [x_range[0] + (x_range[1] - x_range[0]) * i / (size - 1) for i in range(size)]
    ys = [y_range[0] + (y_range[1] - y_range[0]) * i / (size - 1) for i in range(size)]
    values: list[list[float]] = []
    for y in ys:
        row: list[float] = []
        s_y = _apply_uniform_override(state, y_dim, y)
        for x in xs:
            s_xy = _apply_uniform_override(s_y, x_dim, x)
            row.append(dcf(s_xy).intrinsic_per_share)
        values.append(row)
    return {"x_dim": x_dim, "y_dim": y_dim, "x_values": xs, "y_values": ys, "values": values}


def thesis_vs_priced_in(state: ModelState, *, target_per_share: float) -> list[dict]:
    """For each of the three dimensions, return {thesis, priced_in, delta}.
    `thesis` = current value in `state` (revenue growth: average across forecast; margin: avg gross_margin_pct;
    multiple: assumptions.terminal_multiple). `priced_in` = solver output."""
    forecast = [p for p in state.periods if not p.is_historical]

    def avg_driver(key: str) -> float:
        vals = [state.drivers.get(p.label, {}).get(key, None) for p in forecast]
        nums = [c.value for c in vals if c is not None and c.value is not None]
        return sum(nums) / len(nums) if nums else 0.0

    def avg_ebit_margin() -> float:
        margins = []
        for p in forecast:
            revenue = (state.income_statement.get("revenue", {}).get(p.label) or None)
            ebit = (state.income_statement.get("ebit", {}).get(p.label) or None)
            if revenue is None or ebit is None or not revenue.value:
                continue
            margins.append((ebit.value or 0.0) / revenue.value)
        return sum(margins) / len(margins) if margins else 0.0

    thesis_growth = avg_driver("revenue_growth_pct")
    thesis_margin = avg_ebit_margin()
    thesis_multiple = state.assumptions.terminal_multiple.value or 0.0

    rows = []
    for dim, thesis in [
        ("revenue_growth_pct", thesis_growth),
        ("ebit_margin_pct", thesis_margin),
        ("terminal_multiple", thesis_multiple),
    ]:
        try:
            priced_in = solve_implied_driver(state, dimension=dim, target_per_share=target_per_share)
        except ValueError:
            priced_in = None
        rows.append({
            "dimension": dim,
            "thesis": thesis,
            "priced_in": priced_in,
            "delta": (thesis - priced_in) if priced_in is not None else None,
        })
    return rows
