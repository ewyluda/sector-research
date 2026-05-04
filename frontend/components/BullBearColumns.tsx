/**
 * Two-column renderer for bull vs bear thesis points.
 * Left column: olive-tinted cards (--success) for bull case.
 * Right column: magenta-tinted cards (--error) for bear case.
 * Variable-length: handles 2-5 items per side.
 *
 * highlightedPillar: when set to "bull:N" or "bear:N" (1-indexed), the matching
 * card receives a ring/glow. Used by chip-hover handlers in CatalystList and
 * the kill-criteria list inside ThesisCard.
 */

import type { ThesisPoint } from "@/lib/api";

function PointCard({
  point,
  variant,
  highlighted,
}: {
  point: ThesisPoint;
  variant: "bull" | "bear";
  highlighted: boolean;
}) {
  const bg =
    variant === "bull"
      ? "bg-[var(--success)]/4 border-[var(--success)]/22"
      : "bg-[var(--error)]/4 border-[var(--error)]/22";

  const ring = highlighted
    ? variant === "bull"
      ? "ring-2 ring-[var(--success)]/60 shadow-lg shadow-[var(--success)]/10"
      : "ring-2 ring-[var(--error)]/60 shadow-lg shadow-[var(--error)]/10"
    : "";

  return (
    <div className={`rounded-md border p-2.5 transition-shadow duration-150 ${bg} ${ring}`}>
      <div className="text-[11px] font-semibold text-[var(--text)] leading-snug">
        {point.title}
      </div>
      <div className="text-[10px] text-[var(--text-muted)] mt-1 leading-relaxed">
        {point.evidence}
      </div>
    </div>
  );
}

export function BullBearColumns({
  bull,
  bear,
  highlightedPillar = null,
}: {
  bull: ThesisPoint[];
  bear: ThesisPoint[];
  highlightedPillar?: string | null;
}) {
  const matched = highlightedPillar?.match(/^(bull|bear):(\d+)$/);
  const highlightSide = (matched?.[1] ?? null) as "bull" | "bear" | null;
  const highlightIndex = matched ? Number(matched[2]) - 1 : -1;

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)]" />
          <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--success)]">
            Bull Case
          </span>
        </div>
        {bull.map((p, i) => (
          <PointCard
            key={i}
            point={p}
            variant="bull"
            highlighted={highlightSide === "bull" && highlightIndex === i}
          />
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--error)]" />
          <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--error)]">
            Bear Case
          </span>
        </div>
        {bear.map((p, i) => (
          <PointCard
            key={i}
            point={p}
            variant="bear"
            highlighted={highlightSide === "bear" && highlightIndex === i}
          />
        ))}
      </div>
    </div>
  );
}
