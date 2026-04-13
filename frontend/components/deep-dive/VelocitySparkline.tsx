import type { XSignalVelocity } from "@/lib/api";

const DIRECTION_CONFIG = {
  accelerating: { label: "Accelerating", color: "text-emerald-400", bg: "bg-emerald-500/10", arrow: "↑" },
  stable: { label: "Stable", color: "text-amber-400", bg: "bg-amber-500/10", arrow: "→" },
  decelerating: { label: "Decelerating", color: "text-red-400", bg: "bg-red-500/10", arrow: "↓" },
} as const;

interface VelocitySparklineProps {
  velocity: XSignalVelocity;
}

export function VelocitySparkline({ velocity }: VelocitySparklineProps) {
  if (!velocity.direction || velocity.ratio == null) return null;

  const config = DIRECTION_CONFIG[velocity.direction];
  const ratioDisplay = velocity.ratio.toFixed(2);

  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full ${config.bg}`}>
      <span className={`text-xs font-semibold ${config.color}`}>{config.arrow}</span>
      <span className={`text-[10px] font-mono font-medium ${config.color}`}>
        {ratioDisplay}x
      </span>
      {velocity.is_stale && (
        <span className="text-[9px] text-[var(--color-text-faint)]" title="Signal data is stale (>36h old)">stale</span>
      )}
    </div>
  );
}
