"use client";

/**
 * Catalyst timeline list for the ThesisCard.
 * Renders 3-5 catalyst rows. Each row shows:
 *   - timeframe label (left, fixed width)
 *   - description (right)
 *   - type badge (small pill, color-coded by type)
 *   - signposts (revealed by an inline expand toggle)
 *   - linked_pillar chip (hover lifts state to highlight the bull/bear card)
 */

import { useState } from "react";
import type { Catalyst, CatalystType } from "@/lib/api";

const TYPE_COLORS: Record<CatalystType, string> = {
  earnings:   "bg-[var(--primary)]/10 text-[var(--primary)] border-[var(--primary)]/30",
  product:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  regulatory: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  m_and_a:    "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  macro:      "bg-[var(--text-muted)]/10 text-[var(--text-muted)] border-[var(--text-muted)]/30",
  other:      "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]",
};

const TYPE_LABELS: Record<CatalystType, string> = {
  earnings:   "EARNINGS",
  product:    "PRODUCT",
  regulatory: "REGULATORY",
  m_and_a:    "M&A",
  macro:      "MACRO",
  other:      "OTHER",
};

export function CatalystList({
  catalysts,
  onPillarHover,
}: {
  catalysts: Catalyst[];
  onPillarHover?: (pillar: string | null) => void;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="w-full">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Key Catalysts
        </span>
        <span className="flex-1 h-px bg-[var(--border)]" />
      </div>
      <div>
        {catalysts.map((c, i) => {
          const hasSignposts = (c.signposts ?? []).length > 0;
          const isOpen = expanded.has(i);
          return (
            <div
              key={i}
              className={`grid grid-cols-[140px_1fr] gap-3 py-2 items-baseline ${
                i > 0 ? "border-t border-[var(--border)]/50" : ""
              }`}
            >
              <span className="text-[10px] font-semibold font-mono text-[var(--primary)] uppercase">
                {c.timeframe}
              </span>
              <div className="flex flex-col gap-1.5">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[11px] text-[var(--text)] leading-snug">
                    {c.description}
                  </span>
                  {c.type && (
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${TYPE_COLORS[c.type]}`}>
                      {TYPE_LABELS[c.type]}
                    </span>
                  )}
                  {c.linked_pillar && onPillarHover && (
                    <button
                      type="button"
                      onMouseEnter={() => onPillarHover(c.linked_pillar ?? null)}
                      onMouseLeave={() => onPillarHover(null)}
                      onFocus={() => onPillarHover(c.linked_pillar ?? null)}
                      onBlur={() => onPillarHover(null)}
                      className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--surface-alt)] cursor-default"
                    >
                      tests {c.linked_pillar}
                    </button>
                  )}
                  {hasSignposts && (
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={`catalyst-signposts-${i}`}
                      onClick={() => toggle(i)}
                      className="text-[9px] font-mono text-[var(--text-faint)] hover:text-[var(--primary)] underline-offset-2"
                    >
                      {isOpen ? "− signposts" : `+ ${(c.signposts ?? []).length} signpost${(c.signposts ?? []).length === 1 ? "" : "s"}`}
                    </button>
                  )}
                </div>
                {hasSignposts && isOpen && (
                  <ul id={`catalyst-signposts-${i}`} className="ml-3 list-disc text-[10px] text-[var(--text-muted)] leading-relaxed">
                    {(c.signposts ?? []).map((s, j) => (
                      <li key={j}>{s}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
