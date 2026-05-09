"use client";
import { useState } from "react";
import type { ModelState } from "@/lib/api";
import { driverPath, toWire } from "@/lib/cellPath";
import { CellRenderer } from "./CellRenderer";

const GROUPS: Array<{ label: string; keys: string[] }> = [
  { label: "Revenue",       keys: ["revenue_growth_pct", "revenue_absolute"] },
  { label: "Margins",       keys: ["gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue", "other_opex_pct_revenue", "da_pct_revenue"] },
  { label: "Below the line",keys: ["effective_tax_rate", "interest_income_yield", "interest_expense_rate"] },
  { label: "Capex / WC",    keys: ["capex_pct_revenue", "dso_days", "dio_days", "dpo_days"] },
  { label: "Capital return",keys: ["dividend_payout_ratio", "buyback_dollars", "share_count_change_pct"] },
  { label: "Debt",          keys: ["debt_repayment_dollars", "revolver_rate"] },
];

export function DriverPanel({
  state, focused, onFocus, onEdit,
}: {
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (cellPath: string, value: number | null) => Promise<void>;
}) {
  const periods = state.periods.filter((p) => !p.is_historical);
  const [open, setOpen] = useState(true);
  return (
    <section className="border-b border-[var(--border)] bg-[var(--surface)]">
      <button onClick={() => setOpen(!open)} className="w-full text-left px-6 py-2 text-sm text-[var(--text-muted)] hover:text-[var(--text)]">
        {open ? "▾" : "▸"} Drivers
      </button>
      {open && (
        <div className="px-6 pb-3 overflow-x-auto">
          {GROUPS.map((g) => (
            <div key={g.label} className="mb-3">
              <div className="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">{g.label}</div>
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs text-[var(--text-muted)] pr-2 py-0.5">Driver</th>
                    {periods.map((p) => <th key={p.label} className="text-right text-xs text-[var(--text-muted)] px-1 py-0.5">{p.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {g.keys.map((k) => (
                    <tr key={k} className="border-t border-[var(--border)]">
                      <td className="text-left text-xs text-[var(--text)] pr-2 py-0.5">{k}</td>
                      {periods.map((p) => {
                        const path = toWire(driverPath(p.label, k));
                        return <CellRenderer key={path} cell={state.drivers[p.label]?.[k]} cellPath={path}
                                             focused={focused === path} onFocus={onFocus} onCommitEdit={onEdit} />;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
