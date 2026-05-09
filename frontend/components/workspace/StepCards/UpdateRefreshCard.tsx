"use client";
import type { UpdateRefreshOutput } from "@/lib/api";

export function UpdateRefreshCard({ output }: { output: UpdateRefreshOutput }) {
  const grouped = groupByStatement(output.changed_cells);

  return (
    <div className="space-y-3 mt-2">
      <p className="text-sm text-[var(--text)]">{output.summary}</p>

      <div className="text-xs text-[var(--text-muted)]">
        v{output.version_before} → v{output.version_after ?? "—"} · {output.changed_cells.length} cells changed · {output.new_filings.length} new filings
      </div>

      {output.new_filings.length > 0 && (
        <div className="text-xs text-[var(--text-muted)]">
          New filings:{" "}
          {output.new_filings
            .map((f) => `${f.form} ${f.accession}`)
            .join(", ")}
        </div>
      )}

      <div className="space-y-2">
        {(["income_statement", "balance_sheet", "cash_flow", "drivers", "assumptions"] as const).map(
          (sec) => {
            const rows = grouped[sec] || [];
            if (rows.length === 0) return null;

            return (
              <details
                key={sec}
                className="rounded border border-[var(--border)] bg-[var(--surface)] p-2"
              >
                <summary className="cursor-pointer text-sm font-medium text-[var(--text)] hover:text-[var(--primary)]">
                  {sec} ({rows.length})
                </summary>
                <table className="mt-2 w-full text-xs text-[var(--text)]">
                  <thead>
                    <tr className="border-b border-[var(--border)]">
                      <th className="text-left py-1 px-1 font-semibold text-[var(--text-muted)]">cell</th>
                      <th className="text-right py-1 px-1 font-semibold text-[var(--text-muted)]">prior</th>
                      <th className="text-right py-1 px-1 font-semibold text-[var(--text-muted)]">new</th>
                      <th className="text-right py-1 px-1 font-semibold text-[var(--text-muted)]">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.cell_path} className="border-b border-[var(--border)]">
                        <td className="font-mono py-1 px-1">{r.cell_path}</td>
                        <td className="text-right py-1 px-1">{fmt(r.prior_value)}</td>
                        <td className="text-right py-1 px-1">{fmt(r.new_value)}</td>
                        <td className="text-right py-1 px-1 font-medium">{fmtDelta(r.prior_value, r.new_value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            );
          }
        )}
      </div>
    </div>
  );
}

function groupByStatement(
  cells: UpdateRefreshOutput["changed_cells"]
): Record<string, UpdateRefreshOutput["changed_cells"]> {
  const groups: Record<string, UpdateRefreshOutput["changed_cells"]> = {};
  for (const c of cells) {
    const top = c.cell_path.split(".")[0] || "other";
    (groups[top] ||= []).push(c);
  }
  return groups;
}

function fmt(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function fmtDelta(a: number | null, b: number | null): string {
  if (a == null || b == null || a === 0) return "—";
  const delta = ((b - a) / Math.abs(a)) * 100;
  return `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`;
}
