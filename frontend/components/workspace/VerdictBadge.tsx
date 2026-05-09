import type { WorkspaceVerdict } from "@/lib/api";

// Mirrors the HealthPill palette in frontend/app/status/page.tsx
const PALETTE: Record<WorkspaceVerdict, string> = {
  healthy:   "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  imminent:  "bg-blue-500/10 text-blue-400 border-blue-500/30",
  triggered: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  broken:    "bg-red-500/10 text-red-400 border-red-500/30",
};

const LABEL: Record<WorkspaceVerdict, string> = {
  healthy:   "Healthy",
  imminent:  "Imminent",
  triggered: "Triggered",
  broken:    "Broken",
};

export function VerdictBadge({ verdict }: { verdict: WorkspaceVerdict | null }) {
  if (!verdict) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-semibold bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]">
        —
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-semibold ${PALETTE[verdict]}`}
    >
      {LABEL[verdict]}
    </span>
  );
}
