import type { OverviewStatGroup } from "@/lib/api";
import { formatStat } from "./formatStat";

export function StatisticsGrid({ groups }: { groups: OverviewStatGroup[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {groups.map((g) => (
        <div key={g.title} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {g.title}
          </h3>
          <dl className="space-y-1">
            {g.items.map((it) => (
              <div key={it.label} className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-[var(--text-muted)]">{it.label}</dt>
                <dd className="font-mono text-sm tabular-nums text-[var(--text)]">
                  {formatStat(it.value, it.unit)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
