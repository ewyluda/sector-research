"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";

const CTA: Record<string, { label: string; href: (t: string) => string }> = {
  unsaved_model_draft: { label: "Save or discard draft →", href: (t) => `/model/${t}#forecast` },
};

export function WorkspaceButton({ ticker, researchRunId }: { ticker: string; researchRunId: string }) {
  const router = useRouter();
  const { status: preflight, reasons } = useWorkspacePreflight(ticker, researchRunId);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const blockedCode = preflight && !preflight.ok ? preflight.missing[0] : null;
  const cta = blockedCode ? CTA[blockedCode] : null;
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button
        type="button"
        disabled={!canKickOff}
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
        className="rounded bg-[var(--surface-alt)] px-2 py-0.5 text-[11px] text-[var(--text-muted)] ring-1 ring-[var(--border)] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        ↻ Workspace
      </button>
      {!canKickOff && reasons.length > 0 && (
        <span className="text-[10px] text-[var(--text-faint)]" onClick={(e) => e.stopPropagation()}>
          {reasons[0]}{" "}
          {cta && (
            <Link href={cta.href(ticker)} className="text-[var(--primary-dk)] hover:underline">
              {cta.label}
            </Link>
          )}
        </span>
      )}
    </span>
  );
}
