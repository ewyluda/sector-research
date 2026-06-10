"use client";

import type { JournalSummary, TradeDetail } from "@/lib/api";
import { ReturnCell } from "@/components/performance/ReturnCell";

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div className="text-sm font-semibold">{children}</div>
    </div>
  );
}

export function DecisionVsOutcomePanel({
  summary,
  trades,
}: {
  summary: JournalSummary;
  trades: TradeDetail[];
}) {
  const compared = trades.filter((t) => t.comparison != null);
  return (
    <div className="mb-4 space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Stat label="Hit rate (vs SPY)">
          {summary.hit_rate == null ? "—" : `${(summary.hit_rate * 100).toFixed(0)}%`}
        </Stat>
        <Stat label="Avg excess">
          <ReturnCell value={summary.avg_spy_excess_pct} />
        </Stat>
        <Stat label="Execution vs paper">
          {summary.execution_vs_paper.n === 0 ? (
            "—"
          ) : (
            <ReturnCell value={summary.execution_vs_paper.avg_delta_pct} />
          )}
        </Stat>
        <Stat label="Theses traded">
          {summary.coverage.outcomes_total === 0
            ? "—"
            : `${summary.coverage.outcomes_traded}/${summary.coverage.outcomes_total}`}
        </Stat>
      </div>

      {compared.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-2 py-1">Ticker</th>
                <th className="px-2 py-1 text-right">Trade return</th>
                <th className="px-2 py-1 text-right">Trade vs SPY</th>
                <th className="px-2 py-1 text-right">Paper</th>
                <th className="px-2 py-1 text-right">Paper vs SPY</th>
                <th className="px-2 py-1 text-right">Execution Δ</th>
              </tr>
            </thead>
            <tbody>
              {compared.map((t) => (
                <tr key={t.id} className="border-t border-[var(--border)]">
                  <td className="px-2 py-1.5 font-semibold">{t.ticker}</td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.trade_return_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.trade_spy_excess_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.paper_return_pct} />
                    <span className="ml-1 text-[10px] text-[var(--text-muted)]">
                      @{t.comparison!.offset}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.paper_spy_excess_pct} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <ReturnCell value={t.comparison!.execution_delta_pct} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
