"use client";

import type { DifferentiationOutput } from "@/lib/api";

function fmt(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export function DifferentiationCard({ output }: { output: DifferentiationOutput }) {
  const { peer_comp, read_throughs, per_peer_errors } = output;

  if (!peer_comp) {
    return (
      <div className="text-sm text-[var(--text-muted)] mt-2 italic">
        No peer comp data available.
      </div>
    );
  }

  const metrics = ["pe", "ev_ebitda", "p_b", "p_fcf", "p_s", "roe", "revenue_yoy", "eps_yoy", "gross_margin", "ebitda_margin"] as const;

  return (
    <div className="space-y-4 mt-2">
      {/* Peer Comp Table */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-[var(--text)]">Peer Comparison</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-[var(--text)] border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)] sticky top-0 bg-[var(--surface)]">
                <th className="sticky left-0 bg-[var(--surface)] text-left py-1 px-2 font-semibold text-[var(--text-muted)] z-10">Ticker</th>
                {metrics.map((m) => (
                  <th key={m} className="text-right py-1 px-2 font-semibold text-[var(--text-muted)]">
                    {m.replace(/_/g, "\n")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Focus row */}
              <tr className="border-b border-[var(--border)] bg-[var(--accent-bg)] font-bold">
                <td className="sticky left-0 bg-[var(--accent-bg)] text-left py-1 px-2 text-[var(--primary)] z-10">
                  {peer_comp.focus_ticker}
                </td>
                {metrics.map((m) => (
                  <td key={m} className="text-right py-1 px-2 text-[var(--text)]">
                    {fmt(peer_comp.rows.find((r) => r.ticker === peer_comp.focus_ticker)?.[m] ?? null)}
                  </td>
                ))}
              </tr>

              {/* Peer rows */}
              {peer_comp.rows
                .filter((r) => r.ticker !== peer_comp.focus_ticker)
                .map((row, i) => (
                  <tr key={i} className="border-b border-[var(--border)]">
                    <td className="sticky left-0 bg-[var(--surface)] text-left py-1 px-2 text-[var(--text)] z-10">
                      {row.ticker}
                    </td>
                    {metrics.map((m) => (
                      <td key={m} className="text-right py-1 px-2">
                        {fmt(row[m])}
                      </td>
                    ))}
                  </tr>
                ))}

              {/* Median row */}
              <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)]">
                <td className="sticky left-0 bg-[var(--surface-alt)] text-left py-1 px-2 text-[var(--text-muted)] font-medium z-10">
                  Median
                </td>
                {metrics.map((m) => (
                  <td key={m} className="text-right py-1 px-2 text-[var(--text-muted)]">
                    {fmt(peer_comp.median[m])}
                  </td>
                ))}
              </tr>

              {/* Delta vs Median row */}
              <tr className="border-b border-[var(--border)]">
                <td className="sticky left-0 bg-[var(--surface)] text-left py-1 px-2 text-[var(--text-muted)] font-medium z-10">
                  Δ vs Median %
                </td>
                {metrics.map((m) => {
                  const delta = peer_comp.delta_vs_median_pct[m];
                  const deltaColor = delta === null ? "text-[var(--text-muted)]" : delta > 0 ? "text-[var(--success)]" : "text-[var(--error)]";
                  return (
                    <td key={m} className={`text-right py-1 px-2 ${deltaColor}`}>
                      {delta === null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}%`}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Read-throughs */}
      {read_throughs.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-[var(--text)]">Read-throughs</h3>
          <ul className="space-y-1">
            {read_throughs.map((rt, i) => (
              <li key={i} className="text-sm text-[var(--text)]">
                <span className="text-xs px-1 rounded mr-2 bg-[var(--surface-alt)] text-[var(--text-muted)]">
                  {rt.event_key ?? rt.summary ?? "read-through"}
                </span>
                {rt.summary && <span className="text-[var(--text-muted)]">{rt.summary}</span>}
                {!rt.summary && rt.event_key && <span className="text-[var(--text-muted)]">{rt.event_key}</span>}
                {!rt.summary && !rt.event_key && (
                  <code className="text-xs text-[var(--text-faint)] block mt-1">{JSON.stringify(rt)}</code>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Per-peer errors */}
      {per_peer_errors.length > 0 && (
        <details className="rounded border border-[var(--border)] bg-[var(--surface)] p-2">
          <summary className="text-sm font-medium text-[var(--text)] hover:text-[var(--primary)] cursor-pointer">
            Per-peer errors ({per_peer_errors.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {per_peer_errors.map((e, i) => (
              <li key={i} className="text-xs text-[var(--text)]">
                <span className="font-mono text-[var(--text-muted)]">{e.peer_ticker}</span>:{" "}
                <span className="text-[var(--error)]">{e.error_message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
