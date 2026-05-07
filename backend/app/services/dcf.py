"""Pure DCF engine. No IO, no DB."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from backend.app.models.model_state import ModelState


@dataclass
class DcfResult:
    intrinsic_value: float
    intrinsic_per_share: float
    fcf_schedule: list[tuple[str, float]]    # [(period_label, fcf)]
    pv_schedule: list[tuple[str, float]]     # [(period_label, pv_of_fcf)]
    terminal_value: float
    terminal_pv: float


def _forecast_periods(state: ModelState) -> list:
    return [p for p in state.periods if not p.is_historical]


def _resolve_overrides(state: ModelState, overrides: dict[str, float] | None) -> dict[str, float]:
    """A no-op for now; downstream solvers will pass overrides for revenue_growth_pct, ebit_margin_pct,
    or terminal_multiple. The simple flat-fixture path doesn't use overrides; full recompute integration
    happens in Task 13 when reverse_dcf is wired with real overrides."""
    return overrides or {}


def dcf(
    state: ModelState,
    *,
    overrides: dict[str, float] | None = None,
    terminal_method: Literal["exit_multiple", "perpetuity"] | None = None,
    discount_rate: float | None = None,
) -> DcfResult:
    """Compute intrinsic value from a ModelState.

    Reads FCF from `cash_flow.free_cash_flow.<period>` for each forecast period.
    Terminal value: exit_multiple = EBITDA(last forecast period) * terminal_multiple
                    perpetuity   = FCF(last) * (1+g) / (r-g)
    Discount rate: assumptions.discount_rate unless overridden.
    """
    forecast = _forecast_periods(state)
    if not forecast:
        raise ValueError("dcf(): state has no forecast periods")

    r = discount_rate if discount_rate is not None else (state.assumptions.discount_rate.value or 0.0)
    method = terminal_method or state.assumptions.terminal_method
    overrides = _resolve_overrides(state, overrides)

    # FCF schedule
    fcfs: list[tuple[str, float]] = []
    for p in forecast:
        cell = state.cash_flow.get("free_cash_flow", {}).get(p.label)
        if cell is None or cell.value is None:
            raise ValueError(f"dcf(): missing FCF for forecast period {p.label}")
        fcfs.append((p.label, float(cell.value)))

    # PV of FCFs (discount each by year-fraction; quarters fractional)
    pvs: list[tuple[str, float]] = []
    cumulative_year = 0.0
    for label, fcf in fcfs:
        # Q periods get 0.25 year increments; Y periods 1.0
        period = next(p for p in forecast if p.label == label)
        delta = 0.25 if period.kind == "Q" else 1.0
        cumulative_year += delta
        pv = fcf / ((1.0 + r) ** cumulative_year)
        pvs.append((label, pv))

    # Terminal value at end of last forecast period
    last = forecast[-1]
    if method == "exit_multiple":
        ebitda_cell = state.income_statement.get("ebitda", {}).get(last.label)
        if ebitda_cell is None or ebitda_cell.value is None:
            raise ValueError("dcf(): exit_multiple terminal requires EBITDA on last forecast period")
        tv = float(ebitda_cell.value) * (state.assumptions.terminal_multiple.value or 0.0)
    elif method == "perpetuity":
        g = state.assumptions.perpetuity_growth.value or 0.0
        if r <= g:
            raise ValueError(f"dcf(): perpetuity requires discount_rate > perpetuity_growth (r={r}, g={g})")
        tv = fcfs[-1][1] * (1.0 + g) / (r - g)
    else:
        raise ValueError(f"dcf(): unknown terminal_method {method!r}")

    tv_pv = tv / ((1.0 + r) ** cumulative_year)

    intrinsic = sum(pv for _, pv in pvs) + tv_pv

    # Per-share: divide by diluted shares from last forecast period
    shares_cell = state.income_statement.get("shares_diluted", {}).get(last.label)
    shares = float(shares_cell.value) if shares_cell and shares_cell.value else 1.0

    return DcfResult(
        intrinsic_value=intrinsic,
        intrinsic_per_share=intrinsic / shares,
        fcf_schedule=fcfs,
        pv_schedule=pvs,
        terminal_value=tv,
        terminal_pv=tv_pv,
    )
