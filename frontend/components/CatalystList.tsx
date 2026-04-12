/**
 * Catalyst timeline list for the ThesisCard.
 * Renders 3-5 catalyst rows with a fixed-width timeframe label on the left
 * and a description on the right.
 */

import type { Catalyst } from "@/lib/api";

export function CatalystList({ catalysts }: { catalysts: Catalyst[] }) {
  return (
    <div className="w-full">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Key Catalysts
        </span>
        <span className="flex-1 h-px bg-[var(--border)]" />
      </div>
      <div>
        {catalysts.map((c, i) => (
          <div
            key={i}
            className={`grid grid-cols-[140px_1fr] gap-3 py-2 items-baseline ${
              i > 0 ? "border-t border-[var(--border)]/50" : ""
            }`}
          >
            <span className="text-[10px] font-semibold font-mono text-[var(--primary)] uppercase">
              {c.timeframe}
            </span>
            <span className="text-[11px] text-[var(--text)] leading-snug">
              {c.description}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
