"use client";

interface BetaGaugeProps {
  beta: number;
}

export function BetaGauge({ beta }: BetaGaugeProps) {
  const max = 2.5;
  const pct = Math.min(beta / max, 1) * 100;
  const label = beta < 0.8 ? "Low Sensitivity" : beta <= 1.2 ? "Moderate" : "High Sensitivity";
  const color = beta < 0.8 ? "text-emerald-400" : beta <= 1.2 ? "text-amber-400" : "text-red-400";

  return (
    <div className="space-y-1.5">
      <div className="relative h-5 rounded-full overflow-hidden flex">
        <div className="h-full bg-emerald-500/20" style={{ width: `${(0.8 / max) * 100}%` }} />
        <div className="h-full bg-amber-500/20" style={{ width: `${(0.4 / max) * 100}%` }} />
        <div className="h-full bg-red-500/20 flex-1" />
        <div
          className="absolute top-0 bottom-0 w-1 bg-[var(--color-text-primary)] rounded-full"
          style={{ left: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between items-center">
        <span className={`text-xs font-medium ${color}`}>{label}</span>
        <span className="text-xs font-mono text-[var(--color-text-muted)]">Beta: {beta.toFixed(2)}</span>
      </div>
    </div>
  );
}
