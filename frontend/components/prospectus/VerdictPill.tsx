import type { IPOVerdict } from "@/lib/api";

const STYLES: Record<IPOVerdict, string> = {
  participate: "bg-emerald-950 text-emerald-300 border-emerald-800",
  watch_post_lockup: "bg-amber-950 text-amber-300 border-amber-800",
  pass: "bg-red-950 text-red-300 border-red-800",
};

const LABELS: Record<IPOVerdict, string> = {
  participate: "Participate",
  watch_post_lockup: "Watch post-lockup",
  pass: "Pass",
};

export function VerdictPill({ verdict }: { verdict: IPOVerdict | null | undefined }) {
  if (!verdict) {
    return (
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)]">
        Pending
      </span>
    );
  }
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full border ${STYLES[verdict]}`}>
      {LABELS[verdict]}
    </span>
  );
}
