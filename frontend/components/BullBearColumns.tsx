/**
 * Two-column renderer for bull vs bear thesis points.
 * Left column: olive-tinted cards (--success) for bull case.
 * Right column: magenta-tinted cards (--error) for bear case.
 * Variable-length: handles 2-5 items per side.
 */

import type { ThesisPoint } from "@/lib/api";

function PointCard({
  point,
  variant,
}: {
  point: ThesisPoint;
  variant: "bull" | "bear";
}) {
  const bg =
    variant === "bull"
      ? "bg-[var(--success)]/4 border-[var(--success)]/22"
      : "bg-[var(--error)]/4 border-[var(--error)]/22";

  return (
    <div className={`rounded-md border p-2.5 ${bg}`}>
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
}: {
  bull: ThesisPoint[];
  bear: ThesisPoint[];
}) {
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
          <PointCard key={i} point={p} variant="bull" />
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
          <PointCard key={i} point={p} variant="bear" />
        ))}
      </div>
    </div>
  );
}
