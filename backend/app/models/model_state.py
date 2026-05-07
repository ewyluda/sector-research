"""Pydantic schemas + registries for the per-ticker financial model."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

# ---- Driver registry (~25 keys, all per-period) -----------------------------

DRIVER_KEYS: list[str] = [
    # Revenue (one of these populated per period; the other is None)
    "revenue_growth_pct", "revenue_absolute",
    # Margins
    "gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue",
    "other_opex_pct_revenue", "da_pct_revenue",
    # Below the line
    "effective_tax_rate", "interest_income_yield", "interest_expense_rate",
    # Capex / WC
    "capex_pct_revenue", "dso_days", "dio_days", "dpo_days",
    # Capital return
    "dividend_payout_ratio", "buyback_dollars", "share_count_change_pct",
    # Debt
    "debt_repayment_dollars", "revolver_rate",
]

# ---- Line item registries (mirror FMP statement structure) ------------------

LINE_ITEMS_PNL: list[str] = [
    "revenue", "cost_of_revenue", "gross_profit",
    "sga", "rd", "other_opex", "operating_expenses",
    "ebit", "depreciation_amortization", "ebitda",
    "interest_income", "interest_expense", "pretax_income",
    "income_tax", "net_income",
    "shares_diluted", "eps_diluted",
]

LINE_ITEMS_BS: list[str] = [
    "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
    "total_current_assets",
    "ppe_net", "goodwill", "other_long_term_assets", "total_assets",
    "accounts_payable", "short_term_debt", "other_current_liabilities",
    "total_current_liabilities",
    "long_term_debt", "other_long_term_liabilities", "total_liabilities",
    "common_equity", "retained_earnings", "total_equity",
    "total_liab_and_equity",
]

LINE_ITEMS_CF: list[str] = [
    "net_income_cf", "depreciation_amortization_cf",
    "delta_accounts_receivable", "delta_inventory", "delta_accounts_payable",
    "operating_cash_flow",
    "capex", "free_cash_flow",
    "debt_issued", "debt_repaid",
    "dividends_paid", "buybacks",
    "net_change_in_cash",
]


# ---- Schemas ----------------------------------------------------------------

class Period(BaseModel):
    label: str                              # "2024Q1", "2026"
    kind: Literal["Q", "Y"]
    is_historical: bool
    quarter_index: int | None = None        # 1-4 for Q, None for Y


CellSource = Literal["historical", "ai_baseline", "driver", "computed", "override"]


class ModelCell(BaseModel):
    value: float | None = None
    source: CellSource = "computed"
    formula: str | None = None
    citation_id: str | None = None
    last_edited_at: str | None = None        # ISO
    last_edited_by: Literal["system", "ai_baseline", "user"] | None = None


class ModelAssumptions(BaseModel):
    discount_rate: ModelCell
    terminal_method: Literal["exit_multiple", "perpetuity"]
    terminal_multiple: ModelCell
    perpetuity_growth: ModelCell
    tax_rate: ModelCell
    plug_priority: list[Literal["debt_paydown", "buyback", "dividend", "cash"]] = Field(
        default_factory=lambda: ["debt_paydown", "buyback", "dividend", "cash"]
    )


class ModelState(BaseModel):
    periods: list[Period]
    drivers: dict[str, dict[str, ModelCell]]            # {period_label: {driver_key: cell}}
    income_statement: dict[str, dict[str, ModelCell]]   # {line_item: {period_label: cell}}
    balance_sheet: dict[str, dict[str, ModelCell]]
    cash_flow: dict[str, dict[str, ModelCell]]
    assumptions: ModelAssumptions


# ---- Helpers used by services -----------------------------------------------

def cell_path_pnl(line_item: str, period: str) -> str:
    return f"income_statement.{line_item}.{period}"


def cell_path_bs(line_item: str, period: str) -> str:
    return f"balance_sheet.{line_item}.{period}"


def cell_path_cf(line_item: str, period: str) -> str:
    return f"cash_flow.{line_item}.{period}"


def cell_path_driver(period: str, driver_key: str) -> str:
    return f"drivers.{period}.{driver_key}"


def cell_path_assumption(key: str) -> str:
    return f"assumptions.{key}"
