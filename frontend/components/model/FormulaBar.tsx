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
  if (!focused) return <div className="px-6 py-1 text-xs text-slate-600 border-b border-slate-900" data-print-hide="true">Click a cell to inspect.</div>;
  const cell = lookupCell(state, focused);
  return (
    <div className="px-6 py-1 text-xs text-slate-300 border-b border-slate-900 flex gap-3" data-print-hide="true">
      <span className="text-slate-500">{focused}</span>
      <span className="text-slate-400">{cell?.source ?? "—"}</span>
      <span>{cell?.value === null || cell?.value === undefined ? "—" : cell.value.toLocaleString()}</span>
      {cell?.formula && <span className="text-slate-500">· {cell.formula}</span>}
      {cell?.citation_id && <a href={`#citation-${cell.citation_id}`} className="text-blue-400 hover:underline">citation</a>}
    </div>
  );
}
