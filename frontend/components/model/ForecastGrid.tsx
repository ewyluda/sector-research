"use client";
import type { ModelState } from "@/lib/api";
import { statementPath, toWire, type Statement } from "@/lib/cellPath";
import { PNL_LINES, BS_LINES, CF_LINES } from "@/lib/modelVocab";
import { CellRenderer } from "./CellRenderer";

function StmtTable({ title, lines, stmt, state, focused, onFocus, onEdit }: {
  title: string; lines: string[]; stmt: Statement;
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
                  const path = toWire(statementPath(stmt, li, p.label));
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
