"use client";

import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";
import { useWorkspaceKickoff } from "@/lib/hooks/useWorkspaceKickoff";

/**
 * Retry button for failed workspace runs on the /workspace index.
 *
 * Mirrors the kick-off pattern in components/status/WorkspaceButton.tsx:
 * preflight gates the button (disabled + reason when blocked), an in-flight
 * run redirects instead of kicking off, and kick-off failures alert.
 * Kicks off WITHOUT a pinned research_run_id — the backend picks the latest
 * completed run for the ticker.
 */
export function RetryRunButton({ ticker }: { ticker: string }) {
  const { status: preflight, reasons } = useWorkspacePreflight(ticker);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const { kickOff } = useWorkspaceKickoff({ ticker, inFlightRunId });
  return (
    <button
      type="button"
      disabled={!canKickOff}
      title={!canKickOff && reasons.length > 0 ? reasons[0] : undefined}
      onClick={(ev) => {
        ev.stopPropagation();
        void kickOff();
      }}
      className="rounded bg-[var(--surface-alt)] px-2 py-0.5 text-[11px] text-[var(--text-muted)] ring-1 ring-[var(--border)] enabled:hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      ↻ Retry
    </button>
  );
}
