"use client";
import type { ModelState, ModelCell } from "@/lib/api";

function lookupCell(state: ModelState, path: string): ModelCell | undefined {
  const parts = path.split(".");
  if (parts[0] === "drivers" && parts.length === 3) return state.drivers[parts[1]]?.[parts[2]];
  if ((parts[0] === "income_statement" || parts[0] === "balance_sheet" || parts[0] === "cash_flow") && parts.length === 3) {
    const stmt = state[parts[0] as "income_statement" | "balance_sheet" | "cash_flow"];
    return stmt?.[parts[1]]?.[parts[2]];
  }
  if (parts[0] === "assumptions" && parts.length === 2) {
    const a = (state.assumptions as unknown as Record<string, ModelCell | unknown>)[parts[1]];
    return typeof a === "object" && a !== null && "value" in (a as ModelCell) ? (a as ModelCell) : undefined;
  }
  return undefined;
}

export function FormulaBar({ state, focused }: { state: ModelState; focused: string | null }) {
  if (!focused) return <div className="px-6 py-1 text-xs text-[var(--text-faint)] border-b border-[var(--border)] bg-[var(--surface-alt)]" data-print-hide="true">Click a cell to inspect.</div>;
  const cell = lookupCell(state, focused);
  return (
    <div className="px-6 py-1 text-xs text-[var(--text)] border-b border-[var(--border)] bg-[var(--surface-alt)] flex gap-3" data-print-hide="true">
      <span className="text-[var(--text-muted)]">{focused}</span>
      <span className="text-[var(--text-muted)]">{cell?.source ?? "—"}</span>
      <span>{cell?.value === null || cell?.value === undefined ? "—" : cell.value.toLocaleString()}</span>
      {cell?.formula && <span className="text-[var(--text-muted)]">· {cell.formula}</span>}
      {cell?.citation_id && <a href={`#citation-${cell.citation_id}`} className="text-[var(--primary)] hover:underline">citation</a>}
    </div>
  );
}
