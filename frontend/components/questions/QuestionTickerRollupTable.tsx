"use client";

import Link from "next/link";
import type { QuestionTickerRollup } from "@/lib/api";

interface Props {
  rollup: QuestionTickerRollup[];
}

export function QuestionTickerRollupTable({ rollup }: Props) {
  if (rollup.length === 0) {
    return <p className="text-[var(--text-faint)] text-sm">No open questions across the fleet.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-left text-[var(--text-muted)] border-b border-[var(--surface)]">
        <tr>
          <th className="py-2 pr-4">Ticker</th>
          <th className="py-2 px-3 text-right">P1</th>
          <th className="py-2 px-3 text-right">P2</th>
          <th className="py-2 px-3 text-right">P3</th>
          <th className="py-2 px-3 text-right">Total open</th>
        </tr>
      </thead>
      <tbody>
        {rollup.map((row) => (
          <tr
            key={row.ticker}
            className="border-b border-[var(--bg)] hover:bg-[var(--bg)]/40"
          >
            <td className="py-2 pr-4">
              <Link
                href={`/questions?ticker=${row.ticker}`}
                className="text-emerald-300 hover:underline font-mono"
              >
                {row.ticker}
              </Link>
            </td>
            <td className="py-2 px-3 text-right">
              {row.p1_count > 0 ? (
                <span className="text-rose-300 font-semibold">{row.p1_count}</span>
              ) : (
                <span className="text-slate-600">0</span>
              )}
            </td>
            <td className="py-2 px-3 text-right">
              {row.p2_count > 0 ? (
                <span className="text-amber-300">{row.p2_count}</span>
              ) : (
                <span className="text-slate-600">0</span>
              )}
            </td>
            <td className="py-2 px-3 text-right text-[var(--text-muted)]">{row.p3_count}</td>
            <td className="py-2 px-3 text-right text-[var(--text)] font-semibold">{row.open_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
