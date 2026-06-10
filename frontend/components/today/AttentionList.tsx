"use client";

import Link from "next/link";
import type { AttentionRow } from "@/lib/todayDerive";
import { WorkspaceButton } from "@/components/status/WorkspaceButton";

const ROW_BORDER: Record<AttentionRow["severity"], string> = {
  red: "border-l-red-500",
  amber: "border-l-amber-500",
  blue: "border-l-blue-500",
};

const HEALTH_LABEL: Record<string, string> = {
  broken: "Broken",
  triggered: "Triggered",
  stale: "Stale",
};

const EVENT_TYPE_LABEL: Record<string, string> = {
  guidance: "Guidance",
  personnel: "Personnel",
  ma: "M&A",
  financing: "Financing",
  other: "8-K",
};

export function AttentionList({ rows, error }: { rows: AttentionRow[]; error: string | null }) {
  return (
    <section>
      <h2 className="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wide mb-2">
        Needs attention
      </h2>

      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)] mb-1.5">
          {error}
        </div>
      )}

      {rows.length === 0 ? (
        !error && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-4 py-3 text-sm text-[var(--text-muted)]">
            All clear ✓{" "}
            <Link href="/status" className="text-[var(--primary)] hover:underline">
              View status board →
            </Link>
          </div>
        )
      ) : (
        <div className="space-y-1.5">
          {rows.map((row) =>
            row.kind === "health" ? (
              <div
                key={`health-${row.ticker}-${row.runId}`}
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2`}
              >
                <Link
                  href={`/pipeline/${row.runId}`}
                  className="font-mono font-bold text-sm text-[var(--text)] tracking-wide hover:underline shrink-0"
                >
                  {row.ticker}
                </Link>
                <span className="text-[11px] text-[var(--text-muted)] truncate shrink-0 max-w-[140px]">
                  {row.themeName}
                </span>
                <span className="text-xs text-[var(--text-muted)] truncate flex-1">
                  <span className="font-semibold text-[var(--text)]">{HEALTH_LABEL[row.health]}</span>
                  {row.health === "stale" && ` · ${row.daysSinceUpdate}d since update`}
                  {row.triggeredCriteria > 0 &&
                    ` · ${row.triggeredCriteria}/${row.totalCriteria} kill criteria triggered`}
                  {row.reasons.length > 0 && ` — ${row.reasons.join("; ")}`}
                </span>
                <span className="shrink-0" data-print-hide="true">
                  <WorkspaceButton ticker={row.ticker} researchRunId={row.runId} />
                </span>
              </div>
            ) : row.kind === "event" ? (
              <Link
                key={`event-${row.eventId}`}
                href={`/status?expand_events=${row.ticker}`}
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2 hover:bg-[var(--surface-alt)] transition-colors`}
              >
                <span className="font-mono font-bold text-sm text-[var(--text)] tracking-wide shrink-0">
                  {row.ticker}
                </span>
                <span className="text-[11px] text-[var(--text-muted)] shrink-0">
                  {EVENT_TYPE_LABEL[row.eventType] ?? "8-K"} · {row.filingDate}
                </span>
                <span className="text-xs text-[var(--text-muted)] truncate flex-1">
                  <span className="font-semibold text-[var(--text)]">8-K</span> — {row.headline}
                </span>
                <span className="text-[11px] text-[var(--primary)] shrink-0">View →</span>
              </Link>
            ) : (
              <Link
                key={`questions-${row.ticker}`}
                href="/questions"
                className={`flex items-center gap-3 rounded-lg border border-[var(--border)] border-l-[3px] ${ROW_BORDER[row.severity]} bg-[var(--surface)] px-3 py-2 hover:bg-[var(--surface-alt)] transition-colors`}
              >
                <span className="font-mono font-bold text-sm text-[var(--text)] tracking-wide shrink-0">
                  {row.ticker}
                </span>
                <span className="text-xs text-[var(--text-muted)] flex-1">
                  {row.p1Count} open P1 question{row.p1Count === 1 ? "" : "s"}
                  {row.openCount > row.p1Count && ` (${row.openCount} open total)`}
                </span>
                <span className="text-[11px] text-[var(--primary)] shrink-0">View →</span>
              </Link>
            ),
          )}
        </div>
      )}
    </section>
  );
}
