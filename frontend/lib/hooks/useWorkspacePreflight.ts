"use client";
import { useEffect, useState } from "react";
import { workspaceApi, type WorkspacePreflight } from "@/lib/api";

const MISSING_COPY: Record<WorkspacePreflight["missing"][number], string> = {
  no_completed_research_run: "Needs a completed research run for this ticker.",
  research_run_not_completed: "The pinned research run hasn't completed yet.",
  research_run_ticker_mismatch: "The pinned research run doesn't match this ticker.",
  no_ticker_model: "Initialize a model for this ticker first.",
  unsaved_model_draft: "Save or discard the model draft first.",
  workspace_run_in_flight: "A workspace run is already running.",
};

export interface UsePreflightResult {
  loading: boolean;
  status: WorkspacePreflight | null;
  reasons: string[]; // human-readable copy for each missing code
}

export function useWorkspacePreflight(
  ticker: string | null | undefined,
  researchRunId?: string | null,
): UsePreflightResult {
  const [status, setStatus] = useState<WorkspacePreflight | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) {
      return;
    }
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    workspaceApi
      .preflight(ticker, researchRunId ?? undefined)
      .then((r) => {
        if (!cancelled) setStatus(r);
      })
      .catch(() => {
        // If preflight itself errors, fall back to optimistic (let kick_off
        // surface the real error). Don't block the button on transient netfails.
        if (!cancelled) setStatus({ ok: true, missing: [], in_flight_run_id: null });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, researchRunId]);

  const effectiveStatus = ticker ? status : null;
  const reasons = (effectiveStatus?.missing ?? []).map((m) => MISSING_COPY[m]);
  return { loading, status: effectiveStatus, reasons };
}
