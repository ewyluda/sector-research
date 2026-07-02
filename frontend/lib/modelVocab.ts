/**
 * Canonical financial-model cell vocabulary for the frontend grid.
 *
 * Single source of truth on the frontend: ForecastGrid (line items) and
 * DriverPanel (drivers) both read from here instead of each hardcoding their
 * own copy.
 *
 * These arrays MIRROR the backend registries in
 * backend/app/models/model_state.py (DRIVER_KEYS, LINE_ITEMS_PNL/BS/CF). The
 * grid renders one row per entry and then looks the value up in the model
 * state, so a key here the backend doesn't emit — or a backend key missing
 * here — silently produces an empty/absent row (a renamed driver only surfaces
 * when a PUT /draft 422s at runtime). `modelVocab.test.mts` pins these against
 * the backend so drift fails CI instead of shipping a blank column.
 */

export const PNL_LINES: string[] = [
  "revenue", "cost_of_revenue", "gross_profit",
  "sga", "rd", "other_opex", "operating_expenses",
  "ebit", "depreciation_amortization", "ebitda",
  "interest_income", "interest_expense", "pretax_income",
  "income_tax", "net_income",
  "shares_diluted", "eps_diluted",
];

export const BS_LINES: string[] = [
  "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
  "total_current_assets",
  "ppe_net", "goodwill", "other_long_term_assets", "total_assets",
  "accounts_payable", "short_term_debt", "other_current_liabilities",
  "total_current_liabilities",
  "long_term_debt", "other_long_term_liabilities", "total_liabilities",
  "common_equity", "retained_earnings", "total_equity",
  "total_liab_and_equity",
];

export const CF_LINES: string[] = [
  "net_income_cf", "depreciation_amortization_cf",
  "delta_accounts_receivable", "delta_inventory", "delta_accounts_payable",
  "operating_cash_flow",
  "capex", "free_cash_flow",
  "debt_issued", "debt_repaid",
  "dividends_paid", "buybacks",
  "net_change_in_cash",
];

/**
 * Drivers, grouped for the DriverPanel's labelled sections. The flattened key
 * set (DRIVER_KEYS below) must equal the backend DRIVER_KEYS in both membership
 * and order — the parity test pins the flattened array.
 */
export const DRIVER_GROUPS: Array<{ label: string; keys: string[] }> = [
  { label: "Revenue", keys: ["revenue_growth_pct", "revenue_absolute"] },
  { label: "Margins", keys: ["gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue", "other_opex_pct_revenue", "da_pct_revenue"] },
  { label: "Below the line", keys: ["effective_tax_rate", "interest_income_yield", "interest_expense_rate"] },
  { label: "Capex / WC", keys: ["capex_pct_revenue", "dso_days", "dio_days", "dpo_days"] },
  { label: "Capital return", keys: ["dividend_payout_ratio", "buyback_dollars", "share_count_change_pct"] },
  { label: "Debt", keys: ["debt_repayment_dollars", "revolver_rate"] },
];

export const DRIVER_KEYS: string[] = DRIVER_GROUPS.flatMap((g) => g.keys);
