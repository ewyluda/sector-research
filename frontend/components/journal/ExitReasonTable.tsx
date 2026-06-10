"use client";

import type { ExitReasonStat } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

const LABELS: Record<string, string> = {
  thesis_played_out: "Thesis played out",
  kill_criterion: "Kill criterion",
  stop_loss: "Stop loss",
  better_opportunity: "Better opportunity",
  rebalance: "Rebalance",
  mistake: "Mistake",
  other: "Other",
  unspecified: "Unspecified",
};

export function ExitReasonTable({ rows }: { rows: ExitReasonStat[] }) {
  return (
    <div className="mt-4">
      <h3 className="text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-1">
        By exit reason
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-2 py-1">Reason</th>
            <th className="px-2 py-1 text-right">Trades</th>
            <th className="px-2 py-1 text-right">Avg return</th>
            <th className="px-2 py-1 text-right">Avg vs SPY</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.exit_reason} className="border-t border-[var(--border)]">
              <td className="px-2 py-1.5">{LABELS[r.exit_reason] ?? r.exit_reason}</td>
              <td className="px-2 py-1.5 text-right">{r.count}</td>
              <td className="px-2 py-1.5 text-right">
                <ReturnCell value={r.avg_return_pct} />
              </td>
              <td className="px-2 py-1.5 text-right">
                <ReturnCell value={r.avg_spy_excess_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
