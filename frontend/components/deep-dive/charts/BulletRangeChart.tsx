"use client";

interface BulletRangeChartProps {
  low: number;
  high: number;
  current: number;
  dcfTarget?: number | null;
}

export function BulletRangeChart({ low, high, current, dcfTarget }: BulletRangeChartProps) {
  const range = high - low || 1;
  const currentPct = ((current - low) / range) * 100;
  const dcfPct = dcfTarget != null ? ((dcfTarget - low) / range) * 100 : null;

  return (
    <div className="space-y-2">
      <div className="relative h-8 rounded-full bg-[var(--color-surface-alt)] overflow-hidden">
        <div className="absolute inset-y-0 left-0 right-0 bg-gradient-to-r from-red-500/20 via-amber-500/20 to-emerald-500/20 rounded-full" />
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-[var(--color-primary)]"
          style={{ left: `${Math.min(Math.max(currentPct, 0), 100)}%` }}
        >
          <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] font-mono text-[var(--color-primary)] whitespace-nowrap">
            ${current.toFixed(0)}
          </div>
        </div>
        {dcfPct != null && dcfTarget != null && (
          <div
            className="absolute top-0 bottom-0 w-0.5 border-l border-dashed border-emerald-400"
            style={{ left: `${Math.min(Math.max(dcfPct, 0), 100)}%` }}
          >
            <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-mono text-emerald-400 whitespace-nowrap">
              DCF ${dcfTarget.toFixed(0)}
            </div>
          </div>
        )}
      </div>
      <div className="flex justify-between text-[9px] text-[var(--color-text-muted)] font-mono">
        <span>52W Low: ${low.toFixed(0)}</span>
        <span>52W High: ${high.toFixed(0)}</span>
      </div>
    </div>
  );
}
