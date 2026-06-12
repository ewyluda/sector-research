"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";

/**
 * Shared workspace kick-off: route to the in-flight run if one exists,
 * otherwise POST a new run and route to it. Extracted from the three
 * identical closures in WorkspaceButton / ReportHeader / RetryRunButton.
 */
export function useWorkspaceKickoff(opts: {
  ticker: string;
  researchRunId?: string | null;
  inFlightRunId?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const { ticker, researchRunId, inFlightRunId } = opts;

  const kickOff = useCallback(async () => {
    if (inFlightRunId) {
      router.push(`/workspace/${inFlightRunId}`);
      return;
    }
    setBusy(true);
    try {
      const { run_id } = await workspaceApi.kickOff(
        ticker,
        researchRunId ?? undefined,
      );
      router.push(`/workspace/${run_id}`);
    } catch (err) {
      alert(`Workspace kick-off failed: ${err instanceof Error ? err.message : err}`);
    } finally {
      setBusy(false);
    }
  }, [ticker, researchRunId, inFlightRunId, router]);

  return { kickOff, busy };
}
