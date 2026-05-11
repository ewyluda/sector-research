"use client";

import Link from "next/link";
import type { OutcomeListItem } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function OutcomeList({ outcomes }: { outcomes: OutcomeListItem[] }) {
  if (outcomes.length === 0) {
    return <div className="px-4 py-6 text-[var(--text-muted)]">No outcomes match the current filters.</div>;
  }

  return (
    <section className="px-4 py-6">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">Outcomes</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Ticker</th>
            <th className="py-1 font-normal">Verdict</th>
            <th className="py-1 font-normal">Emitted</th>
            <th className="py-1 font-normal">Status</th>
            <th className="py-1 font-normal text-right">+1m</th>
            <th className="py-1 font-normal text-right">+3m</th>
            <th className="py-1 font-normal text-right">+6m</th>
            <th className="py-1 font-normal text-right">Realized</th>
          </tr>
        </thead>
        <tbody>
          {outcomes.map((o) => {
            const byOffset = Object.fromEntries(o.snapshots.map((s) => [s.snapshot_offset, s]));
            const status =
              o.closed_at ? "closed"
              : o.superseded_at ? "superseded"
              : "open";
            const href =
              o.source_type === "research_run"
                ? `/pipeline/${o.source_id}`
                : `/workspace/${o.source_id}`;
            return (
              <tr key={o.id} className="border-t border-[var(--border)] hover:bg-[var(--surface-2)]">
                <td className="py-1"><Link href={href} className="hover:underline">{o.ticker}</Link></td>
                <td className="py-1">{o.verdict}</td>
                <td className="py-1">{o.verdict_emitted_at.slice(0, 10)}</td>
                <td className="py-1">{status}</td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["1m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["3m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={byOffset["6m"]?.spy_excess_pct ?? null} /></td>
                <td className="py-1 text-right"><ReturnCell value={o.realized_spy_excess_pct} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
