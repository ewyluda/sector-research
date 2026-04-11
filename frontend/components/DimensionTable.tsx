/**
 * 5-row dimension table used by QuickScreenCard (and reusable for future
 * Deep Dive category rendering).
 *
 * Data-driven: iterates whatever dimensions array it receives. Bar color
 * varies by score/max_score ratio so the visual reads the same whether the
 * max is 20 (current) or changes in a future schema revision.
 *
 * Uses globals.css tokens: --text, --text-muted, --text-faint, --border,
 * --success (emerald), --warning (amber/rust), --error (magenta/red).
 */

import type { QuickScreenDimension } from "@/lib/api";

function barColor(ratio: number): string {
  if (ratio >= 0.75) return "var(--success)";
  if (ratio >= 0.5) return "var(--warning)";
  return "var(--error)";
}

export function DimensionTable({
  dimensions,
}: {
  dimensions: QuickScreenDimension[];
}) {
  return (
    <div className="w-full">
      <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
        Dimension Breakdown
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] font-medium">
            <th className="text-left font-medium py-1.5 w-[22%]">Dimension</th>
            <th className="text-left font-medium py-1.5 w-[22%]">Score</th>
            <th className="text-left font-medium py-1.5">Rationale</th>
          </tr>
        </thead>
        <tbody>
          {dimensions.map((d) => {
            const ratio = d.max_score > 0 ? d.score / d.max_score : 0;
            const pct = Math.max(0, Math.min(100, ratio * 100));
            return (
              <tr
                key={d.name}
                className="border-t border-[var(--border)] align-middle"
              >
                <td className="py-2 text-xs font-semibold text-[var(--text)]">
                  {d.name}
                </td>
                <td className="py-2 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${pct}%`,
                          background: barColor(ratio),
                        }}
                      />
                    </div>
                    <span className="text-xs font-mono font-semibold text-[var(--text)] tabular-nums">
                      {d.score}
                    </span>
                  </div>
                </td>
                <td className="py-2 text-xs text-[var(--text-muted)] leading-snug">
                  {d.rationale}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
