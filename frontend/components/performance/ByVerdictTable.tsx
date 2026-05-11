import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

const VERDICT_ROW_ORDER = [
  "healthy", "imminent", "triggered", "broken", "completed", "watchlist", "passed",
] as const;

export function ByVerdictTable({ summary }: { summary: OutcomeSummary }) {
  const rows = VERDICT_ROW_ORDER
    .map((v) => ({ verdict: v, stats: summary.by_verdict[v] }))
    .filter((r) => r.stats && r.stats.n > 0);

  if (rows.length === 0) {
    return <div className="px-4 py-6 text-[var(--text-muted)]">No outcomes in window.</div>;
  }

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">By verdict</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Band</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean return</th>
            <th className="py-1 font-normal text-right">Excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
            <th className="py-1 font-normal text-right">Median excess</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ verdict, stats }) => (
            <tr key={verdict} className="border-t border-[var(--border)]">
              <td className="py-1">{verdict === "passed" ? "pass" : verdict}</td>
              <td className="py-1 text-right">{stats!.n}</td>
              <td className="py-1 text-right"><ReturnCell value={stats!.mean_return_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.win_rate} asPercent /></td>
              <td className="py-1 text-right"><ReturnCell value={stats!.median_excess_pct} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
