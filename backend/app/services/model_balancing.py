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


def _override_value(cell: ModelCell | None) -> float | None:
    if cell is not None and cell.source == "override" and cell.value is not None:
        return float(cell.value)
    return None


def _set_pnl(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> float:
    period_cells = state.income_statement.setdefault(line, {})
    override = _override_value(period_cells.get(period))
    if override is not None:
        return override
    period_cells[period] = ModelCell(
        value=value, source="computed", formula=formula,
    )
    return value


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
        abs_cell = s.drivers.get(p.label, {}).get("revenue_absolute")
        if abs_cell and abs_cell.value is not None:
            computed_rev = abs_cell.value
        else:
            growth = _drv(s, p.label, "revenue_growth_pct") or 0.0
            if prior_rev is None:
                raise ValueError(f"compute_income_statement: no prior revenue for {p.label}")
            # Quarterly periods: apply growth as YoY against prior_rev (simplification for v1)
            computed_rev = prior_rev * (1.0 + growth)
        rev = _set_pnl(s, "revenue", p.label, computed_rev, formula="= prior_revenue * (1 + revenue_growth_pct)")
        prior_rev = rev

        gm = _drv(s, p.label, "gross_margin_pct") or 0.0
        gp = _set_pnl(s, "gross_profit", p.label, rev * gm, formula="= revenue * gross_margin_pct")
        _set_pnl(s, "cost_of_revenue", p.label, rev - gp, formula="= revenue - gross_profit")

        sga_pct = _drv(s, p.label, "sga_pct_revenue") or 0.0
        rd_pct = _drv(s, p.label, "rd_pct_revenue") or 0.0
        other_pct = _drv(s, p.label, "other_opex_pct_revenue") or 0.0
        da_pct = _drv(s, p.label, "da_pct_revenue") or 0.0
        sga = _set_pnl(s, "sga", p.label, rev * sga_pct)
        rd = _set_pnl(s, "rd", p.label, rev * rd_pct)
        other = _set_pnl(s, "other_opex", p.label, rev * other_pct)
        opex = _set_pnl(s, "operating_expenses", p.label, sga + rd + other)
        da = _set_pnl(s, "depreciation_amortization", p.label, rev * da_pct)
        ebit = _set_pnl(s, "ebit", p.label, gp - opex - da, formula="= gross_profit - operating_expenses - da")
        _set_pnl(s, "ebitda", p.label, ebit + da, formula="= ebit + da")

        # Interest assumed 0 in v1 P&L; debt schedule lives in CF/BS step
        interest_income = _set_pnl(s, "interest_income", p.label, 0.0)
        interest_expense = _set_pnl(s, "interest_expense", p.label, 0.0)
        pretax = _set_pnl(s, "pretax_income", p.label, ebit + interest_income - interest_expense)
        tax_rate = _drv(s, p.label, "effective_tax_rate") or 0.0
        tax = _set_pnl(s, "income_tax", p.label, pretax * tax_rate)
        ni = _set_pnl(s, "net_income", p.label, pretax - tax, formula="= pretax_income - income_tax")

        # Shares: prior shares × (1 + share_count_change_pct)
        sh_change = _drv(s, p.label, "share_count_change_pct") or 0.0
        existing_sh = s.income_statement.get("shares_diluted", {}).get(p.label)
        override_sh = _override_value(existing_sh)
        if override_sh is not None:
            sh = override_sh
        else:
            idx = s.periods.index(p)
            prior_period = s.periods[idx - 1] if idx > 0 else p
            prior_sh = (s.income_statement.get("shares_diluted", {}).get(prior_period.label) or ModelCell()).value
            if prior_sh is None and existing_sh is not None:
                prior_sh = existing_sh.value
            sh = _set_pnl(s, "shares_diluted", p.label, (prior_sh or 0.0) * (1.0 + sh_change))
        _set_pnl(s, "eps_diluted", p.label, ni / sh if sh else 0.0)

    return s


def _set_cf(state: ModelState, line: str, period: str, value: float) -> float:
    period_cells = state.cash_flow.setdefault(line, {})
    override = _override_value(period_cells.get(period))
    if override is not None:
        return override
    period_cells[period] = ModelCell(value=value, source="computed")
    return value


def _set_bs(state: ModelState, line: str, period: str, value: float) -> float:
    period_cells = state.balance_sheet.setdefault(line, {})
    override = _override_value(period_cells.get(period))
    if override is not None:
        return override
    period_cells[period] = ModelCell(value=value, source="computed")
    return value


def _bs_prior(state: ModelState, line: str, period_idx: int) -> float:
    prior_period = state.periods[period_idx - 1]
    cell = state.balance_sheet.get(line, {}).get(prior_period.label)
    return (cell.value if cell else 0.0) or 0.0


def compute_cash_flow(state: ModelState) -> ModelState:
    """CF derived from P&L + WC changes + capex + financing drivers. Run after compute_income_statement."""
    s = state
    forecast = [p for p in s.periods if not p.is_historical]
    for p in forecast:
        idx = s.periods.index(p)
        ni = (s.income_statement["net_income"][p.label].value or 0.0)
        da = (s.income_statement["depreciation_amortization"][p.label].value or 0.0)
        rev = (s.income_statement["revenue"][p.label].value or 0.0)
        cogs = (s.income_statement["cost_of_revenue"][p.label].value or 0.0)

        dso = _drv(s, p.label, "dso_days") or 0.0
        dio = _drv(s, p.label, "dio_days") or 0.0
        dpo = _drv(s, p.label, "dpo_days") or 0.0

        # New AR/Inv/AP using days-driven targets
        new_ar = rev * (dso / 365.0)
        new_inv = cogs * (dio / 365.0)
        new_ap = cogs * (dpo / 365.0)

        prior_ar = _bs_prior(s, "accounts_receivable", idx)
        prior_inv = _bs_prior(s, "inventory", idx)
        prior_ap = _bs_prior(s, "accounts_payable", idx)

        d_ar = -(new_ar - prior_ar)   # AR up = cash use
        d_inv = -(new_inv - prior_inv)
        d_ap = (new_ap - prior_ap)    # AP up = cash source

        capex_pct = _drv(s, p.label, "capex_pct_revenue") or 0.0
        capex = -(rev * capex_pct)    # negative outflow

        _set_cf(s, "net_income_cf", p.label, ni)
        _set_cf(s, "depreciation_amortization_cf", p.label, da)
        d_ar = _set_cf(s, "delta_accounts_receivable", p.label, d_ar)
        d_inv = _set_cf(s, "delta_inventory", p.label, d_inv)
        d_ap = _set_cf(s, "delta_accounts_payable", p.label, d_ap)
        ocf = _set_cf(s, "operating_cash_flow", p.label, ni + da + d_ar + d_inv + d_ap)
        capex = _set_cf(s, "capex", p.label, capex)
        fcf = _set_cf(s, "free_cash_flow", p.label, ocf + capex)
        debt_issued = _set_cf(s, "debt_issued", p.label, 0.0)
        debt_repay = _set_cf(s, "debt_repaid", p.label, -(_drv(s, p.label, "debt_repayment_dollars") or 0.0))
        payout = _drv(s, p.label, "dividend_payout_ratio") or 0.0
        dividends = _set_cf(s, "dividends_paid", p.label, -(ni * payout))
        buybacks = _set_cf(s, "buybacks", p.label, -(_drv(s, p.label, "buyback_dollars") or 0.0))
        _set_cf(s, "net_change_in_cash", p.label, fcf + debt_issued + debt_repay + buybacks + dividends)
    return s


def roll_balance_sheet(state: ModelState) -> ModelState:
    """Roll BS forward from prior period + CF activity. Plug priority is honored implicitly:
    debt_repaid drains LT debt; buybacks drain cash; dividends drain cash; remainder is cash buildup.
    If FCF + financing < 0, the gap is funded by short_term_debt (revolver). v1 ignores PPE/goodwill changes
    beyond capex flowing into PPE."""
    s = state
    forecast = [p for p in s.periods if not p.is_historical]
    for p in forecast:
        idx = s.periods.index(p)
        rev = s.income_statement["revenue"][p.label].value or 0.0
        cogs = s.income_statement["cost_of_revenue"][p.label].value or 0.0

        dso = _drv(s, p.label, "dso_days") or 0.0
        dio = _drv(s, p.label, "dio_days") or 0.0
        dpo = _drv(s, p.label, "dpo_days") or 0.0

        _set_bs(s, "accounts_receivable", p.label, rev * (dso / 365.0))
        _set_bs(s, "inventory", p.label, cogs * (dio / 365.0))
        _set_bs(s, "accounts_payable", p.label, cogs * (dpo / 365.0))
        _set_bs(s, "other_current_assets", p.label, _bs_prior(s, "other_current_assets", idx))
        _set_bs(s, "other_current_liabilities", p.label, _bs_prior(s, "other_current_liabilities", idx))
        _set_bs(s, "other_long_term_assets", p.label, _bs_prior(s, "other_long_term_assets", idx))
        _set_bs(s, "other_long_term_liabilities", p.label, _bs_prior(s, "other_long_term_liabilities", idx))
        _set_bs(s, "goodwill", p.label, _bs_prior(s, "goodwill", idx))

        capex = -(s.cash_flow["capex"][p.label].value or 0.0)  # positive for PPE addition
        da = s.income_statement["depreciation_amortization"][p.label].value or 0.0
        _set_bs(s, "ppe_net", p.label, _bs_prior(s, "ppe_net", idx) + capex - da)

        # Debt
        prior_lt = _bs_prior(s, "long_term_debt", idx)
        debt_repay = (_drv(s, p.label, "debt_repayment_dollars") or 0.0)
        _set_bs(s, "long_term_debt", p.label, max(0.0, prior_lt - debt_repay))

        # Equity
        prior_re = _bs_prior(s, "retained_earnings", idx)
        ni = s.income_statement["net_income"][p.label].value or 0.0
        dividends = -(s.cash_flow["dividends_paid"][p.label].value or 0.0)  # negative cash, positive distribution
        new_re = _set_bs(s, "retained_earnings", p.label, prior_re + ni - dividends)
        prior_ce = _bs_prior(s, "common_equity", idx)
        buybacks = -(s.cash_flow["buybacks"][p.label].value or 0.0)
        _set_bs(s, "common_equity", p.label, prior_ce - buybacks)

        # Cash plug
        prior_cash = _bs_prior(s, "cash_and_equivalents", idx)
        ncf = s.cash_flow["net_change_in_cash"][p.label].value or 0.0
        new_cash = prior_cash + ncf
        prior_st = _bs_prior(s, "short_term_debt", idx)
        if new_cash < 0:
            revolver_draw = -new_cash
            new_cash = 0.0
            _set_bs(s, "short_term_debt", p.label, prior_st + revolver_draw)
        else:
            _set_bs(s, "short_term_debt", p.label, prior_st)
        _set_bs(s, "cash_and_equivalents", p.label, new_cash)

        # Totals
        ca = sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
        ])
        ca = _set_bs(s, "total_current_assets", p.label, ca)
        ta = _set_bs(s, "total_assets", p.label, ca + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "ppe_net", "goodwill", "other_long_term_assets",
        ]))
        cl = sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "accounts_payable", "short_term_debt", "other_current_liabilities",
        ])
        cl = _set_bs(s, "total_current_liabilities", p.label, cl)
        tl = _set_bs(s, "total_liabilities", p.label, cl + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "long_term_debt", "other_long_term_liabilities",
        ]))
        # Plug retained_earnings to force balance: RE absorbs any gap from
        # untracked BS items (ppe_net, goodwill, etc. seeded as 0 when
        # CuratedFinancials lacks granular BS data). This is the standard
        # 3-statement model approach.
        re_before_plug = s.balance_sheet.get("retained_earnings", {}).get(p.label)
        re_val = re_before_plug.value if re_before_plug and re_before_plug.value is not None else new_re
        ce_val = (s.balance_sheet.get("common_equity", {}).get(p.label) or ModelCell(value=0.0)).value or 0.0
        te_target = ta - tl
        re_plugged = te_target - ce_val
        re_val = _set_bs(s, "retained_earnings", p.label, re_plugged)
        te = _set_bs(s, "total_equity", p.label, ce_val + re_val)
        total_le = _set_bs(s, "total_liab_and_equity", p.label, tl + te)

        # Balance check (should always pass after plug)
        if abs(ta - total_le) > 1.0:
            raise ModelBalanceError(
                f"BS imbalance at {p.label}: assets={ta:.2f}, liab+eq={total_le:.2f}, diff={ta-total_le:.2f}"
            )

    return s


def recompute(state: ModelState) -> ModelState:
    """Full recompute pipeline. Idempotent: produces a deep-copied new state with all computed
    cells refreshed and BS balanced."""
    s = compute_income_statement(state)
    s = compute_cash_flow(s)
    s = roll_balance_sheet(s)
    return s
