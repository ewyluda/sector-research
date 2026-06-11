"use client";

import { useEffect, useState } from "react";
import {
  pipeline as pipelineApi,
  killCriteria as killCriteriaApi,
  type KillCriterion,
  type KillCriterionStateOut,
} from "@/lib/api";

interface Props {
  runId: string;
  /** Called after a successful toggle so the board can refresh the KC chip. */
  onToggled?: () => void;
}

/**
 * Inline-expand drawer for the status board (same pattern as
 * ReadThroughDrawer / MaterialEventsDrawer). Fetches the run report once on
 * mount for the criteria text + persisted states, then toggles individual
 * criteria armed ↔ triggered via PUT /api/runs/{id}/kill-criteria/{ordinal}
 * with an optimistic update that reverts on error. Ordinals are the 0-based
 * index into the thesis kill_criteria list — same convention as ThesisCard.
 */
export function KillCriteriaDrawer({ runId, onToggled }: Props) {
  const [criteria, setCriteria] = useState<KillCriterion[] | null>(null);
  const [states, setStates] = useState<KillCriterionStateOut[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingOrdinal, setSavingOrdinal] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    pipelineApi
      .report(runId)
      .then((r) => {
        if (cancelled) return;
        setCriteria(r.phases.thesis.structured?.kill_criteria ?? []);
        setStates(r.kill_criterion_states ?? []);
      })
      .catch((e) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : "Failed to load kill criteria");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  function statusOf(ordinal: number): "armed" | "triggered" {
    return states.find((s) => s.ordinal === ordinal)?.status ?? "armed";
  }

  async function toggle(ordinal: number) {
    const next = statusOf(ordinal) === "triggered" ? "armed" : "triggered";
    const prev = states;
    const note = prev.find((s) => s.ordinal === ordinal)?.note ?? null;
    // Optimistic flip; revert on error.
    setStates((s) => [
      ...s.filter((x) => x.ordinal !== ordinal),
      { ordinal, status: next, flipped_at: new Date().toISOString(), note },
    ]);
    setSaveError(null);
    setSavingOrdinal(ordinal);
    try {
      const res = await killCriteriaApi.set(runId, ordinal, { status: next });
      setStates((s) =>
        [...s.filter((x) => x.ordinal !== ordinal), res].sort((a, b) => a.ordinal - b.ordinal),
      );
      onToggled?.();
    } catch (e) {
      setStates(prev);
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSavingOrdinal(null);
    }
  }

  if (loadError) {
    return (
      <div className="px-4 py-3 text-xs text-rose-400" data-print-hide="true">
        {loadError}
      </div>
    );
  }
  if (criteria === null) {
    return (
      <div className="px-4 py-3 text-sm text-[var(--text-faint)]" data-print-hide="true">
        Loading kill criteria…
      </div>
    );
  }
  if (criteria.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-[var(--text-faint)]" data-print-hide="true">
        No kill criteria on this thesis.
      </div>
    );
  }

  return (
    <div className="space-y-2 px-4 py-3" data-print-hide="true">
      {criteria.map((k, i) => {
        const cur = statusOf(i);
        return (
          <div
            key={i}
            className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 flex flex-col gap-1.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-[11px] font-semibold text-[var(--text)] leading-snug flex-1">
                {k.condition}
              </div>
              <button
                type="button"
                disabled={savingOrdinal === i}
                onClick={() => toggle(i)}
                title={cur === "triggered" ? "Mark armed" : "Mark triggered"}
                className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold disabled:opacity-50 ${
                  cur === "triggered"
                    ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                    : "bg-slate-500/10 text-[var(--text-muted)] border-slate-500/30"
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    cur === "triggered" ? "bg-[var(--warning)]" : "bg-[var(--text-muted)]"
                  }`}
                />
                {cur === "triggered" ? "Triggered" : "Armed"}
              </button>
            </div>
            <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
              <span className="font-mono text-[var(--text-faint)]">trigger</span> {k.threshold}
            </div>
          </div>
        );
      })}
      {saveError && <div className="text-xs text-rose-400">{saveError}</div>}
    </div>
  );
}
