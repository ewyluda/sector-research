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
      <div className="text-sm text-slate-400 mt-2 italic">
        No peer comp data available.
      </div>
    );
  }

  const metrics = ["pe", "ev_ebitda", "p_b", "p_fcf", "p_s", "roe", "revenue_yoy", "eps_yoy", "gross_margin", "ebitda_margin"] as const;

  return (
    <div className="space-y-4 mt-2">
      {/* Peer Comp Table */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-200">Peer Comparison</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-slate-300 border-collapse">
            <thead>
              <tr className="border-b border-slate-700 sticky top-0 bg-slate-900">
                <th className="sticky left-0 bg-slate-900 text-left py-1 px-2 font-semibold text-slate-400 z-10">Ticker</th>
                {metrics.map((m) => (
                  <th key={m} className="text-right py-1 px-2 font-semibold text-slate-400">
                    {m.replace(/_/g, "\n")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {/* Focus row */}
              <tr className="border-b border-slate-800 bg-slate-900/50 font-bold">
                <td className="sticky left-0 bg-slate-900/50 text-left py-1 px-2 text-slate-100 z-10">
                  {peer_comp.focus_ticker}
                </td>
                {metrics.map((m) => (
                  <td key={m} className="text-right py-1 px-2 text-slate-100">
                    {fmt(peer_comp.rows.find((r) => r.ticker === peer_comp.focus_ticker)?.[m] ?? null)}
                  </td>
                ))}
              </tr>

              {/* Peer rows */}
              {peer_comp.rows
                .filter((r) => r.ticker !== peer_comp.focus_ticker)
                .map((row, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="sticky left-0 bg-slate-900 text-left py-1 px-2 text-slate-200 z-10">
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
              <tr className="border-b border-slate-700 bg-slate-900/30">
                <td className="sticky left-0 bg-slate-900/30 text-left py-1 px-2 text-slate-400 font-medium z-10">
                  Median
                </td>
                {metrics.map((m) => (
                  <td key={m} className="text-right py-1 px-2 text-slate-400">
                    {fmt(peer_comp.median[m])}
                  </td>
                ))}
              </tr>

              {/* Delta vs Median row */}
              <tr className="border-b border-slate-700">
                <td className="sticky left-0 bg-slate-900 text-left py-1 px-2 text-slate-400 font-medium z-10">
                  Δ vs Median %
                </td>
                {metrics.map((m) => {
                  const delta = peer_comp.delta_vs_median_pct[m];
                  const deltaColor = delta === null ? "text-slate-400" : delta > 0 ? "text-emerald-400" : "text-red-400";
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
          <h3 className="text-sm font-semibold text-slate-200">Read-throughs</h3>
          <ul className="space-y-1">
            {read_throughs.map((rt, i) => (
              <li key={i} className="text-sm text-slate-300">
                <span className="text-xs px-1 rounded mr-2 bg-slate-800 text-slate-400">
                  {rt.event_key ?? rt.summary ?? "read-through"}
                </span>
                {rt.summary && <span className="text-slate-400">{rt.summary}</span>}
                {!rt.summary && rt.event_key && <span className="text-slate-400">{rt.event_key}</span>}
                {!rt.summary && !rt.event_key && (
                  <code className="text-xs text-slate-500 block mt-1">{JSON.stringify(rt)}</code>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Per-peer errors */}
      {per_peer_errors.length > 0 && (
        <details className="rounded border border-slate-700 bg-slate-900/50 p-2">
          <summary className="text-sm font-medium text-slate-200 hover:text-slate-100 cursor-pointer">
            Per-peer errors ({per_peer_errors.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {per_peer_errors.map((e, i) => (
              <li key={i} className="text-xs text-slate-300">
                <span className="font-mono text-slate-400">{e.peer_ticker}</span>:{" "}
                <span className="text-red-400">{e.error_message}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
