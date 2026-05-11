import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function HeroBand({ summary }: { summary: OutcomeSummary }) {
  const { overall, benchmark } = summary;
  const benchLabel = benchmark === "spy" ? "SPY" : benchmark === "sector" ? "Sector ETF" : "Theme basket";

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">
        Lifetime IRR — vs {benchLabel} · {summary.window} window · {summary.snapshot_offset} snapshot
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Tile label="Mean return" value={overall.mean_return_pct} />
        <Tile label="Excess vs benchmark" value={overall.mean_excess_pct} highlight />
        <Tile label="Win rate" value={overall.win_rate} asPercent />
      </div>
      <div className="mt-3 text-sm text-[var(--text-muted)]">
        N = {overall.n} · Median excess: <ReturnCell value={overall.median_excess_pct} />
      </div>
    </section>
  );
}

function Tile({
  label, value, highlight = false, asPercent = true,
}: {
  label: string;
  value: number | null;
  highlight?: boolean;
  asPercent?: boolean;
}) {
  return (
    <div className={"p-4 rounded " + (highlight ? "bg-[var(--surface-2)]" : "bg-[var(--surface)]")}>
      <div className="text-xs text-[var(--text-muted)]">{label}</div>
      <div className="text-2xl font-semibold mt-1">
        <ReturnCell value={value} asPercent={asPercent} />
      </div>
    </div>
  );
}
