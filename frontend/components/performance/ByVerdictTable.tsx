import type { OutcomeSummary, StatGroup } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

const WORKSPACE_HEALTH_SET = new Set(["healthy", "imminent", "triggered", "broken", "stale"]);
const RUN_VERDICT_ORDER = ["completed", "watchlist", "passed"] as const;
const WORKSPACE_HEALTH_ORDER = ["healthy", "imminent", "stale", "triggered", "broken"] as const;

export function ByVerdictTable({ summary }: { summary: OutcomeSummary }) {
  const runRows = RUN_VERDICT_ORDER
    .map((v) => ({ verdict: v, stats: summary.by_verdict[v] as StatGroup | null | undefined }))
    .filter((r) => r.stats && r.stats.n > 0);

  const healthRows = WORKSPACE_HEALTH_ORDER
    .map((v) => ({ verdict: v, stats: summary.by_verdict[v] as StatGroup | null | undefined }))
    .filter((r) => r.stats && r.stats.n > 0);

  // Also catch any unknown verdicts not in the predefined orders.
  const knownVerdicts = new Set<string>([...RUN_VERDICT_ORDER, ...WORKSPACE_HEALTH_ORDER]);
  const otherRunRows = Object.entries(summary.by_verdict)
    .filter(([v, s]) => !knownVerdicts.has(v) && !WORKSPACE_HEALTH_SET.has(v) && s && (s as StatGroup).n > 0)
    .map(([v, s]) => ({ verdict: v, stats: s as StatGroup }));

  const hasRunRows = runRows.length > 0 || otherRunRows.length > 0;
  const hasHealthRows = healthRows.length > 0;

  if (!hasRunRows && !hasHealthRows) {
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
          {hasRunRows && (
            <tr>
              <td colSpan={6} className="pt-3 pb-1 text-xs uppercase tracking-wide text-[var(--text-muted)] font-medium">
                Run verdict
              </td>
            </tr>
          )}
          {[...runRows, ...otherRunRows].map(({ verdict, stats }) => (
            <VerdictRow key={verdict} verdict={verdict} stats={stats!} />
          ))}
          {hasHealthRows && (
            <tr>
              <td colSpan={6} className="pt-3 pb-1 text-xs uppercase tracking-wide text-[var(--text-muted)] font-medium">
                Workspace health
              </td>
            </tr>
          )}
          {healthRows.map(({ verdict, stats }) => (
            <VerdictRow key={verdict} verdict={verdict} stats={stats!} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function VerdictRow({ verdict, stats }: { verdict: string; stats: StatGroup }) {
  return (
    <tr className="border-t border-[var(--border)]">
      <td className="py-1">{verdict === "passed" ? "pass" : verdict}</td>
      <td className="py-1 text-right">{stats.n}</td>
      <td className="py-1 text-right"><ReturnCell value={stats.mean_return_pct} /></td>
      <td className="py-1 text-right"><ReturnCell value={stats.mean_excess_pct} /></td>
      <td className="py-1 text-right"><ReturnCell value={stats.win_rate} asPercent /></td>
      <td className="py-1 text-right"><ReturnCell value={stats.median_excess_pct} /></td>
    </tr>
  );
}
