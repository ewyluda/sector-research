import type { WorkspaceVerdict } from "@/lib/api";

// Uses app CSS variable tokens to match the warm light palette.
const PALETTE: Record<WorkspaceVerdict, string> = {
  healthy:   "bg-[var(--accent-bg)] text-[var(--success)] border-[var(--success)]",
  imminent:  "bg-[var(--accent-bg)] text-[var(--primary)] border-[var(--primary)]",
  triggered: "bg-[var(--accent-bg)] text-[var(--warning)] border-[var(--warning)]",
  broken:    "bg-[var(--error-bg)] text-[var(--error)] border-[var(--error-border)]",
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
