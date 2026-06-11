/**
 * Analyst Memo dashboard for the Thesis Construction phase output.
 *
 * Layout (top to bottom):
 *   1. Header — ScoreRing (conviction) + ticker + thesis status badge
 *   2. Core thesis callout (teal-tinted, left-bordered)
 *   3. Bull/Bear columns (symmetric two-column layout)
 *   4. Variant perception callout (rust-tinted, left-bordered)
 *   5. Catalyst list (timeframe + description rows)
 *   6. Kill criteria — collapsible (default closed)
 *   7. Pre-mortem — collapsible (default closed)
 *   8. Conviction rationale footer
 *   9. Citation list footer
 *
 * State: highlightedPillar tracks "bull:N"|"bear:N" hovers from the
 * pillar-link chips in CatalystList and the kill criteria list, and is
 * passed down to BullBearColumns to apply a ring/glow.
 */

"use client";

import { useState } from "react";
import type {
  ThesisStructured,
  Citation,
  KillCriterion,
  FailureMode,
  PreMortem,
  KillCriterionStateOut,
} from "@/lib/api";
import { killCriteria as killCriteriaApi } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { BullBearColumns } from "@/components/BullBearColumns";
import { CatalystList } from "@/components/CatalystList";
import { CitationList } from "@/components/CitationList";
import { usePersistedCollapse } from "@/components/deep-dive/usePersistedCollapse";

const STATUS_COLORS: Record<string, string> = {
  "ON TRACK": "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  DRIFTING:   "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  BROKEN:     "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  PENDING:    "bg-[var(--surface)] text-[var(--text-faint)] border-[var(--border)]",
};

const PROBABILITY_COLORS: Record<FailureMode["probability"], string> = {
  Low:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  Medium: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  High:   "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
};

interface Props {
  structured: ThesisStructured;
  citations?: Citation[];
  ticker: string;
  thesisStatus: string;
  runId: string;
  killCriterionStates: KillCriterionStateOut[];
}

function PillarChip({
  pillar,
  prefix,
  onHover,
}: {
  pillar: string;
  prefix: string;
  onHover: (p: string | null) => void;
}) {
  return (
    <button
      type="button"
      onMouseEnter={() => onHover(pillar)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(pillar)}
      onBlur={() => onHover(null)}
      className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--surface-alt)] cursor-default"
    >
      {prefix} {pillar}
    </button>
  );
}

function KillCriteriaSection({
  items,
  states: initialStates,
  runId,
  onPillarHover,
}: {
  items: KillCriterion[];
  states: KillCriterionStateOut[];
  runId: string;
  onPillarHover: (p: string | null) => void;
}) {
  const [collapsed, setCollapsed] = usePersistedCollapse(
    "thesis-kill-criteria",
    true,
  );
  const [states, setStates] = useState<KillCriterionStateOut[]>(initialStates);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftNote, setDraftNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  function statusOf(ordinal: number): "armed" | "triggered" {
    return states.find((s) => s.ordinal === ordinal)?.status ?? "armed";
  }

  async function flip(ordinal: number, next: "armed" | "triggered", note: string) {
    setSaving(true);
    setSaveError(null);
    try {
      const res = await killCriteriaApi.set(runId, ordinal, {
        status: next,
        note: note || undefined,
      });
      setStates((prev) => {
        const without = prev.filter((s) => s.ordinal !== ordinal);
        return [...without, res].sort((a, b) => a.ordinal - b.ordinal);
      });
      setEditing(null);
      setDraftNote("");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
      <button
        type="button"
        aria-expanded={!collapsed}
        aria-controls="thesis-kill-criteria-panel"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3.5 py-2.5"
      >
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Kill Criteria · {items.length}
        </span>
        <span className="text-[10px] text-[var(--text-faint)] font-mono">
          {collapsed ? "+" : "−"}
        </span>
      </button>
      {!collapsed && (
        <div id="thesis-kill-criteria-panel" className="px-3.5 pb-3 flex flex-col gap-2">
          {items.map((k, i) => {
            const cur = statusOf(i);
            const isEditing = editing === i;
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
                    onClick={() => {
                      const note = states.find((s) => s.ordinal === i)?.note ?? "";
                      setDraftNote(note);
                      setEditing(isEditing ? null : i);
                      setSaveError(null);
                    }}
                    className={`shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${
                      cur === "triggered"
                        ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                        : "bg-slate-500/10 text-[var(--text-muted)] border-slate-500/30"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${cur === "triggered" ? "bg-[var(--warning)]" : "bg-[var(--text-muted)]"}`} />
                    {cur === "triggered" ? "Triggered" : "Armed"}
                  </button>
                </div>
                <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                  <span className="font-mono text-[var(--text-faint)]">trigger</span>{" "}
                  {k.threshold}
                </div>
                <div className="flex items-center gap-2 flex-wrap mt-0.5">
                  <span className="text-[9px] font-mono text-[var(--text-faint)]">
                    watch: {k.monitoring_source}
                  </span>
                  {k.kills_pillar && (
                    <PillarChip
                      pillar={k.kills_pillar}
                      prefix="kills"
                      onHover={onPillarHover}
                    />
                  )}
                </div>

                {isEditing && (
                  <div className="mt-1.5 flex flex-col gap-1.5 border-t border-[var(--border)] pt-1.5">
                    <textarea
                      value={draftNote}
                      onChange={(e) => setDraftNote(e.target.value)}
                      placeholder="Optional note (what triggered it?)"
                      className="w-full text-[11px] bg-[var(--surface-alt)] border border-[var(--border)] rounded px-2 py-1 resize-y min-h-[40px]"
                    />
                    <div className="flex gap-2 items-center">
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() =>
                          flip(i, cur === "triggered" ? "armed" : "triggered", draftNote)
                        }
                        className="px-2 py-0.5 rounded bg-[var(--accent-bg)] text-[var(--primary-dk)] text-[10px] font-semibold disabled:opacity-50"
                      >
                        {saving ? "Saving…" : cur === "triggered" ? "Mark Armed" : "Mark Triggered"}
                      </button>
                      <button
                        type="button"
                        disabled={saving}
                        onClick={() => { setEditing(null); setDraftNote(""); setSaveError(null); }}
                        className="px-2 py-0.5 rounded text-[10px] text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        Cancel
                      </button>
                      {saveError && (
                        <span className="text-[10px] text-red-400">{saveError}</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function PreMortemSection({ data }: { data: PreMortem }) {
  const [collapsed, setCollapsed] = usePersistedCollapse(
    "thesis-pre-mortem",
    true,
  );
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
      <button
        type="button"
        aria-expanded={!collapsed}
        aria-controls="thesis-pre-mortem-panel"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3.5 py-2.5"
      >
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Pre-Mortem · {data.failure_modes.length}
        </span>
        <span className="text-[10px] text-[var(--text-faint)] font-mono">
          {collapsed ? "+" : "−"}
        </span>
      </button>
      {!collapsed && (
        <div id="thesis-pre-mortem-panel" className="px-3.5 pb-3 flex flex-col gap-2">
          <div className="text-[11px] italic text-[var(--text-muted)] leading-snug">
            {data.framing}
          </div>
          {data.failure_modes.map((fm, i) => (
            <div
              key={i}
              className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 flex flex-col gap-1"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-semibold text-[var(--text)] leading-snug">
                  {fm.mode}
                </span>
                <span
                  className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${PROBABILITY_COLORS[fm.probability]}`}
                >
                  {fm.probability.toUpperCase()}
                </span>
              </div>
              <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                <span className="font-mono text-[var(--text-faint)]">leading:</span>{" "}
                {fm.leading_indicator}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ThesisCard({
  structured,
  citations = [],
  ticker,
  thesisStatus,
  runId,
  killCriterionStates,
}: Props) {
  const statusColor = STATUS_COLORS[thesisStatus] ?? STATUS_COLORS.PENDING;
  const [highlightedPillar, setHighlightedPillar] = useState<string | null>(null);

  const killCriteria = structured.kill_criteria ?? [];
  const preMortem = structured.pre_mortem ?? null;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center gap-4 pb-4 border-b border-[var(--border)]">
        <ScoreRing score={structured.conviction_score} size={86} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 mb-1">
            <span className="text-2xl font-mono font-bold text-[var(--text)] tracking-wide">
              {ticker}
            </span>
            <span
              className={`px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider ${statusColor}`}
            >
              {thesisStatus === "ON TRACK" ? "● ON TRACK" : thesisStatus}
            </span>
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            Thesis Construction · Conviction {structured.conviction_score}/100
          </div>
        </div>
      </div>

      {/* Core thesis callout */}
      <div
        className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3.5"
        style={{ borderLeft: "3px solid var(--primary)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1.5">
          Core Thesis
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.core_thesis}
        </div>
      </div>

      {/* Bull / Bear columns */}
      <BullBearColumns
        bull={structured.bull_case}
        bear={structured.bear_case}
        highlightedPillar={highlightedPillar}
      />

      {/* Variant perception callout */}
      <div
        className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/4 p-3.5"
        style={{ borderLeft: "3px solid var(--warning)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--warning)] mb-1.5">
          ◆ Variant Perception
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.variant_perception}
        </div>
      </div>

      {/* Catalyst list */}
      <CatalystList
        catalysts={structured.catalysts}
        onPillarHover={setHighlightedPillar}
      />

      {/* Kill criteria — only if present */}
      {killCriteria.length > 0 && (
        <KillCriteriaSection
          items={killCriteria}
          states={killCriterionStates}
          runId={runId}
          onPillarHover={setHighlightedPillar}
        />
      )}

      {/* Pre-mortem — only if present */}
      {preMortem && <PreMortemSection data={preMortem} />}

      {/* Conviction rationale footer */}
      <div className="rounded-lg bg-[var(--surface-alt)] border border-[var(--border)] p-3.5">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
          Why {structured.conviction_score}?
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.conviction_rationale}
        </div>
      </div>

      {/* Citation footer */}
      <CitationList citations={citations} />
    </div>
  );
}
