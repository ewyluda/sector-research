"use client";

/**
 * Proximity-bucketed catalyst calendar. Renders five sections (this week,
 * next 30 days, next 90 days, later, untimed) using CatalystRow. Empty
 * sections collapse so a ticker with only one upcoming catalyst doesn't
 * scroll past four blank headers.
 */

import type { CatalystBuckets, CatalystRow as CatalystRowT } from "@/lib/api";
import { CatalystRow } from "@/components/CatalystRow";

const SECTIONS: Array<{ key: keyof CatalystBuckets; label: string }> = [
  { key: "this_week", label: "This week" },
  { key: "next_30d",  label: "Next 30 days" },
  { key: "next_90d",  label: "Next 90 days" },
  { key: "later",     label: "Later" },
  { key: "untimed",   label: "Untimed" },
];

export function CatalystCalendar({ buckets, emptyMessage }: { buckets: CatalystBuckets; emptyMessage?: string }) {
  const total =
    buckets.this_week.length +
    buckets.next_30d.length +
    buckets.next_90d.length +
    buckets.later.length +
    buckets.untimed.length;

  if (total === 0) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <p className="text-xs text-[var(--text-muted)]">
          {emptyMessage ?? "No catalysts yet. Run a thesis to populate the calendar."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {SECTIONS.map(({ key, label }) => {
        const rows: CatalystRowT[] = buckets[key];
        if (rows.length === 0) return null;
        return (
          <section key={key}>
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
                {label} · {rows.length}
              </span>
              <span className="flex-1 h-px bg-[var(--border)]" />
            </div>
            <div>
              {rows.map((r) => <CatalystRow key={r.id} row={r} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
