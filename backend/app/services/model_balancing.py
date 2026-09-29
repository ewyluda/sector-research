# backend/app/services/model_balancing.py
"""Recompute pipeline: drivers → IS → CF → BS.

Conventions (2026-09-27 rework — see docs/adr and the review's M7–M9):
- Quarterly revenue growth is year-over-year against the same quarter a year
  earlier, so seasonality survives and an annual growth rate is never
  compounded four times a year. The first forecast year builds on the four
  quarters of the year before it; later years chain year on year.
- Flow drivers are per period: days-based working capital uses the period's
  length (91.25 or 365 days), interest applies the annual rate to the prior
  period's balance for the period's fraction of a year.
- Tax uses the period's effective_tax_rate driver, else assumptions.tax_rate.
- The balance sheet rolls forward from the prior period with no plug: cash
  absorbs net cash flow, a revolver (short-term debt) covers any shortfall,
  retained earnings roll by net income less dividends. Because every flow is
  mirrored on the balance sheet, a period without user overrides must balance;
  if it doesn't, that's an engine bug and ModelBalanceError is raised. Only a
  period containing user overrides (deliberately inconsistent inputs) is
  reconciled through retained earnings, and the cell says by how much.
"""
from __future__ import annotations
from copy import deepcopy

from backend.app.models.model_state import ModelCell, ModelState, Period
from backend.app.services.model_periods import days_in_period, period_fraction


class ModelBalanceError(Exception):
    """Balance sheet failed to balance after rollforward."""


def _drv(state: ModelState, period: str, key: str) -> float | None:
    cell = state.drivers.get(period, {}).get(key)
    return cell.value if cell else None


def _override_value(cell: ModelCell | None) -> float | None:
    if cell is not None and cell.source == "override" and cell.value is not None:
        return float(cell.value)
    return None


def _value(stmt: dict[str, dict[str, ModelCell]], line: str, period: str) -> float | None:
    cell = stmt.get(line, {}).get(period)
    return cell.value if cell is not None else None


def _set(stmt: dict[str, dict[str, ModelCell]], line: str, period: str, value: float,
         formula: str | None = None) -> float:
    period_cells = stmt.setdefault(line, {})
    override = _override_value(period_cells.get(period))
    if override is not None:
        return override
    period_cells[period] = ModelCell(value=value, source="computed", formula=formula)
    return value


def _set_pnl(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> float:
    return _set(state.income_statement, line, period, value, formula)


def _set_cf(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> float:
    return _set(state.cash_flow, line, period, value, formula)


def _set_bs(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> float:
    return _set(state.balance_sheet, line, period, value, formula)


def _prior(state: ModelState, p: Period) -> Period | None:
    idx = state.periods.index(p)
    return state.periods[idx - 1] if idx > 0 else None


def _bs_prior(state: ModelState, line: str, p: Period) -> float:
    prior = _prior(state, p)
    if prior is None:
        return 0.0
    return _value(state.balance_sheet, line, prior.label) or 0.0


def _revenue_base(s: ModelState, p: Period) -> tuple[float, str]:
    """The revenue a period's growth rate applies to, and a formula note."""
    labels = {q.label for q in s.periods}
    rev = lambda label: _value(s.income_statement, "revenue", label)  # noqa: E731
    prior = _prior(s, p)
    if p.kind == "Q":
        year, q = p.label.split("Q")
        same_q_last_year = f"{int(year) - 1}Q{q}"
        if same_q_last_year in labels and rev(same_q_last_year) is not None:
            return rev(same_q_last_year), f"= revenue[{same_q_last_year}] * (1 + revenue_growth_pct)"
        latest = _latest_revenue_period(s, p)
        if latest is not None:
            return rev(latest), f"= revenue[{latest}] * (1 + revenue_growth_pct)  [no year-ago quarter]"
        raise ValueError(f"compute_income_statement: no prior revenue for {p.label}")
    # Annual period
    if prior is not None and prior.kind == "Y" and rev(prior.label) is not None:
        return rev(prior.label), f"= revenue[{prior.label}] * (1 + revenue_growth_pct)"
    year = int(p.label.rstrip("Y")) - 1
    quarters = [f"{year}Q{i}" for i in range(1, 5)]
    if all(rev(q) is not None for q in quarters):
        return sum(rev(q) for q in quarters), f"= sum(revenue[{year}Q1..Q4]) * (1 + revenue_growth_pct)"
    latest = _latest_revenue_period(s, p)
    if latest is not None:
        # Legacy layout (a gap before the first year): annualize the last quarter.
        scale = 4.0 if "Q" in latest else 1.0
        return rev(latest) * scale, f"= revenue[{latest}] × {scale:g} * (1 + revenue_growth_pct)"
    raise ValueError(f"compute_income_statement: no prior revenue for {p.label}")


def _latest_revenue_period(s: ModelState, p: Period) -> str | None:
    """Most recent period before `p` that has revenue (sparse / legacy states)."""
    idx = s.periods.index(p)
    for q in reversed(s.periods[:idx]):
        if _value(s.income_statement, "revenue", q.label) is not None:
            return q.label
    return None


def _income_statement_period(s: ModelState, p: Period) -> None:
    """P&L for one forecast period (needs the prior period's balance sheet)."""
    frac = period_fraction(p)

    # --- Revenue ---
    abs_rev = _drv(s, p.label, "revenue_absolute")
    if abs_rev is not None:
        rev = _set_pnl(s, "revenue", p.label, abs_rev, formula="= revenue_absolute")
    else:
        base, formula = _revenue_base(s, p)
        growth = _drv(s, p.label, "revenue_growth_pct") or 0.0
        rev = _set_pnl(s, "revenue", p.label, base * (1.0 + growth), formula=formula)

    gm = _drv(s, p.label, "gross_margin_pct") or 0.0
    gp = _set_pnl(s, "gross_profit", p.label, rev * gm, formula="= revenue * gross_margin_pct")
    _set_pnl(s, "cost_of_revenue", p.label, rev - gp, formula="= revenue - gross_profit")

    sga = _set_pnl(s, "sga", p.label, rev * (_drv(s, p.label, "sga_pct_revenue") or 0.0))
    rd = _set_pnl(s, "rd", p.label, rev * (_drv(s, p.label, "rd_pct_revenue") or 0.0))
    other = _set_pnl(s, "other_opex", p.label, rev * (_drv(s, p.label, "other_opex_pct_revenue") or 0.0))
    opex = _set_pnl(s, "operating_expenses", p.label, sga + rd + other)
    da = _set_pnl(s, "depreciation_amortization", p.label, rev * (_drv(s, p.label, "da_pct_revenue") or 0.0))
    ebit = _set_pnl(s, "ebit", p.label, gp - opex - da, formula="= gross_profit - operating_expenses - da")
    _set_pnl(s, "ebitda", p.label, ebit + da, formula="= ebit + da")

    # --- Interest on the prior period's balances, for this period's length ---
    prior_cash = _bs_prior(s, "cash_and_equivalents", p)
    prior_debt = _bs_prior(s, "short_term_debt", p) + _bs_prior(s, "long_term_debt", p)
    ii = _set_pnl(s, "interest_income", p.label,
                  prior_cash * (_drv(s, p.label, "interest_income_yield") or 0.0) * frac,
                  formula="= prior cash * interest_income_yield * period_years")
    ie = _set_pnl(s, "interest_expense", p.label,
                  prior_debt * (_drv(s, p.label, "interest_expense_rate") or 0.0) * frac,
                  formula="= prior total debt * interest_expense_rate * period_years")
    pretax = _set_pnl(s, "pretax_income", p.label, ebit + ii - ie)

    tax_rate = _drv(s, p.label, "effective_tax_rate")
    if tax_rate is None:
        tax_rate = s.assumptions.tax_rate.value or 0.0
    tax = _set_pnl(s, "income_tax", p.label, max(pretax, 0.0) * tax_rate,
                   formula="= max(pretax_income, 0) * tax rate")
    ni = _set_pnl(s, "net_income", p.label, pretax - tax, formula="= pretax_income - income_tax")

    # --- Shares: prior shares × (1 + share_count_change_pct) ---
    existing_sh = s.income_statement.get("shares_diluted", {}).get(p.label)
    override_sh = _override_value(existing_sh)
    if override_sh is not None:
        sh = override_sh
    else:
        prior = _prior(s, p)
        prior_sh = _value(s.income_statement, "shares_diluted", prior.label) if prior else None
        if prior_sh is None and existing_sh is not None:
            prior_sh = existing_sh.value
        sh = _set_pnl(s, "shares_diluted", p.label,
                      (prior_sh or 0.0) * (1.0 + (_drv(s, p.label, "share_count_change_pct") or 0.0)))
    _set_pnl(s, "eps_diluted", p.label, ni / sh if sh else 0.0)


def _cash_flow_period(s: ModelState, p: Period) -> None:
    """CF for one forecast period from its P&L and the prior balance sheet."""
    days = days_in_period(p)
    ni = _value(s.income_statement, "net_income", p.label) or 0.0
    da = _value(s.income_statement, "depreciation_amortization", p.label) or 0.0
    rev = _value(s.income_statement, "revenue", p.label) or 0.0
    cogs = _value(s.income_statement, "cost_of_revenue", p.label) or 0.0

    new_ar = rev * (_drv(s, p.label, "dso_days") or 0.0) / days
    new_inv = cogs * (_drv(s, p.label, "dio_days") or 0.0) / days
    new_ap = cogs * (_drv(s, p.label, "dpo_days") or 0.0) / days

    _set_cf(s, "net_income_cf", p.label, ni)
    _set_cf(s, "depreciation_amortization_cf", p.label, da)
    d_ar = _set_cf(s, "delta_accounts_receivable", p.label, -(new_ar - _bs_prior(s, "accounts_receivable", p)))
    d_inv = _set_cf(s, "delta_inventory", p.label, -(new_inv - _bs_prior(s, "inventory", p)))
    d_ap = _set_cf(s, "delta_accounts_payable", p.label, new_ap - _bs_prior(s, "accounts_payable", p))
    ocf = _set_cf(s, "operating_cash_flow", p.label, ni + da + d_ar + d_inv + d_ap)
    capex = _set_cf(s, "capex", p.label, -(rev * (_drv(s, p.label, "capex_pct_revenue") or 0.0)))
    fcf = _set_cf(s, "free_cash_flow", p.label, ocf + capex)

    debt_issued = _set_cf(s, "debt_issued", p.label, 0.0)
    # Can't repay more long-term debt than exists (the BS floors at zero).
    repay = min(_drv(s, p.label, "debt_repayment_dollars") or 0.0, _bs_prior(s, "long_term_debt", p))
    debt_repay = _set_cf(s, "debt_repaid", p.label, -max(repay, 0.0))
    dividends = _set_cf(s, "dividends_paid", p.label,
                        -(max(ni, 0.0) * (_drv(s, p.label, "dividend_payout_ratio") or 0.0)))
    buybacks = _set_cf(s, "buybacks", p.label, -(_drv(s, p.label, "buyback_dollars") or 0.0))
    _set_cf(s, "net_change_in_cash", p.label, fcf + debt_issued + debt_repay + dividends + buybacks)


_ASSETS_CURRENT = ["cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets"]
_ASSETS_LONG = ["ppe_net", "goodwill", "other_long_term_assets"]
_LIAB_CURRENT = ["accounts_payable", "short_term_debt", "other_current_liabilities"]
_LIAB_LONG = ["long_term_debt", "other_long_term_liabilities"]


def _period_has_override(s: ModelState, label: str) -> bool:
    for stmt in (s.income_statement, s.cash_flow, s.balance_sheet):
        for cells in stmt.values():
            cell = cells.get(label)
            if cell is not None and cell.source == "override":
                return True
    return False


def _balance_sheet_period(s: ModelState, p: Period) -> None:
    """Roll one forecast period's balance sheet from the prior period + its cash flow."""
    days = days_in_period(p)
    rev = _value(s.income_statement, "revenue", p.label) or 0.0
    cogs = _value(s.income_statement, "cost_of_revenue", p.label) or 0.0

    _set_bs(s, "accounts_receivable", p.label, rev * (_drv(s, p.label, "dso_days") or 0.0) / days)
    _set_bs(s, "inventory", p.label, cogs * (_drv(s, p.label, "dio_days") or 0.0) / days)
    _set_bs(s, "accounts_payable", p.label, cogs * (_drv(s, p.label, "dpo_days") or 0.0) / days)
    for line in ("other_current_assets", "other_current_liabilities", "other_long_term_assets",
                 "other_long_term_liabilities", "goodwill"):
        _set_bs(s, line, p.label, _bs_prior(s, line, p))

    capex = -(_value(s.cash_flow, "capex", p.label) or 0.0)
    da = _value(s.income_statement, "depreciation_amortization", p.label) or 0.0
    _set_bs(s, "ppe_net", p.label, _bs_prior(s, "ppe_net", p) + capex - da, formula="= prior + capex - D&A")

    repaid = -(_value(s.cash_flow, "debt_repaid", p.label) or 0.0)
    issued = _value(s.cash_flow, "debt_issued", p.label) or 0.0
    _set_bs(s, "long_term_debt", p.label, _bs_prior(s, "long_term_debt", p) - repaid + issued)

    ni = _value(s.income_statement, "net_income", p.label) or 0.0
    dividends = -(_value(s.cash_flow, "dividends_paid", p.label) or 0.0)
    buybacks = -(_value(s.cash_flow, "buybacks", p.label) or 0.0)
    new_re = _set_bs(s, "retained_earnings", p.label, _bs_prior(s, "retained_earnings", p) + ni - dividends,
                     formula="= prior + net income - dividends")
    ce = _set_bs(s, "common_equity", p.label, _bs_prior(s, "common_equity", p) - buybacks)

    # Cash absorbs the period's net cash flow; a revolver covers any shortfall.
    cash = _bs_prior(s, "cash_and_equivalents", p) + (_value(s.cash_flow, "net_change_in_cash", p.label) or 0.0)
    revolver = _bs_prior(s, "short_term_debt", p)
    if cash < 0:
        revolver += -cash
        cash = 0.0
    _set_bs(s, "short_term_debt", p.label, revolver)
    _set_bs(s, "cash_and_equivalents", p.label, cash)

    v = lambda line: _value(s.balance_sheet, line, p.label) or 0.0  # noqa: E731
    ca = _set_bs(s, "total_current_assets", p.label, sum(v(li) for li in _ASSETS_CURRENT))
    ta = _set_bs(s, "total_assets", p.label, ca + sum(v(li) for li in _ASSETS_LONG))
    cl = _set_bs(s, "total_current_liabilities", p.label, sum(v(li) for li in _LIAB_CURRENT))
    tl = _set_bs(s, "total_liabilities", p.label, cl + sum(v(li) for li in _LIAB_LONG))

    gap = ta - (tl + ce + new_re)
    tolerance = max(1.0, 1e-6 * abs(ta))
    if abs(gap) > tolerance:
        if not _period_has_override(s, p.label):
            raise ModelBalanceError(
                f"BS imbalance at {p.label}: assets={ta:.2f}, "
                f"liab+eq={tl + ce + new_re:.2f}, diff={gap:.2f}"
            )
        # User overrides make the statements deliberately inconsistent;
        # reconcile through retained earnings and say so on the cell.
        new_re = _set_bs(s, "retained_earnings", p.label, new_re + gap,
                         formula=f"= prior + net income - dividends + {gap:,.0f} (override reconciliation)")
    te = _set_bs(s, "total_equity", p.label, ce + new_re)
    _set_bs(s, "total_liab_and_equity", p.label, tl + te)


def recompute(state: ModelState) -> ModelState:
    """Full recompute. Idempotent: returns a deep-copied state with every
    computed cell refreshed.

    Statements are computed period by period (P&L → CF → BS, then the next
    period), because each period's interest and working-capital deltas read
    the PRIOR period's balance sheet. Computing all P&Ls, then all cash
    flows, then all balance sheets read unset forecast balances as zero —
    e.g. booking a quarter's entire receivables balance as a cash outflow.
    """
    s = deepcopy(state)
    for p in (p for p in s.periods if not p.is_historical):
        _income_statement_period(s, p)
        _cash_flow_period(s, p)
        _balance_sheet_period(s, p)
    return s


def compute_income_statement(state: ModelState) -> ModelState:
    """P&L only, all forecast periods (for tests / inspection). Exact for a
    single forecast period; multi-period models should use recompute()."""
    s = deepcopy(state)
    for p in (p for p in s.periods if not p.is_historical):
        _income_statement_period(s, p)
    return s
