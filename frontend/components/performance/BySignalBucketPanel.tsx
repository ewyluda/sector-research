"use client";

import { useState } from "react";
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function BySignalBucketPanel({ summary }: { summary: OutcomeSummary }) {
  const signals = Object.keys(summary.by_signal_bucket);
  const [active, setActive] = useState<string | null>(signals[0] ?? null);

  if (signals.length === 0) {
    return null;
  }

  const buckets = active ? summary.by_signal_bucket[active] ?? [] : [];

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)]">By signal bucket</h2>
        <div className="flex gap-1">
          {signals.map((sig) => (
            <button
              key={sig}
              type="button"
              onClick={() => setActive(sig)}
              className={
                "px-2 py-1 text-xs rounded " +
                (sig === active
                  ? "bg-[var(--primary)] text-white"
                  : "bg-[var(--surface)] text-[var(--text)] hover:bg-[var(--surface-2)]")
              }
            >
              {sig}
            </button>
          ))}
        </div>
      </div>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Quartile</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((b) => (
            <tr key={b.bucket} className="border-t border-[var(--border)]">
              <td className="py-1">{b.bucket}</td>
              <td className="py-1 text-right">{b.n}</td>
              <td className="py-1 text-right"><ReturnCell value={b.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={b.win_rate} asPercent /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
