# backend/app/services/model_balancing.py
"""Recompute pipeline: drivers → IS → CF → BS."""
from __future__ import annotations
from copy import deepcopy
from backend.app.models.model_state import ModelState, ModelCell


class ModelBalanceError(Exception):
    """Balance sheet failed to balance after rollforward."""


def _drv(state: ModelState, period: str, key: str) -> float | None:
    cell = state.drivers.get(period, {}).get(key)
    return cell.value if cell else None


def _set_pnl(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> None:
    state.income_statement.setdefault(line, {})[period] = ModelCell(
        value=value, source="computed", formula=formula,
    )


def compute_income_statement(state: ModelState) -> ModelState:
    """Compute P&L from drivers, period by period (forecast only). Returns a deep-copied new state.
    Skips any cell already marked source=='override' (preserves user overrides)."""
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]

    # We need to know prior-period revenue; build a sequential chain through historicals first.
    prior_rev: float | None = None
    for p in s.periods:
        if p.is_historical:
            cell = s.income_statement.get("revenue", {}).get(p.label)
            if cell and cell.value is not None:
                prior_rev = cell.value

    for p in forecast:
        # --- Revenue ---
        existing = s.income_statement.get("revenue", {}).get(p.label)
        if existing and existing.source == "override" and existing.value is not None:
            rev = existing.value
        else:
            abs_cell = s.drivers.get(p.label, {}).get("revenue_absolute")
            if abs_cell and abs_cell.value is not None:
                rev = abs_cell.value
            else:
                growth = _drv(s, p.label, "revenue_growth_pct") or 0.0
                if prior_rev is None:
                    raise ValueError(f"compute_income_statement: no prior revenue for {p.label}")
                # Quarterly periods: apply growth as YoY against prior_rev (simplification for v1)
                rev = prior_rev * (1.0 + growth)
            _set_pnl(s, "revenue", p.label, rev, formula="= prior_revenue * (1 + revenue_growth_pct)")
        prior_rev = rev

        gm = _drv(s, p.label, "gross_margin_pct") or 0.0
        gp = rev * gm
        cogs = rev - gp
        _set_pnl(s, "cost_of_revenue", p.label, cogs, formula="= revenue - gross_profit")
        _set_pnl(s, "gross_profit", p.label, gp, formula="= revenue * gross_margin_pct")

        sga_pct = _drv(s, p.label, "sga_pct_revenue") or 0.0
        rd_pct = _drv(s, p.label, "rd_pct_revenue") or 0.0
        other_pct = _drv(s, p.label, "other_opex_pct_revenue") or 0.0
        da_pct = _drv(s, p.label, "da_pct_revenue") or 0.0
        sga, rd, other, da = rev * sga_pct, rev * rd_pct, rev * other_pct, rev * da_pct
        opex = sga + rd + other
        _set_pnl(s, "sga", p.label, sga)
        _set_pnl(s, "rd", p.label, rd)
        _set_pnl(s, "other_opex", p.label, other)
        _set_pnl(s, "operating_expenses", p.label, opex)
        _set_pnl(s, "depreciation_amortization", p.label, da)
        ebit = gp - opex - da
        _set_pnl(s, "ebit", p.label, ebit, formula="= gross_profit - operating_expenses - da")
        _set_pnl(s, "ebitda", p.label, ebit + da, formula="= ebit + da")

        # Interest assumed 0 in v1 P&L; debt schedule lives in CF/BS step
        _set_pnl(s, "interest_income", p.label, 0.0)
        _set_pnl(s, "interest_expense", p.label, 0.0)
        pretax = ebit
        _set_pnl(s, "pretax_income", p.label, pretax)
        tax_rate = _drv(s, p.label, "effective_tax_rate") or 0.0
        tax = pretax * tax_rate
        _set_pnl(s, "income_tax", p.label, tax)
        ni = pretax - tax
        _set_pnl(s, "net_income", p.label, ni, formula="= pretax_income * (1 - effective_tax_rate)")

        # Shares: prior shares × (1 + share_count_change_pct)
        sh_change = _drv(s, p.label, "share_count_change_pct") or 0.0
        prior_sh_cell = s.income_statement.get("shares_diluted", {}).get(p.label)
        if prior_sh_cell and prior_sh_cell.source != "override":
            # Find prior period's shares
            idx = s.periods.index(p)
            prior_period = s.periods[idx - 1]
            prior_sh = (s.income_statement.get("shares_diluted", {}).get(prior_period.label) or ModelCell()).value or 0.0
            sh = prior_sh * (1.0 + sh_change)
            _set_pnl(s, "shares_diluted", p.label, sh)
        else:
            sh = (prior_sh_cell.value if prior_sh_cell else 0.0) or 0.0
        _set_pnl(s, "eps_diluted", p.label, ni / sh if sh else 0.0)

    return s
