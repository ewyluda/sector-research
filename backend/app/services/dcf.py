"""Pure DCF engine. No IO, no DB."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from backend.app.models.model_state import ModelState


@dataclass
class DcfResult:
    intrinsic_value: float                   # equity value = enterprise value - net debt
    intrinsic_per_share: float               # equity value / current diluted shares
    fcf_schedule: list[tuple[str, float]]    # [(period_label, unlevered fcf)]
    pv_schedule: list[tuple[str, float]]     # [(period_label, pv_of_fcf)]
    terminal_value: float
    terminal_pv: float
    enterprise_value: float = 0.0
    net_debt: float = 0.0
    shares: float = 0.0


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

    # Unlevered FCF: add back after-tax net interest, since the discount rate
    # is a WACC and debt holders are netted out below via net debt.
    tax = state.assumptions.tax_rate.value or 0.0
    fcfs: list[tuple[str, float]] = []
    for p in forecast:
        cell = state.cash_flow.get("free_cash_flow", {}).get(p.label)
        if cell is None or cell.value is None:
            raise ValueError(f"dcf(): missing FCF for forecast period {p.label}")
        net_interest = (_is_value(state, "interest_expense", p.label) - _is_value(state, "interest_income", p.label))
        fcfs.append((p.label, float(cell.value) + net_interest * (1.0 - tax)))

    # Mid-period convention: cash arrives on average halfway through a period.
    pvs: list[tuple[str, float]] = []
    elapsed = 0.0
    for p, (label, fcf) in zip(forecast, fcfs):
        length = 0.25 if p.kind == "Q" else 1.0
        pvs.append((label, fcf / ((1.0 + r) ** (elapsed + length / 2))))
        elapsed += length

    # Terminal value at the end of the last forecast period
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
    tv_pv = tv / ((1.0 + r) ** elapsed)

    enterprise_value = sum(pv for _, pv in pvs) + tv_pv

    # Bridge to equity at today's balance sheet: EV - (debt - cash), divided
    # by today's diluted shares. (Previously EV was divided by terminal-year
    # shares with no net-debt adjustment, and a missing share count became 1.)
    anchor = _valuation_anchor(state)
    net_debt = (_bs_value(state, "short_term_debt", anchor) + _bs_value(state, "long_term_debt", anchor)
                - _bs_value(state, "cash_and_equivalents", anchor))
    shares = _is_value(state, "shares_diluted", anchor)
    if shares <= 0:
        raise ValueError(f"dcf(): no diluted share count for {anchor} — cannot value per share")
    equity_value = enterprise_value - net_debt

    return DcfResult(
        intrinsic_value=equity_value,
        intrinsic_per_share=equity_value / shares,
        fcf_schedule=fcfs,
        pv_schedule=pvs,
        terminal_value=tv,
        terminal_pv=tv_pv,
        enterprise_value=enterprise_value,
        net_debt=net_debt,
        shares=shares,
    )


def _is_value(state: ModelState, line: str, label: str) -> float:
    cell = state.income_statement.get(line, {}).get(label)
    return float(cell.value) if cell is not None and cell.value is not None else 0.0


def _bs_value(state: ModelState, line: str, label: str) -> float:
    cell = state.balance_sheet.get(line, {}).get(label)
    return float(cell.value) if cell is not None and cell.value is not None else 0.0


def _valuation_anchor(state: ModelState) -> str:
    """The latest reported period (today's balance sheet and share count);
    the first forecast period for states with no history (test fixtures)."""
    hist = [p for p in state.periods if p.is_historical]
    return hist[-1].label if hist else _forecast_periods(state)[0].label
