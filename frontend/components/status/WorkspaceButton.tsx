"use client";

import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";

export function WorkspaceButton({ ticker, researchRunId }: { ticker: string; researchRunId: string }) {
  const router = useRouter();
  const { status: preflight, reasons } = useWorkspacePreflight(ticker, researchRunId);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const tooltip = reasons.length > 0 ? reasons.join(" • ") : "Run workspace refresh";
  return (
    <button
      type="button"
      disabled={!canKickOff}
      title={tooltip}
      onClick={async (ev) => {
        ev.stopPropagation();
        if (inFlightRunId) {
          router.push(`/workspace/${inFlightRunId}`);
          return;
        }
        try {
          const { run_id } = await workspaceApi.kickOff(ticker, researchRunId);
          router.push(`/workspace/${run_id}`);
        } catch (err) {
          alert(`Workspace kick-off failed: ${err instanceof Error ? err.message : err}`);
        }
      }}
      className="rounded bg-slate-700/40 px-2 py-0.5 text-[11px] text-slate-300 ring-1 ring-slate-600 hover:bg-slate-700/60 hover:ring-slate-500 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-slate-700/40 disabled:hover:ring-slate-600"
    >
      ↻ Workspace
    </button>
  );
}
