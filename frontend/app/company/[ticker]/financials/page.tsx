"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getCompanyFinancials } from "@/lib/api";
import type { CompanyFinancials } from "@/lib/api";
import { StatementTable } from "@/components/company/StatementTable";
import { INCOME_SPEC, BALANCE_SPEC, CASHFLOW_SPEC } from "@/components/company/statementRows";
import type { Unit } from "@/components/company/fmtFinancial";

type StmtKey = "income" | "balance" | "cashflow";
const STATEMENTS: { key: StmtKey; label: string }[] = [
  { key: "income", label: "Income Statement" },
  { key: "balance", label: "Balance Sheet" },
  { key: "cashflow", label: "Cash Flow" },
];
const SPECS = { income: INCOME_SPEC, balance: BALANCE_SPEC, cashflow: CASHFLOW_SPEC };

export default function FinancialsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  const [period, setPeriod] = useState<"annual" | "quarter">("quarter");
  const [stmt, setStmt] = useState<StmtKey>("income");
  const [unit, setUnit] = useState<Unit>("M");
  const [pctChg, setPctChg] = useState(false);
  const [commonSize, setCommonSize] = useState(false);
  const [fin, setFin] = useState<CompanyFinancials | null | undefined>(null);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    getCompanyFinancials(ticker, period)
      .then((f) => { if (alive) setFin(f); })
      .catch(() => { if (alive) setFin(undefined); });
    return () => { alive = false; };
  }, [ticker, period]);

  const spec = SPECS[stmt];
  const commonSizeDisabled = spec.baseKey == null;

  return (
    <div className="space-y-3">
      <div className="flex gap-1 border-b border-[var(--border)]">
        {STATEMENTS.map((s) => (
          <button
            key={s.key}
            onClick={() => setStmt(s.key)}
            className={`px-3 py-2 text-sm transition-colors ${
              stmt === s.key
                ? "border-b-2 border-[var(--primary)] font-medium text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 text-xs">
        <Toggle options={[["quarter", "Quarterly"], ["annual", "Annual"]]} value={period} onChange={(v) => setPeriod(v as "annual" | "quarter")} />
        <Toggle options={[["K", "K"], ["M", "M"], ["B", "B"]]} value={unit} onChange={(v) => setUnit(v as Unit)} />
        <label className="flex items-center gap-1 text-[var(--text-muted)]">
          <input type="checkbox" checked={pctChg} onChange={(e) => setPctChg(e.target.checked)} /> % Chg
        </label>
        <label className={`flex items-center gap-1 ${commonSizeDisabled ? "opacity-40" : "text-[var(--text-muted)]"}`}>
          <input type="checkbox" checked={commonSize && !commonSizeDisabled} disabled={commonSizeDisabled} onChange={(e) => setCommonSize(e.target.checked)} /> Common Size
        </label>
      </div>

      {fin === null ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Loading financials…</div>
      ) : fin === undefined ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Could not load financials.</div>
      ) : (
        <StatementTable
          periods={fin.periods}
          data={fin[stmt]}
          spec={spec}
          unit={unit}
          pctChg={pctChg}
          commonSize={commonSize && !commonSizeDisabled}
        />
      )}
    </div>
  );
}

function Toggle({ options, value, onChange }: { options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex gap-0.5 rounded-md border border-[var(--border)] p-0.5">
      {options.map(([val, label]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          className={`rounded px-2 py-0.5 transition-colors ${
            value === val ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]" : "text-[var(--text-muted)] hover:text-[var(--text)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
