import clsx from "clsx";
import type { XSignalSnapshot } from "@/lib/api";

interface Props {
  signal: XSignalSnapshot;
  compact?: boolean;
}

const CONFIG = {
  accelerating: {
    label: "↑ Accelerating",
    classes: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  },
  stable: {
    label: "→ Stable",
    classes: "bg-[var(--surface-alt)] text-[var(--text-muted)] border-[var(--border)]",
  },
  decelerating: {
    label: "↓ Decelerating",
    classes: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  },
  unknown: {
    label: "— No signal",
    classes: "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]",
  },
};

export default function VelocityBadge({ signal, compact = false }: Props) {
  const cfg = CONFIG[signal.direction] ?? CONFIG.unknown;
  const isStale = signal.is_stale;

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 border rounded-full font-medium",
        compact ? "text-[10px] px-2 py-0.5" : "text-xs px-2.5 py-1",
        isStale ? "opacity-40 grayscale" : cfg.classes
      )}
      title={isStale ? "Signal data stale — last updated over 36h ago" : undefined}
    >
      {cfg.label}
      {isStale && <span className="text-[9px]">(stale)</span>}
    </span>
  );
}
