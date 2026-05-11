"use client";

import { useRouter, useSearchParams } from "next/navigation";
import type { OutcomeSummary } from "@/lib/api";
import { ReturnCell } from "./ReturnCell";

export function ByThemeTable({ summary }: { summary: OutcomeSummary }) {
  const router = useRouter();
  const sp = useSearchParams();
  const rows = [...summary.by_theme].sort((a, b) => (b.stats.n - a.stats.n));

  function pickTheme(themeId: string | null) {
    const params = new URLSearchParams(sp.toString());
    if (themeId) params.set("theme_filter", themeId);
    else params.delete("theme_filter");
    router.push(`/performance?${params.toString()}`);
  }

  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="px-4 py-6 border-b border-[var(--border)]">
      <h2 className="text-sm uppercase tracking-wide text-[var(--text-muted)] mb-3">By theme</h2>
      <table className="w-full text-sm">
        <thead className="text-[var(--text-muted)] text-left">
          <tr>
            <th className="py-1 font-normal">Theme</th>
            <th className="py-1 font-normal text-right">N</th>
            <th className="py-1 font-normal text-right">Mean return</th>
            <th className="py-1 font-normal text-right">Excess</th>
            <th className="py-1 font-normal text-right">Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r.theme_id ?? "untagged"}
              className="border-t border-[var(--border)] cursor-pointer hover:bg-[var(--surface-2)]"
              onClick={() => pickTheme(r.theme_id)}
            >
              <td className="py-1">{r.theme_name ?? <em>untagged</em>}</td>
              <td className="py-1 text-right">{r.stats.n}</td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.mean_return_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.mean_excess_pct} /></td>
              <td className="py-1 text-right"><ReturnCell value={r.stats.win_rate} asPercent /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
