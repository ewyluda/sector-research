"""Historical statements → model cells, and driver defaults from history. Pure.

One mapping from FMP /stable/ quarterly statements to the model's line items,
shared by baseline seeding and the workspace refresh so they can't drift.
The balance sheet is seeded completely: "other" buckets are residuals against
FMP's reported totals, so every seeded quarter balances exactly and the
forecast roll-forward starts from a real opening position. (Before, only two
non-line-item keys were seeded and a retained-earnings plug hid the gap.)
"""
from __future__ import annotations

from typing import Any

from backend.app.models.model_state import ModelCell, ModelState
from backend.app.services.model_periods import calendar_quarter_label


def _f(row: dict | None, *keys: str) -> float:
    """First present numeric field among `keys`, else 0.0."""
    for k in keys:
        v = (row or {}).get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def map_fmp_quarter(inc: dict | None, bs: dict | None, cf: dict | None) -> dict[str, dict[str, float]]:
    """Model line items for one reported quarter, keyed by statement."""
    out: dict[str, dict[str, float]] = {"income_statement": {}, "balance_sheet": {}, "cash_flow": {}}
    if inc:
        rev = _f(inc, "revenue")
        gp = _f(inc, "grossProfit")
        sga = _f(inc, "sellingGeneralAndAdministrativeExpenses")
        rd = _f(inc, "researchAndDevelopmentExpenses")
        da = _f(cf, "depreciationAndAmortization") or _f(inc, "depreciationAndAmortization")
        ebit = _f(inc, "operatingIncome")
        # The model's identity is EBIT = GP - (SG&A + R&D + other) - D&A.
        # Companies report D&A inside cost of revenue or inside operating
        # expenses, so "other" is the residual that reproduces REPORTED
        # operating income either way. (Taking operatingExpenses - SG&A - R&D
        # double-counted D&A where it sits in opex: CoreWeave's EBITDA
        # margin came out -3% instead of ~55%.)
        other = gp - ebit - sga - rd - da
        opex = sga + rd + other
        out["income_statement"] = {
            "revenue": rev,
            "cost_of_revenue": _f(inc, "costOfRevenue") or rev - gp,
            "gross_profit": gp,
            "sga": sga,
            "rd": rd,
            "other_opex": other,
            "operating_expenses": opex,
            "depreciation_amortization": da,
            "ebit": ebit,
            # Same identity as the forecast (EBIT + D&A). FMP's own "ebitda"
            # can include non-operating items (CORZ: warrant revaluations put
            # it at -$1.1B against -$72M EBIT).
            "ebitda": ebit + da,
            "interest_income": _f(inc, "interestIncome"),
            "interest_expense": _f(inc, "interestExpense"),
            "pretax_income": _f(inc, "incomeBeforeTax"),
            "income_tax": _f(inc, "incomeTaxExpense"),
            "net_income": _f(inc, "netIncome"),
            "shares_diluted": _f(inc, "weightedAverageShsOutDil", "weightedAverageShsOut"),
            "eps_diluted": _f(inc, "epsDiluted", "eps"),
        }
    if bs:
        # Cash includes short-term investments so net debt reflects liquidity.
        cash = _f(bs, "cashAndShortTermInvestments", "cashAndCashEquivalents")
        ar = _f(bs, "netReceivables", "accountsReceivables")
        inv = _f(bs, "inventory")
        tca = _f(bs, "totalCurrentAssets")
        ppe = _f(bs, "propertyPlantEquipmentNet")
        gw = _f(bs, "goodwillAndIntangibleAssets")
        ta = _f(bs, "totalAssets")
        ap = _f(bs, "accountPayables")
        std = _f(bs, "shortTermDebt")
        tcl = _f(bs, "totalCurrentLiabilities")
        ltd = _f(bs, "longTermDebt")
        tl = _f(bs, "totalLiabilities")
        re = _f(bs, "retainedEarnings")
        te = ta - tl  # forces the seeded quarter to balance (minority interest folds in)
        out["balance_sheet"] = {
            "cash_and_equivalents": cash,
            "accounts_receivable": ar,
            "inventory": inv,
            "other_current_assets": tca - cash - ar - inv,
            "total_current_assets": tca,
            "ppe_net": ppe,
            "goodwill": gw,
            "other_long_term_assets": ta - tca - ppe - gw,
            "total_assets": ta,
            "accounts_payable": ap,
            "short_term_debt": std,
            "other_current_liabilities": tcl - ap - std,
            "total_current_liabilities": tcl,
            "long_term_debt": ltd,
            "other_long_term_liabilities": tl - tcl - ltd,
            "total_liabilities": tl,
            "common_equity": te - re,
            "retained_earnings": re,
            "total_equity": te,
            "total_liab_and_equity": tl + te,
        }
    if cf:
        out["cash_flow"] = {
            "net_income_cf": _f(cf, "netIncome"),
            "depreciation_amortization_cf": _f(cf, "depreciationAndAmortization"),
            "delta_accounts_receivable": _f(cf, "accountsReceivables"),
            "delta_inventory": _f(cf, "inventory"),
            "delta_accounts_payable": _f(cf, "accountsPayables"),
            "operating_cash_flow": _f(cf, "operatingCashFlow", "netCashProvidedByOperatingActivities"),
            "capex": _f(cf, "capitalExpenditure"),
            "free_cash_flow": _f(cf, "freeCashFlow"),
            "debt_issued": max(_f(cf, "netDebtIssuance"), 0.0),
            "debt_repaid": min(_f(cf, "netDebtIssuance"), 0.0),
            "dividends_paid": _f(cf, "commonDividendsPaid", "netDividendsPaid"),
            "buybacks": _f(cf, "commonStockRepurchased"),
            "net_change_in_cash": _f(cf, "netChangeInCash"),
        }
    return out


def rows_by_quarter(
    income: list[dict], balance: list[dict], cashflow: list[dict],
) -> dict[str, tuple[dict | None, dict | None, dict | None]]:
    """Group FMP rows by calendar-quarter label (from each row's period-end date)."""
    grouped: dict[str, list[dict | None]] = {}
    for idx, rows in enumerate((income, balance, cashflow)):
        for row in rows or []:
            if not isinstance(row, dict) or not row.get("date"):
                continue
            label = calendar_quarter_label(row["date"])
            grouped.setdefault(label, [None, None, None])[idx] = row
    return {k: (v[0], v[1], v[2]) for k, v in grouped.items()}


def seed_history(state: ModelState, quarters: dict[str, tuple[dict | None, dict | None, dict | None]]) -> None:
    """Write mapped actuals into every historical period present in `quarters`."""
    for p in state.periods:
        if not p.is_historical or p.label not in quarters:
            continue
        mapped = map_fmp_quarter(*quarters[p.label])
        for stmt_name, lines in mapped.items():
            stmt = getattr(state, stmt_name)
            for line, value in lines.items():
                stmt.setdefault(line, {})[p.label] = ModelCell(
                    value=value, source="historical", last_edited_by="system",
                )


def _hist_values(state: ModelState, stmt: str, line: str) -> list[float]:
    """Historical values for a line, oldest first (missing cells skipped)."""
    cells = getattr(state, stmt).get(line, {})
    return [cells[p.label].value for p in state.periods
            if p.is_historical and p.label in cells and cells[p.label].value is not None]


def _ttm(values: list[float]) -> float:
    return sum(values[-4:]) if len(values) >= 4 else 0.0


def _bounded(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def historical_driver_defaults(state: ModelState, *, statutory_tax: float = 0.21) -> dict[str, tuple[float, str]]:
    """Annual driver values implied by the last four reported quarters (TTM).

    Fills any driver the AI baseline leaves out, so the forecast never runs on
    silent zeros (0% tax, 0 DSO). Returns {driver_key: (value, note)}.
    """
    inc = lambda line: _hist_values(state, "income_statement", line)  # noqa: E731
    bsv = lambda line: _hist_values(state, "balance_sheet", line)  # noqa: E731
    cfv = lambda line: _hist_values(state, "cash_flow", line)  # noqa: E731

    rev_q = inc("revenue")
    rev, cogs = _ttm(rev_q), _ttm(inc("cost_of_revenue"))
    out: dict[str, tuple[float, str]] = {}
    if rev <= 0:
        return out

    def ratio(line: str, stmt=inc) -> float:
        return _ttm(stmt(line)) / rev

    if len(rev_q) >= 8 and sum(rev_q[-8:-4]) > 0:
        out["revenue_growth_pct"] = (rev / sum(rev_q[-8:-4]) - 1.0, "TTM revenue vs prior TTM")
    out["gross_margin_pct"] = (ratio("gross_profit"), "TTM gross margin")
    out["sga_pct_revenue"] = (ratio("sga"), "TTM SG&A / revenue")
    out["rd_pct_revenue"] = (ratio("rd"), "TTM R&D / revenue")
    out["other_opex_pct_revenue"] = (ratio("other_opex"), "TTM other opex / revenue")
    out["da_pct_revenue"] = (ratio("depreciation_amortization"), "TTM D&A / revenue")
    out["capex_pct_revenue"] = (-ratio("capex", cfv), "TTM capex / revenue")

    pretax, tax = _ttm(inc("pretax_income")), _ttm(inc("income_tax"))
    rate = tax / pretax if pretax > 0 else statutory_tax
    out["effective_tax_rate"] = (_bounded(rate, 0.0, 0.40), "TTM tax / pretax (bounded 0–40%)")

    cash, debt = bsv("cash_and_equivalents"), [s + lt for s, lt in zip(bsv("short_term_debt"), bsv("long_term_debt"))]
    avg_cash = sum(cash[-4:]) / len(cash[-4:]) if cash else 0.0
    avg_debt = sum(debt[-4:]) / len(debt[-4:]) if debt else 0.0
    out["interest_income_yield"] = (
        _bounded(_ttm(inc("interest_income")) / avg_cash, 0.0, 0.08) if avg_cash > 0 else 0.0,
        "TTM interest income / average cash",
    )
    ie_rate = _bounded(_ttm(inc("interest_expense")) / avg_debt, 0.0, 0.15) if avg_debt > 0 else 0.0
    out["interest_expense_rate"] = (ie_rate, "TTM interest expense / average debt")
    out["revolver_rate"] = (max(ie_rate, 0.06), "max(interest expense rate, 6%)")

    last = lambda xs: xs[-1] if xs else 0.0  # noqa: E731
    out["dso_days"] = (last(bsv("accounts_receivable")) / rev * 365.0, "AR / TTM revenue × 365")
    if cogs > 0:
        out["dio_days"] = (last(bsv("inventory")) / cogs * 365.0, "inventory / TTM COGS × 365")
        out["dpo_days"] = (last(bsv("accounts_payable")) / cogs * 365.0, "AP / TTM COGS × 365")

    ni = _ttm(inc("net_income"))
    divs = -_ttm(cfv("dividends_paid"))
    out["dividend_payout_ratio"] = (_bounded(divs / ni, 0.0, 1.5) if ni > 0 else 0.0, "TTM dividends / net income")
    out["buyback_dollars"] = (max(-_ttm(cfv("buybacks")), 0.0), "TTM buybacks (annual $)")
    shares = inc("shares_diluted")
    if len(shares) >= 5 and shares[-5] > 0:
        out["share_count_change_pct"] = (shares[-1] / shares[-5] - 1.0, "diluted shares vs 4 quarters ago")
    out["debt_repayment_dollars"] = (0.0, "no scheduled repayment assumed")
    return out


# Annual driver → quarterly driver. Rates of change compound (de-compound them),
# annual dollar amounts split evenly, everything else (margins, days, annual
# interest rates, YoY revenue growth) carries over unchanged.
_COMPOUNDING = {"share_count_change_pct"}
_DOLLARS = {"buyback_dollars", "debt_repayment_dollars", "revenue_absolute"}


def annual_to_quarterly(key: str, value: float | None) -> float | None:
    if value is None:
        return None
    if key in _COMPOUNDING:
        return (1.0 + value) ** 0.25 - 1.0
    if key in _DOLLARS:
        return value / 4.0
    return value


def summarize_history(state: ModelState) -> list[dict[str, Any]]:
    """Compact per-quarter rows for the AI seeding prompt."""
    rows = []
    for p in state.periods:
        if not p.is_historical:
            continue
        def v(stmt: str, line: str) -> float | None:
            cell = getattr(state, stmt).get(line, {}).get(p.label)
            return cell.value if cell else None
        rows.append({
            "period": p.label,
            "revenue": v("income_statement", "revenue"),
            "gross_profit": v("income_statement", "gross_profit"),
            "ebit": v("income_statement", "ebit"),
            "net_income": v("income_statement", "net_income"),
            "free_cash_flow": v("cash_flow", "free_cash_flow"),
            "shares_diluted": v("income_statement", "shares_diluted"),
        })
    return rows
