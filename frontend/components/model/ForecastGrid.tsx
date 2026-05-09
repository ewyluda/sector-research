"use client";
import type { ModelState } from "@/lib/api";
import { CellRenderer } from "./CellRenderer";

const PNL_LINES = ["revenue", "cost_of_revenue", "gross_profit", "sga", "rd", "other_opex", "operating_expenses",
                   "ebit", "depreciation_amortization", "ebitda", "interest_income", "interest_expense",
                   "pretax_income", "income_tax", "net_income", "shares_diluted", "eps_diluted"];
const BS_LINES = ["cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
                  "total_current_assets", "ppe_net", "goodwill", "other_long_term_assets", "total_assets",
                  "accounts_payable", "short_term_debt", "other_current_liabilities", "total_current_liabilities",
                  "long_term_debt", "other_long_term_liabilities", "total_liabilities",
                  "common_equity", "retained_earnings", "total_equity", "total_liab_and_equity"];
const CF_LINES = ["net_income_cf", "depreciation_amortization_cf", "delta_accounts_receivable",
                  "delta_inventory", "delta_accounts_payable", "operating_cash_flow", "capex",
                  "free_cash_flow", "debt_issued", "debt_repaid", "dividends_paid", "buybacks", "net_change_in_cash"];

function StmtTable({ title, lines, stmt, state, focused, onFocus, onEdit }: {
  title: string; lines: string[]; stmt: "income_statement" | "balance_sheet" | "cash_flow";
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (path: string, v: number | null) => Promise<void>;
}) {
  return (
    <div className="mb-6">
      <h2 className="px-6 py-1 text-sm font-semibold text-[var(--text)] sticky top-0 bg-[var(--surface)] border-b border-[var(--border)] z-10">{title}</h2>
      <div className="overflow-x-auto">
        <table className="border-collapse w-max">
          <thead>
            <tr>
              <th className="sticky left-0 bg-[var(--surface)] text-left text-xs text-[var(--text-muted)] px-6 py-1 border-b border-[var(--border)]">Line item</th>
              {state.periods.map((p) => (
                <th key={p.label} className={`text-right text-xs px-2 py-1 border-b border-[var(--border)] ${p.is_historical ? "text-[var(--text-faint)]" : "text-[var(--text-muted)]"}`}>
                  {p.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((li) => (
              <tr key={li} className="border-t border-[var(--border)]">
                <td className="sticky left-0 bg-[var(--surface)] text-left text-xs text-[var(--text)] px-6 py-1">{li}</td>
                {state.periods.map((p) => {
                  const path = `${stmt}.${li}.${p.label}`;
                  return <CellRenderer key={path} cell={state[stmt][li]?.[p.label]} cellPath={path}
                                       focused={focused === path} onFocus={onFocus} onCommitEdit={onEdit}
                                       editable={!p.is_historical} />;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ForecastGrid({
  state, focused, onFocus, onEdit,
}: {
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (path: string, v: number | null) => Promise<void>;
}) {
  return (
    <div className="pt-3">
      <StmtTable title="Income Statement" lines={PNL_LINES} stmt="income_statement" state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
      <StmtTable title="Balance Sheet"     lines={BS_LINES}  stmt="balance_sheet"   state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
      <StmtTable title="Cash Flow"         lines={CF_LINES}  stmt="cash_flow"       state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
    </div>
  );
}
