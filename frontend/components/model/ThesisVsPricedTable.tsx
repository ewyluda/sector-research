"use client";
import type { ReverseDcfResponse } from "@/lib/api";

export const NO_SOLUTION_NOTE = "no solution at the current price (solver did not converge)";

export function ThesisVsPricedTable({
  rows,
  showFootnote = true,
}: {
  rows: ReverseDcfResponse["thesis_vs_priced_in"];
  showFootnote?: boolean;
}) {
  const hasNulls = rows.some((r) => r.priced_in == null || r.delta == null);
  return (
    <>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-[var(--text-muted)] text-xs">
            <th className="text-left px-2 py-1">Dimension</th>
            <th className="text-right px-2 py-1">Thesis</th>
            <th className="text-right px-2 py-1">Priced in</th>
            <th className="text-right px-2 py-1">&Delta;</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.dimension} className="border-t border-[var(--border)]">
              <td className="text-left px-2 py-1 text-[var(--text)]">{r.dimension}</td>
              <td className="text-right px-2 py-1 text-[var(--text)]">{r.thesis.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
              <td className="text-right px-2 py-1 text-[var(--text)]" title={r.priced_in == null ? NO_SOLUTION_NOTE : undefined}>
                {r.priced_in?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
              </td>
              <td
                className={`text-right px-2 py-1 ${r.delta == null ? "text-[var(--text-muted)]" : r.delta > 0 ? "text-[var(--success)]" : "text-[var(--error)]"}`}
                title={r.delta == null ? NO_SOLUTION_NOTE : undefined}
              >
                {r.delta?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {showFootnote && hasNulls && (
        <p className="mt-1 text-xs text-[var(--text-muted)]">— = {NO_SOLUTION_NOTE}</p>
      )}
    </>
  );
}
