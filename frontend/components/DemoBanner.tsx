import { DEMO } from "@/lib/api/core";

/** Shown only in the read-only demo build (NEXT_PUBLIC_DEMO=1). */
export function DemoBanner() {
  if (!DEMO) return null;
  return (
    <div data-print-hide="true" className="bg-[var(--surface-alt)] border-b border-[var(--border)] text-xs text-[var(--text-muted)] px-6 py-2 text-center">
      Read-only demo — data recorded from a live run on {process.env.NEXT_PUBLIC_DEMO_RECORDED ?? "a recent date"}; changes are
      disabled and some pages outside the demo path are empty. Not investment advice.{" "}
      <a href="https://github.com/ewyluda/sector-research" className="text-[var(--primary-dk)] hover:underline">
        Source and case study
      </a>
    </div>
  );
}
