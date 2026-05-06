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


def _set_cf(state: ModelState, line: str, period: str, value: float) -> None:
    state.cash_flow.setdefault(line, {})[period] = ModelCell(value=value, source="computed")


def _set_bs(state: ModelState, line: str, period: str, value: float) -> None:
    state.balance_sheet.setdefault(line, {})[period] = ModelCell(value=value, source="computed")


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

        ocf = ni + da + d_ar + d_inv + d_ap
        fcf = ocf + capex

        debt_repay = -(_drv(s, p.label, "debt_repayment_dollars") or 0.0)
        buybacks = -(_drv(s, p.label, "buyback_dollars") or 0.0)
        payout = _drv(s, p.label, "dividend_payout_ratio") or 0.0
        dividends = -(ni * payout)

        net_change = fcf + debt_repay + buybacks + dividends

        _set_cf(s, "net_income_cf", p.label, ni)
        _set_cf(s, "depreciation_amortization_cf", p.label, da)
        _set_cf(s, "delta_accounts_receivable", p.label, d_ar)
        _set_cf(s, "delta_inventory", p.label, d_inv)
        _set_cf(s, "delta_accounts_payable", p.label, d_ap)
        _set_cf(s, "operating_cash_flow", p.label, ocf)
        _set_cf(s, "capex", p.label, capex)
        _set_cf(s, "free_cash_flow", p.label, fcf)
        _set_cf(s, "debt_issued", p.label, 0.0)
        _set_cf(s, "debt_repaid", p.label, debt_repay)
        _set_cf(s, "dividends_paid", p.label, dividends)
        _set_cf(s, "buybacks", p.label, buybacks)
        _set_cf(s, "net_change_in_cash", p.label, net_change)
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
        ppe = _bs_prior(s, "ppe_net", idx) + capex - da
        _set_bs(s, "ppe_net", p.label, ppe)

        # Debt
        prior_lt = _bs_prior(s, "long_term_debt", idx)
        debt_repay = (_drv(s, p.label, "debt_repayment_dollars") or 0.0)
        new_lt = max(0.0, prior_lt - debt_repay)
        _set_bs(s, "long_term_debt", p.label, new_lt)

        # Equity
        prior_re = _bs_prior(s, "retained_earnings", idx)
        ni = s.income_statement["net_income"][p.label].value or 0.0
        dividends = -(s.cash_flow["dividends_paid"][p.label].value or 0.0)  # negative cash, positive distribution
        new_re = prior_re + ni - dividends
        _set_bs(s, "retained_earnings", p.label, new_re)
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
        _set_bs(s, "total_current_assets", p.label, ca)
        ta = ca + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "ppe_net", "goodwill", "other_long_term_assets",
        ])
        _set_bs(s, "total_assets", p.label, ta)
        cl = sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "accounts_payable", "short_term_debt", "other_current_liabilities",
        ])
        _set_bs(s, "total_current_liabilities", p.label, cl)
        tl = cl + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "long_term_debt", "other_long_term_liabilities",
        ])
        _set_bs(s, "total_liabilities", p.label, tl)
        te = sum((s.balance_sheet[li][p.label].value or 0.0) for li in ["common_equity", "retained_earnings"])
        _set_bs(s, "total_equity", p.label, te)
        _set_bs(s, "total_liab_and_equity", p.label, tl + te)

        # Balance check
        if abs(ta - (tl + te)) > 1.0:
            raise ModelBalanceError(
                f"BS imbalance at {p.label}: assets={ta:.2f}, liab+eq={tl+te:.2f}, diff={ta-(tl+te):.2f}"
            )

    return s


def recompute(state: ModelState) -> ModelState:
    """Full recompute pipeline. Idempotent: produces a deep-copied new state with all computed
    cells refreshed and BS balanced."""
    s = compute_income_statement(state)
    s = compute_cash_flow(s)
    s = roll_balance_sheet(s)
    return s
