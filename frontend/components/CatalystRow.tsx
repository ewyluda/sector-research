"use client";

/**
 * Single row inside the CatalystCalendar — ticker badge, type pill,
 * description, expected date, signposts toggle. Reused by both the fleet
 * page (/catalysts) and the per-ticker panel inside /pipeline/[runId].
 */

import Link from "next/link";
import { useState } from "react";
import type { CatalystRow as CatalystRowT, CatalystType } from "@/lib/api";

const TYPE_COLORS: Record<CatalystType, string> = {
  earnings:   "bg-[var(--primary)]/10 text-[var(--primary)] border-[var(--primary)]/30",
  product:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  regulatory: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  m_and_a:    "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  macro:      "bg-[var(--text-muted)]/10 text-[var(--text-muted)] border-[var(--text-muted)]/30",
  other:      "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]",
};

const TYPE_LABELS: Record<CatalystType, string> = {
  earnings:   "EARNINGS",
  product:    "PRODUCT",
  regulatory: "REGULATORY",
  m_and_a:    "M&A",
  macro:      "MACRO",
  other:      "OTHER",
};

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  // "2026-05-22" -> "May 22"
  const d = new Date(iso + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

export function CatalystRow({ row }: { row: CatalystRowT }) {
  const [open, setOpen] = useState(false);
  const hasSignposts = (row.signposts ?? []).length > 0;
  const typeClass = row.type ? TYPE_COLORS[row.type] : "";
  const typeLabel = row.type ? TYPE_LABELS[row.type] : null;
  const isFmp = row.date_source === "fmp_earnings";

  return (
    <div className="grid grid-cols-[64px_72px_1fr_72px] gap-3 items-baseline py-2 border-b border-[var(--border)]/40">
      <Link
        href={`/pipeline/${row.run_id}`}
        className="font-mono font-bold text-[var(--text)] hover:text-[var(--primary)]"
      >
        {row.ticker}
      </Link>
      <div>
        {typeLabel && (
          <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${typeClass}`}>
            {typeLabel}
          </span>
        )}
      </div>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-[11px] text-[var(--text)] leading-snug">
            {row.description}
          </span>
          {row.linked_pillar && (
            <span className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)]">
              tests {row.linked_pillar}
            </span>
          )}
          {hasSignposts && (
            <button
              type="button"
              aria-expanded={open}
              aria-controls={`catalyst-row-signposts-${row.id}`}
              onClick={() => setOpen(!open)}
              className="text-[9px] font-mono text-[var(--text-faint)] hover:text-[var(--primary)] underline-offset-2"
            >
              {open ? "− signposts" : `+ ${row.signposts.length} signpost${row.signposts.length === 1 ? "" : "s"}`}
            </button>
          )}
        </div>
        {hasSignposts && open && (
          <ul id={`catalyst-row-signposts-${row.id}`} className="ml-3 list-disc text-[10px] text-[var(--text-muted)] leading-relaxed">
            {row.signposts.map((s, j) => <li key={j}>{s}</li>)}
          </ul>
        )}
      </div>
      <div className="text-right">
        <span className={`text-[11px] font-mono ${isFmp ? "text-[var(--primary)]" : "text-[var(--text-muted)]"}`}>
          {formatDate(row.expected_date)}
        </span>
        {row.expected_date && (
          <div className="text-[8px] uppercase tracking-wider text-[var(--text-faint)]">
            {row.date_source.replace(/_/g, " ")}
          </div>
        )}
      </div>
    </div>
  );
}
