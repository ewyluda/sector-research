"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { pipeline as api } from "@/lib/api";
import type {
  RunDetail,
  SSEEvent,
  AdvanceAction,
  QuickScreenStructured,
  ThesisStructured,
  RiskStressTestStructured,
  PositionMonitorStructured,
  Citation,
  CategoryOutput,
  CuratedFinancials,
  DeepDiveCategoryStructured,
  TranscriptAnalysis,
} from "@/lib/api";
import { QuickScreenCard } from "@/components/QuickScreenCard";
import { ThesisCard } from "@/components/ThesisCard";
import { RiskCard } from "@/components/RiskCard";
import { PositionCard } from "@/components/PositionCard";
import { DeepDiveDashboard } from "@/components/deep-dive/DeepDiveDashboard";

// ── Constants ─────────────────────────────────────────────────────────────────

// Backend phases (backend/app/graph/pipeline.py): quick_screen → deep_dive →
// thesis_construction → risk_stress_test → position_monitor. Transcript
// analysis is a sub-operation INSIDE deep_dive (nodes.run_transcript_analysis),
// not its own top-level phase — do not add it back to this rail.
const PHASE_RAIL = [
  { key: "quick_screen",         label: "Quick Screen",        num: 1 },
  { key: "deep_dive",            label: "Deep Dive",           num: 2 },
  { key: "thesis_construction",  label: "Thesis",              num: 3 },
  { key: "risk_stress_test",     label: "Risk Stress-Test",    num: 4 },
  { key: "position_monitor",     label: "Position",            num: 5 },
] as const;

// Keys must match backend DEEP_DIVE_CATEGORIES in prompts.py exactly —
// the SSE category_complete events use these display names as keys.
const DEEP_DIVE_CATEGORIES = [
  "Business Quality",
  "Financial Health",
  "Growth & Earnings",
  "Management & Governance",
  "Technical & Market Structure",
  "Macro & Regime",
  "Sentiment & Narrative",
  "Risk Assessment",
  "Future Durability",
] as const;

type CatStatus = "pending" | "running" | "pass" | "fail";

interface CategoryState {
  status: CatStatus;
  score: number | null;
  key_findings: string[];
  structured: DeepDiveCategoryStructured | null;
}

// ── Phase Rail ────────────────────────────────────────────────────────────────

function PhaseRail({
  currentPhase,
  runStatus,
  loopCount,
  ticker,
}: {
  currentPhase: string;
  runStatus: string;
  loopCount: number;
  ticker: string;
}) {
  const isComplete = runStatus === "completed" || runStatus === "watchlist";

  return (
    <aside className="w-56 flex-shrink-0 flex flex-col gap-1 pt-1">
      <div className="mb-4">
        <p className="text-xs text-[var(--text-faint)] uppercase tracking-wider font-medium mb-0.5">
          Research Run
        </p>
        <p className="text-xl font-mono font-semibold text-[var(--text)] tracking-wide">
          {ticker}
        </p>
        {loopCount > 0 && (
          <span className="inline-flex items-center gap-1 mt-1 px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 text-xs font-medium">
            ↻ Loop {loopCount}/2
          </span>
        )}
      </div>

      <div className="flex flex-col gap-0.5">
        {PHASE_RAIL.map((phase) => {
          const isDone =
            isComplete ||
            PHASE_RAIL.findIndex((p) => p.key === phase.key) <
            PHASE_RAIL.findIndex((p) => p.key === currentPhase);
          const isActive = phase.key === currentPhase && !isComplete;

          return (
            <div
              key={phase.key}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                isActive
                  ? "bg-[var(--primary)]/10 text-[var(--primary)]"
                  : isDone
                  ? "text-[var(--text-muted)]"
                  : "text-[var(--text-faint)]"
              }`}
            >
              {/* Step circle */}
              <span
                className={`w-6 h-6 flex-shrink-0 flex items-center justify-center rounded-full text-xs font-semibold border ${
                  isActive
                    ? "border-[var(--primary)] bg-[var(--primary)]/20 text-[var(--primary)]"
                    : isDone
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                    : "border-[var(--border)] bg-transparent text-[var(--text-faint)]"
                }`}
              >
                {isDone ? "✓" : phase.num}
              </span>
              <span className="text-sm font-medium leading-tight">{phase.label}</span>
            </div>
          );
        })}
      </div>

      {isComplete && (
        <div
          className={`mt-4 px-3 py-2 rounded-lg text-xs font-semibold text-center ${
            runStatus === "completed"
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
              : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
          }`}
        >
          {runStatus === "completed" ? "✓ Complete" : "⊖ Watchlist"}
        </div>
      )}
    </aside>
  );
}

// ── Category Grid ─────────────────────────────────────────────────────────────

function DeepDiveCategoryGrid({
  categories,
}: {
  categories: Record<string, CategoryState>;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {DEEP_DIVE_CATEGORIES.map((cat) => {
        const state = categories[cat] ?? { status: "pending", score: null, key_findings: [] };
        const statusColors: Record<CatStatus, string> = {
          pending: "border-[var(--border)] bg-[var(--surface)] text-[var(--text-faint)]",
          running: "border-[var(--primary)]/40 bg-[var(--primary)]/5 text-[var(--primary)]",
          pass:    "border-emerald-500/30 bg-emerald-500/8 text-emerald-400",
          fail:    "border-red-500/30 bg-red-500/8 text-red-400",
        };
        const statusDot: Record<CatStatus, string> = {
          pending: "bg-[var(--text-faint)]",
          running: "bg-[var(--primary)] animate-pulse",
          pass:    "bg-emerald-400",
          fail:    "bg-red-400",
        };

        return (
          <div
            key={cat}
            className={`rounded-lg border p-3 transition-all ${statusColors[state.status]}`}
          >
            <div className="flex items-center justify-between gap-1 mb-1">
              <span className="text-xs font-medium leading-tight">
                {cat}
              </span>
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${statusDot[state.status]}`} />
            </div>
            {state.score !== null && (
              <p className="text-lg font-semibold font-mono">{state.score}</p>
            )}
            {state.key_findings[0] && (
              <p className="text-xs opacity-70 mt-1 leading-snug line-clamp-2">
                {state.key_findings[0]}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Action Bar ────────────────────────────────────────────────────────────────

function ActionBar({
  phase,
  awaitingApproval,
  onAction,
  disabled,
}: {
  phase: string;
  awaitingApproval: boolean;
  onAction: (action: AdvanceAction, feedback?: string) => void;
  disabled: boolean;
}) {
  const [flagOpen, setFlagOpen] = useState(false);
  const [flagNote, setFlagNote] = useState("");

  if (!awaitingApproval) {
    return (
      <div className="flex items-center gap-3 py-4 px-1">
        <div className="flex-1 h-px bg-[var(--border)]" />
        <span className="text-xs text-[var(--text-faint)]">
          Running {phase.replace(/_/g, " ")}…
        </span>
        <span className="w-3 h-3 rounded-full border-2 border-[var(--primary)] border-t-transparent animate-spin" />
        <div className="flex-1 h-px bg-[var(--border)]" />
      </div>
    );
  }

  return (
    <div className="border-t border-[var(--border)] pt-4 mt-2">
      <p className="text-xs text-[var(--text-faint)] uppercase tracking-wider font-medium mb-3">
        Phase complete — review and advance
      </p>

      {flagOpen ? (
        <div className="space-y-2">
          <textarea
            value={flagNote}
            onChange={(e) => setFlagNote(e.target.value)}
            placeholder="Add a note about your concern (required to flag)…"
            rows={2}
            className="w-full px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)]
                       text-sm text-[var(--text)] placeholder-[var(--text-faint)]
                       focus:outline-none focus:border-amber-500/50 resize-none"
          />
          <div className="flex gap-2">
            <button
              onClick={() => { onAction("flag", flagNote); setFlagOpen(false); setFlagNote(""); }}
              disabled={!flagNote.trim() || disabled}
              className="flex-1 py-2 rounded-lg bg-amber-500/15 text-amber-400 text-sm font-semibold
                         border border-amber-500/25 hover:bg-amber-500/25 disabled:opacity-40 transition-colors"
            >
              Flag & Continue
            </button>
            <button
              onClick={() => { setFlagOpen(false); setFlagNote(""); }}
              className="px-4 py-2 rounded-lg bg-[var(--surface)] text-[var(--text-faint)]
                         text-sm border border-[var(--border)] hover:text-[var(--text)] transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={() => onAction("approve")}
            disabled={disabled}
            className="flex-1 py-2.5 rounded-lg bg-[var(--primary)] text-white text-sm font-semibold
                       hover:bg-[var(--primary-dk)] active:scale-[0.98] disabled:opacity-40 transition-all"
          >
            Approve & Continue →
          </button>
          <button
            onClick={() => setFlagOpen(true)}
            disabled={disabled}
            className="px-4 py-2.5 rounded-lg bg-amber-500/10 text-amber-400 text-sm font-semibold
                       border border-amber-500/20 hover:bg-amber-500/20 disabled:opacity-40 transition-colors"
          >
            Flag
          </button>
          <button
            onClick={() => onAction("stop")}
            disabled={disabled}
            className="px-4 py-2.5 rounded-lg bg-[var(--surface)] text-[var(--text-muted)] text-sm
                       border border-[var(--border)] hover:text-red-400 hover:border-red-400/30 disabled:opacity-40 transition-colors"
          >
            Stop
          </button>
        </div>
      )}
    </div>
  );
}

// ── Streaming output panel ─────────────────────────────────────────────────────

function StreamPanel({ tokens }: { tokens: string[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight;
    }
  }, [tokens]);

  return (
    <div
      ref={ref}
      className="flex-1 overflow-y-auto rounded-lg bg-[var(--surface)] border border-[var(--border)]
                 p-4 font-mono text-xs text-[var(--text-muted)] leading-relaxed min-h-[200px]"
    >
      {tokens.length === 0 ? (
        <span className="text-[var(--text-faint)]">Waiting for output…</span>
      ) : (
        tokens.join("")
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function PipelineRunnerPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();

  const [run, setRun] = useState<RunDetail | null>(null);
  const [currentPhase, setCurrentPhase] = useState("quick_screen");
  const [awaitingApproval, setAwaitingApproval] = useState(false);
  const [tokens, setTokens] = useState<string[]>([]);
  const [categories, setCategories] = useState<Record<string, CategoryState>>({});
  const [inDeepDive, setInDeepDive] = useState(false);
  const [curatedFinancials, setCuratedFinancials] = useState<CuratedFinancials | null>(null);
  const [transcriptAnalysis, setTranscriptAnalysis] = useState<TranscriptAnalysis | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [flags, setFlags] = useState<string[]>([]);
  const [convictionScore, setConvictionScore] = useState<number | null>(null);

  const esRef = useRef<EventSource | null>(null);

  // Initial fetch
  useEffect(() => {
    if (!runId) return;
    api.get(runId).then((r) => {
      setRun(r);
      setCurrentPhase(r.phase);
      setFlags(r.flags);
      setConvictionScore(r.conviction_score);
      if (r.status === "awaiting_approval") setAwaitingApproval(true);

      // Seed the output panel from persisted state. Non-streaming phases
      // (quick_screen, risk_stress_test, position_monitor) store their content
      // only in phase_outputs. Without this seed the StreamPanel shows
      // "Waiting for output…" forever.
      //
      // Phase names don't always match storage keys — nodes use short keys
      // ("thesis", "risk", "position") while the pipeline uses full names.
      // Apply the same mapping as the SSE interrupt handler.
      const outputKeyMap: Record<string, string> = {
        thesis_construction: "thesis",
        risk_stress_test: "risk",
        position_monitor: "position",
      };
      const outputKey = outputKeyMap[r.phase] ?? r.phase;
      const output = r.phase_outputs?.[outputKey];
      if (output && typeof output === "object" && "content" in output) {
        const content = (output as { content?: unknown }).content;
        if (typeof content === "string" && content.length > 0) {
          setTokens([content]);
        }
      }
    });
  }, [runId]);

  // Poll fallback — if SSE misses an event (stream disconnect, race
  // condition), periodically re-fetch run state so the UI catches up.
  // Polls every 5s while the run is in_progress, stops once settled.
  useEffect(() => {
    if (!runId || awaitingApproval) return;
    const id = setInterval(() => {
      api.get(runId).then((r) => {
        if (r.status === "awaiting_approval" || r.status === "completed" || r.status === "watchlist") {
          setRun(r);
          setCurrentPhase(r.phase);
          setConvictionScore(r.conviction_score);
          if (r.status === "awaiting_approval") setAwaitingApproval(true);
          // Seed tokens for the StreamPanel fallback (non-structured path)
          const keyMap: Record<string, string> = {
            thesis_construction: "thesis",
            risk_stress_test: "risk",
            position_monitor: "position",
          };
          const key = keyMap[r.phase] ?? r.phase;
          const out = r.phase_outputs?.[key];
          if (out && typeof out === "object" && "content" in out) {
            const content = (out as { content?: unknown }).content;
            if (typeof content === "string" && content.length > 0) {
              setTokens((prev) => (prev.length > 0 ? prev : [content]));
            }
          }
        }
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [runId, awaitingApproval]);

  // SSE connection
  useEffect(() => {
    if (!runId) return;

    const url = api.streamUrl(runId);
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        handleSSEEvent(event);
      } catch {}
    };

    return () => {
      es.close();
      esRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case "phase_start":
        setCurrentPhase(event.phase);
        setAwaitingApproval(false);
        setTokens([]);
        setInDeepDive(false);
        break;

      case "deep_dive_start":
        setInDeepDive(true);
        setCategories({});
        setCuratedFinancials(event.curated_financials ?? null);
        setTranscriptAnalysis(event.transcript_analysis ?? null);
        break;

      case "category_complete":
        setCategories((prev) => ({
          ...prev,
          [event.category]: {
            status: "pass",
            score: event.score,
            key_findings: event.key_findings,
            structured: event.structured ?? null,
          },
        }));
        break;

      case "category_error":
        setCategories((prev) => ({
          ...prev,
          [event.category]: { status: "fail", score: null, key_findings: [], structured: null },
        }));
        break;

      case "token":
        setTokens((prev) => [...prev, event.text]);
        break;

      case "interrupt":
        setCurrentPhase(event.phase);
        setAwaitingApproval(true);
        setConvictionScore(event.conviction_score);

        // Merge the full phase output into local run state so structured
        // dashboards render immediately during live sessions.
        //
        // IMPORTANT: phase names don't always match their storage keys in
        // phase_outputs. The nodes use short keys ("thesis", "risk",
        // "position") but the pipeline uses full phase names. This map
        // mirrors PHASE_OUTPUT_KEYS in backend/app/services/pipeline.py.
        {
          const outputKeyMap: Record<string, string> = {
            thesis_construction: "thesis",
            risk_stress_test: "risk",
            position_monitor: "position",
          };
          const outputKey = outputKeyMap[event.phase] ?? event.phase;
          setRun((prev) => {
            if (!prev || !event.output || typeof event.output !== "object") {
              return prev;
            }
            return {
              ...prev,
              phase_outputs: {
                ...prev.phase_outputs,
                [outputKey]: event.output as CategoryOutput,
              },
            };
          });
        }

        // Existing token-seeding fallback — only used when StreamPanel renders
        // (old runs, parse failures, or non-Quick-Screen phases).
        {
          const out = event.output as { content?: unknown } | null | undefined;
          const content = out && typeof out === "object" ? out.content : null;
          if (typeof content === "string" && content.length > 0) {
            setTokens((prev) => (prev.length > 0 ? prev : [content]));
          }
        }
        break;

      case "complete":
        setAwaitingApproval(false);
        setConvictionScore(event.conviction_score);
        // Refresh run state
        api.get(runId!).then(setRun);
        break;

      case "error":
        setAwaitingApproval(true); // allow user to stop
        break;
    }
  }, [runId]);

  async function handleAction(action: AdvanceAction, feedback?: string) {
    if (!runId || advancing) return;
    setAdvancing(true);
    try {
      const updated = await api.advance(runId, action, feedback);
      setRun(updated);
      setCurrentPhase(updated.phase);
      setFlags(updated.flags);
      if (action === "stop") {
        // Stay on page, run is watchlisted
        setAwaitingApproval(false);
      } else {
        setAwaitingApproval(false);
        setTokens([]);
        setInDeepDive(false);
      }
    } finally {
      setAdvancing(false);
    }
  }

  const isComplete =
    run?.status === "completed" || run?.status === "watchlist";

  // Derive the Quick Screen structured output from run state, with a safe
  // cast — CategoryOutput already declares the optional `structured` field.
  const quickScreenOutput = run?.phase_outputs?.quick_screen as
    | CategoryOutput
    | undefined;
  const quickScreenStructured: QuickScreenStructured | null =
    (quickScreenOutput?.structured as QuickScreenStructured | undefined) ?? null;
  // Prefer per-phase citations if the backend populated them; otherwise fall
  // back to the run-level accumulator (during Quick Screen, the accumulator
  // only contains Quick Screen sources anyway).
  const quickScreenCitations: Citation[] =
    quickScreenOutput?.citations ?? run?.citations ?? [];

  // Thesis Construction structured output
  const thesisOutput = run?.phase_outputs?.thesis as
    | CategoryOutput
    | undefined;
  const thesisStructured: ThesisStructured | null =
    (thesisOutput?.structured as unknown as ThesisStructured | null) ?? null;
  const thesisCitations: Citation[] =
    thesisOutput?.citations ?? run?.citations ?? [];

  // Risk Stress-Test structured output
  const riskOutput = run?.phase_outputs?.risk as
    | CategoryOutput
    | undefined;
  const riskStructured: RiskStressTestStructured | null =
    (riskOutput?.structured as unknown as RiskStressTestStructured | null) ?? null;
  const riskCitations: Citation[] =
    riskOutput?.citations ?? run?.citations ?? [];

  // Position Monitor structured output
  const positionOutput = run?.phase_outputs?.position as
    | (CategoryOutput & { structured?: PositionMonitorStructured })
    | undefined;
  const positionStructured: PositionMonitorStructured | null =
    (positionOutput?.structured as unknown as PositionMonitorStructured | null) ?? null;
  const positionCitations: Citation[] =
    positionOutput?.citations ?? run?.citations ?? [];

  return (
    <main className="min-h-screen bg-[var(--bg)] p-6">
      <div className="max-w-6xl mx-auto flex gap-8">
        {/* Left rail */}
        <PhaseRail
          currentPhase={currentPhase}
          runStatus={run?.status ?? "in_progress"}
          loopCount={run?.loop_count ?? 0}
          ticker={run?.ticker ?? "—"}
        />

        {/* Main panel */}
        <div className="flex-1 min-w-0 flex flex-col gap-4">
          {/* Header row */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-[var(--text)] tracking-tight">
                {PHASE_RAIL.find((p) => p.key === currentPhase)?.label ?? currentPhase.replace(/_/g, " ")}
              </h1>
              {run && (
                <p className="text-sm text-[var(--text-faint)] mt-0.5">
                  Run ID: <span className="font-mono text-xs">{runId}</span>
                </p>
              )}
            </div>
            {convictionScore !== null && (
              <div className="text-right">
                <p className="text-xs text-[var(--text-faint)] uppercase tracking-wider">
                  Conviction
                </p>
                <p className="text-2xl font-semibold font-mono text-[var(--primary)]">
                  {convictionScore}
                </p>
              </div>
            )}
          </div>

          {/* Flags */}
          {flags.length > 0 && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 space-y-1">
              <p className="text-xs font-medium text-amber-400 uppercase tracking-wider">
                Flagged notes
              </p>
              {flags.map((f, i) => (
                <p key={i} className="text-xs text-[var(--text-muted)]">
                  · {f}
                </p>
              ))}
            </div>
          )}

          {/* Deep dive dashboard */}
          {inDeepDive ? (
            <DeepDiveDashboard
              financials={curatedFinancials}
              categories={Object.fromEntries(
                Object.entries(categories).map(([k, v]) => [
                  k,
                  v.status === "fail" ? null : {
                    score: v.score ?? 0,
                    content: "",
                    key_findings: v.key_findings,
                    citations: [],
                    structured: v.structured ?? undefined,
                  },
                ])
              )}
              scores={Object.fromEntries(
                Object.entries(categories)
                  .filter(([, v]) => v.score != null)
                  .map(([k, v]) => [k, v.score!])
              )}
              isLive={true}
              transcriptAnalysis={transcriptAnalysis}
            />
          ) : currentPhase === "quick_screen" && quickScreenStructured ? (
            <QuickScreenCard
              structured={quickScreenStructured}
              citations={quickScreenCitations}
              ticker={run?.ticker ?? ""}
            />
          ) : currentPhase === "thesis_construction" && thesisStructured ? (
            <ThesisCard
              structured={thesisStructured}
              citations={thesisCitations}
              ticker={run?.ticker ?? ""}
              thesisStatus={run?.thesis_status ?? "PENDING"}
            />
          ) : currentPhase === "risk_stress_test" && riskStructured ? (
            <RiskCard
              structured={riskStructured}
              citations={riskCitations}
              ticker={run?.ticker ?? ""}
              loopCount={run?.loop_count ?? 0}
            />
          ) : currentPhase === "position_monitor" && positionStructured ? (
            <PositionCard
              structured={positionStructured}
              citations={positionCitations}
              ticker={run?.ticker ?? ""}
              convictionScore={convictionScore}
            />
          ) : (
            <StreamPanel tokens={tokens} />
          )}

          {/* Action bar */}
          <ActionBar
            phase={currentPhase}
            awaitingApproval={awaitingApproval && !isComplete}
            onAction={handleAction}
            disabled={advancing}
          />

          {/* View full report CTA */}
          {isComplete && (
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => router.push(`/report/${runId}`)}
                className="flex-1 py-3 rounded-lg bg-[var(--primary)] text-white text-sm font-semibold
                           hover:bg-[var(--primary-dk)] active:scale-[0.98] transition-all"
              >
                View Full Report →
              </button>
              <button
                onClick={() => router.push("/library")}
                className="px-5 py-3 rounded-lg bg-[var(--surface)] text-[var(--text-muted)] text-sm
                           border border-[var(--border)] hover:text-[var(--text)] transition-colors"
              >
                Back to Library
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
