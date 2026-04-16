"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { pipeline as api } from "@/lib/api";
import type {
  RunDetail,
  ReportResponse,
  SSEEvent,
  QuickScreenStructured,
  ThesisStructured,
  RiskStressTestStructured,
  PositionMonitorStructured,
  Citation,
  CategoryOutput,
  CuratedFinancials,
  DeepDiveCategoryStructured,
  TranscriptAnalysis,
  XSignalVelocity,
  EdgarFacts,
} from "@/lib/api";
import { ThesisCard } from "@/components/ThesisCard";
import { RiskCard } from "@/components/RiskCard";
import { PositionCard } from "@/components/PositionCard";
import { DeepDiveDashboard } from "@/components/deep-dive/DeepDiveDashboard";
import { ReportHeader } from "@/components/deep-dive/ReportHeader";

// ── Constants ─────────────────────────────────────────────────────────────────

const PHASE_ORDER = [
  "quick_screen",
  "deep_dive",
  "thesis_construction",
  "risk_stress_test",
  "position_monitor",
] as const;

const PHASE_LABELS: Record<string, string> = {
  quick_screen: "Quick Screen",
  deep_dive: "Deep Dive",
  thesis_construction: "Thesis Construction",
  risk_stress_test: "Risk Stress-Test",
  position_monitor: "Position Monitor",
};

type CatStatus = "pending" | "running" | "pass" | "fail";

interface CategoryState {
  status: CatStatus;
  score: number | null;
  key_findings: string[];
  structured: DeepDiveCategoryStructured | null;
}

// ── Live Progress Bar (inline) ────────────────────────────────────────────────

function LiveProgressBar({ currentPhase }: { currentPhase: string }) {
  const idx = PHASE_ORDER.indexOf(currentPhase as (typeof PHASE_ORDER)[number]);
  const pct = idx >= 0 ? Math.round(((idx + 0.5) / PHASE_ORDER.length) * 100) : 10;

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
          <span className="text-sm font-medium text-[var(--color-text-primary)]">
            Running: {PHASE_LABELS[currentPhase] ?? currentPhase.replace(/_/g, " ")}
          </span>
        </div>
        <span className="text-xs text-[var(--color-text-muted)] font-mono">{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--color-surface-alt)] overflow-hidden">
        <div
          className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-700"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between mt-2">
        {PHASE_ORDER.map((p, i) => {
          const isDone = i < idx;
          const isActive = i === idx;
          return (
            <span
              key={p}
              className={`text-[10px] font-medium ${
                isActive
                  ? "text-[var(--color-primary)]"
                  : isDone
                  ? "text-emerald-400"
                  : "text-[var(--color-text-faint)]"
              }`}
            >
              {isDone ? "\u2713" : ""} {PHASE_LABELS[p]?.split(" ")[0] ?? p}
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function PipelineRunnerPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();

  // Core state
  const [run, setRun] = useState<RunDetail | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [currentPhase, setCurrentPhase] = useState("quick_screen");
  const [isLive, setIsLive] = useState(true);
  const [loading, setLoading] = useState(true);

  // Phase data
  const [quickScreenStructured, setQuickScreenStructured] = useState<QuickScreenStructured | null>(null);
  const [curatedFinancials, setCuratedFinancials] = useState<CuratedFinancials | null>(null);
  const [transcriptAnalysis, setTranscriptAnalysis] = useState<TranscriptAnalysis | null>(null);
  const [edgarFacts, setEdgarFacts] = useState<EdgarFacts>({});
  const [categories, setCategories] = useState<Record<string, CategoryState>>({});
  const [thesisStructured, setThesisStructured] = useState<ThesisStructured | null>(null);
  const [riskStructured, setRiskStructured] = useState<RiskStressTestStructured | null>(null);
  const [positionStructured, setPositionStructured] = useState<PositionMonitorStructured | null>(null);

  // Raw content fallback (when structured parsing fails)
  const [thesisContent, setThesisContent] = useState<string | null>(null);
  const [riskContent, setRiskContent] = useState<string | null>(null);
  const [positionContent, setPositionContent] = useState<string | null>(null);
  const [thesisParseError, setThesisParseError] = useState<string | null>(null);
  const [riskParseError, setRiskParseError] = useState<string | null>(null);
  const [positionParseError, setPositionParseError] = useState<string | null>(null);

  // Scores & metadata
  const [scores, setScores] = useState<Record<string, number>>({});
  const [convictionScore, setConvictionScore] = useState<number | null>(null);
  const [xSignalVelocity, setXSignalVelocity] = useState<XSignalVelocity | null>(null);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [generatingPosition, setGeneratingPosition] = useState(false);

  const esRef = useRef<EventSource | null>(null);

  // ── Load completed report data ──────────────────────────────────────────────

  const loadReportData = useCallback(async (id: string) => {
    try {
      const r = await api.report(id);
      setReport(r);

      // Quick screen
      const qsOutput = r.phases.quick_screen;
      setQuickScreenStructured((qsOutput?.structured as QuickScreenStructured) ?? null);

      // Curated financials + EDGAR XBRL facts
      setCuratedFinancials(r.phases.deep_dive?.curated_financials ?? null);
      setTranscriptAnalysis(r.phases.deep_dive?.transcript_analysis ?? null);
      setEdgarFacts(r.phases.deep_dive?.edgar_facts ?? {});

      // Categories from deep dive
      const cats = r.phases.deep_dive?.categories ?? {};
      const catState: Record<string, CategoryState> = {};
      for (const [key, val] of Object.entries(cats)) {
        if (val.__type__ === "CategoryError") {
          catState[key] = { status: "fail", score: null, key_findings: [], structured: null };
        } else {
          catState[key] = {
            status: "pass",
            score: val.score ?? null,
            key_findings: val.key_findings ?? [],
            structured: (val.structured as DeepDiveCategoryStructured) ?? null,
          };
        }
      }
      setCategories(catState);

      // Thesis
      const thesisPhase = r.phases.thesis;
      setThesisStructured((thesisPhase?.structured as unknown as ThesisStructured) ?? null);
      setThesisContent(thesisPhase?.content ?? null);
      setThesisParseError(thesisPhase?.parse_error ?? null);

      // Risk
      const riskPhase = r.phases.risk;
      setRiskStructured((riskPhase?.structured as unknown as RiskStressTestStructured) ?? null);
      setRiskContent(riskPhase?.content ?? null);
      setRiskParseError(riskPhase?.parse_error ?? null);

      // Position (optional)
      const posPhase = r.phases.position;
      setPositionStructured((posPhase?.structured as unknown as PositionMonitorStructured) ?? null);
      setPositionContent(posPhase?.content ?? null);
      setPositionParseError((posPhase as unknown as { parse_error?: string })?.parse_error ?? null);

      // Scores
      setScores(r.scores);
      setConvictionScore(r.conviction_score);
      setCitations(r.citations);
      setXSignalVelocity(r.x_signal_velocity ?? null);
    } catch {
      // Report endpoint may 404 for in-progress runs — that's fine
    }
  }, []);

  // ── Initial fetch ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!runId) return;

    api.get(runId).then(async (r) => {
      setRun(r);
      setCurrentPhase(r.phase);
      setConvictionScore(r.conviction_score);

      const isCompleted = r.status === "completed" || r.status === "watchlist" || r.status === "error";

      if (isCompleted) {
        setIsLive(false);
        setGeneratingPosition(false);
        await loadReportData(runId);
      } else {
        setIsLive(true);
        // Seed structured data from phase_outputs if available
        seedFromRunDetail(r);
      }
    }).finally(() => setLoading(false));
  }, [runId, loadReportData]);

  // ── Seed structured data from RunDetail for reconnection ────────────────────

  function seedFromRunDetail(r: RunDetail) {
    const outputKeyMap: Record<string, string> = {
      thesis_construction: "thesis",
      risk_stress_test: "risk",
      position_monitor: "position",
    };

    // Quick screen
    const qsOut = r.phase_outputs?.quick_screen as CategoryOutput | undefined;
    if (qsOut?.structured) {
      setQuickScreenStructured(qsOut.structured as QuickScreenStructured);
    }

    // Thesis
    const thesisKey = outputKeyMap.thesis_construction;
    const thesisOut = r.phase_outputs?.[thesisKey] as CategoryOutput | undefined;
    if (thesisOut?.structured) {
      setThesisStructured(thesisOut.structured as unknown as ThesisStructured);
    }

    // Risk
    const riskKey = outputKeyMap.risk_stress_test;
    const riskOut = r.phase_outputs?.[riskKey] as CategoryOutput | undefined;
    if (riskOut?.structured) {
      setRiskStructured(riskOut.structured as unknown as RiskStressTestStructured);
    }

    // Position
    const posKey = outputKeyMap.position_monitor;
    const posOut = r.phase_outputs?.[posKey] as CategoryOutput | undefined;
    if (posOut?.structured) {
      setPositionStructured(posOut.structured as unknown as PositionMonitorStructured);
    }

    // Scores from run
    if (r.scores && Object.keys(r.scores).length > 0) {
      setScores(r.scores);
    }

    if (r.citations && r.citations.length > 0) {
      setCitations(r.citations);
    }
  }

  // ── SSE connection ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (!runId || !isLive) return;

    const url = api.streamUrl(runId);
    const es = new EventSource(url);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        handleSSEEvent(event);
      } catch {
        // Ignore parse errors
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, isLive]);

  const handleSSEEvent = useCallback((event: SSEEvent) => {
    switch (event.type) {
      case "phase_start":
        setCurrentPhase(event.phase);
        break;

      case "deep_dive_start":
        setCuratedFinancials(event.curated_financials ?? null);
        setTranscriptAnalysis(event.transcript_analysis ?? null);
        setEdgarFacts(event.edgar_facts ?? {});
        // Mark all categories as running
        setCategories({});
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
        // Update scores
        if (event.score != null) {
          setScores((prev) => ({ ...prev, [event.category]: event.score }));
        }
        break;

      case "category_error":
        setCategories((prev) => ({
          ...prev,
          [event.category]: { status: "fail", score: null, key_findings: [], structured: null },
        }));
        break;

      case "phase_complete": {
        setCurrentPhase(event.phase);
        setConvictionScore(event.conviction_score);
        const output = event.output as Record<string, unknown> | null;
        if (!output) break;

        const structured = output.structured as Record<string, unknown> | undefined;

        if (event.phase === "quick_screen" && structured) {
          setQuickScreenStructured(structured as unknown as QuickScreenStructured);
          // Update scores from quick screen dimensions
          const dims = (structured as unknown as QuickScreenStructured).dimensions;
          if (dims) {
            const dimScores: Record<string, number> = {};
            for (const d of dims) {
              dimScores[d.name] = d.score;
            }
            setScores((prev) => ({ ...prev, ...dimScores }));
          }
        } else if (event.phase === "thesis_construction" || event.phase === "thesis") {
          if (structured) {
            setThesisStructured(structured as unknown as ThesisStructured);
            if ((structured as unknown as ThesisStructured).conviction_score != null) {
              setConvictionScore((structured as unknown as ThesisStructured).conviction_score);
            }
          }
          setThesisContent((output.content as string) ?? null);
          setThesisParseError((output.parse_error as string) ?? null);
        } else if (event.phase === "risk_stress_test" || event.phase === "risk") {
          if (structured) {
            setRiskStructured(structured as unknown as RiskStressTestStructured);
          }
          setRiskContent((output.content as string) ?? null);
          setRiskParseError((output.parse_error as string) ?? null);
        }
        break;
      }

      case "interrupt": {
        setCurrentPhase(event.phase);
        setConvictionScore(event.conviction_score);

        const outputKeyMap: Record<string, string> = {
          thesis_construction: "thesis",
          risk_stress_test: "risk",
          position_monitor: "position",
        };
        const outputKey = outputKeyMap[event.phase] ?? event.phase;

        // Merge the full phase output into local run state
        setRun((prev) => {
          if (!prev || !event.output || typeof event.output !== "object") return prev;
          return {
            ...prev,
            phase_outputs: {
              ...prev.phase_outputs,
              [outputKey]: event.output as CategoryOutput,
            },
          };
        });

        // Extract structured data from interrupt output
        const out = event.output as Record<string, unknown> | null;
        if (out && typeof out === "object") {
          const str = out.structured as Record<string, unknown> | undefined;
          if (str) {
            if (event.phase === "quick_screen") {
              setQuickScreenStructured(str as unknown as QuickScreenStructured);
            } else if (event.phase === "thesis_construction") {
              setThesisStructured(str as unknown as ThesisStructured);
              if ((str as unknown as ThesisStructured).conviction_score != null) {
                setConvictionScore((str as unknown as ThesisStructured).conviction_score);
              }
            } else if (event.phase === "risk_stress_test") {
              setRiskStructured(str as unknown as RiskStressTestStructured);
            } else if (event.phase === "position_monitor") {
              setPositionStructured(str as unknown as PositionMonitorStructured);
            }
          }
        }
        break;
      }

      case "complete":
        setIsLive(false);
        setGeneratingPosition(false);
        setConvictionScore(event.conviction_score);
        // Re-fetch full run + report data
        if (runId) {
          api.get(runId).then((r) => {
            setRun(r);
            loadReportData(runId);
          });
        }
        break;

      case "error":
        // Keep isLive true so user sees something went wrong
        break;

      case "token":
      case "heartbeat":
        break;
    }
  }, [runId, loadReportData]);

  // ── Polling fallback ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!runId || !isLive) return;
    const id = setInterval(() => {
      api.get(runId).then((r) => {
        setRun(r);
        setCurrentPhase(r.phase);
        setConvictionScore(r.conviction_score);

        if (r.status === "completed" || r.status === "watchlist" || r.status === "error") {
          setIsLive(false);
          setGeneratingPosition(false);
          loadReportData(runId);
        } else {
          // Seed structured data in case SSE missed events
          seedFromRunDetail(r);
        }
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [runId, isLive, loadReportData]);

  // ── Generate Position ───────────────────────────────────────────────────────

  async function handleGeneratePosition() {
    if (!runId || generatingPosition) return;
    setGeneratingPosition(true);
    try {
      await api.advance(runId, "approve");
      // Reconnect SSE to receive position_monitor events
      setCurrentPhase("position_monitor");
      setIsLive(true);
      // The SSE "complete" handler will call loadReportData()
      // and clear generatingPosition via the complete handler
    } catch {
      setGeneratingPosition(false);
    }
  }

  // Build dashboard categories in the format DeepDiveDashboard expects
  const dashboardCategories: Record<string, CategoryOutput | null> = {};
  for (const [k, v] of Object.entries(categories)) {
    if (v.status === "fail") {
      dashboardCategories[k] = null;
    } else {
      dashboardCategories[k] = {
        score: v.score ?? 0,
        content: "",
        key_findings: v.key_findings,
        citations: [],
        structured: v.structured ?? undefined,
      };
    }
  }

  // ── Loading state ───────────────────────────────────────────────────────────

  if (loading) {
    return (
      <main className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-6 h-6 rounded-full border-2 border-[var(--color-primary)] border-t-transparent animate-spin" />
          <span className="text-sm text-[var(--color-text-muted)]">Loading research run...</span>
        </div>
      </main>
    );
  }

  if (!run) {
    return (
      <main className="min-h-screen bg-[var(--color-bg)] flex items-center justify-center">
        <p className="text-[var(--color-text-muted)]">Run not found.</p>
      </main>
    );
  }

  const ticker = run.ticker ?? "";
  const thesisStatus = run.thesis_status ?? report?.thesis_status ?? "PENDING";
  const loopCount = run.loop_count ?? report?.loop_count ?? 0;

  return (
    <main className="min-h-screen bg-[var(--color-bg)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
          {run && (
            <nav className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]" aria-label="Breadcrumb">
              <a href="/library" className="hover:text-[var(--color-text-primary)] transition-colors">Library</a>
              <span className="text-[var(--color-text-faint)]">/</span>
              <span className="text-[var(--color-text-primary)] font-medium">{run.ticker}</span>
              <span className="text-[var(--color-text-faint)]">/</span>
              <span>Deep Dive</span>
            </nav>
          )}

          {/* Progress indicator for live runs */}
          {isLive && <LiveProgressBar currentPhase={currentPhase} />}

          {/* Error banner for failed runs */}
          {!isLive && run.status === "error" && (
            <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] p-4">
              <p className="text-sm font-semibold text-[var(--error-text)]">Pipeline Error</p>
              <p className="text-xs text-[var(--error-text)]/70 mt-1">
                The pipeline encountered an error during the {currentPhase.replace(/_/g, " ")} phase. Partial results are shown below.
              </p>
            </div>
          )}

          {/* Report Header — shows when quick screen data or financials available */}
          {(quickScreenStructured || curatedFinancials) && (
            <ReportHeader
              financials={curatedFinancials}
              quickScreen={quickScreenStructured}
              scores={scores}
              convictionScore={convictionScore}
              ticker={ticker}
              isLive={isLive}
            />
          )}

          {/* Deep Dive Dashboard — shows when financials or categories available */}
          {(curatedFinancials || Object.keys(categories).length > 0) && (
            <DeepDiveDashboard
              ticker={ticker}
              financials={curatedFinancials}
              categories={dashboardCategories}
              scores={scores}
              isLive={isLive}
              transcriptAnalysis={transcriptAnalysis}
              xSignalVelocity={xSignalVelocity ?? undefined}
              edgarFacts={edgarFacts}
            />
          )}

          {/* Thesis */}
          {(thesisStructured || thesisContent) && (
            <section id="thesis_section">
              {thesisStructured ? (
                <ThesisCard
                  structured={thesisStructured}
                  citations={citations}
                  ticker={ticker}
                  thesisStatus={thesisStatus}
                />
              ) : (
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider mb-3">Thesis Construction</h2>
                  {thesisParseError && (
                    <p className="text-xs text-amber-400 mb-2">Structured format unavailable ({thesisParseError})</p>
                  )}
                  <p className="text-sm text-[var(--color-text-muted)] whitespace-pre-wrap leading-relaxed">{thesisContent}</p>
                </div>
              )}
            </section>
          )}

          {/* Risk */}
          {(riskStructured || riskContent) && (
            <section id="risk_section">
              {riskStructured ? (
                <RiskCard
                  structured={riskStructured}
                  citations={report?.phases.risk?.citations ?? citations}
                  ticker={ticker}
                  loopCount={loopCount}
                />
              ) : (
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider mb-3">Risk Stress-Test</h2>
                  {riskParseError && (
                    <p className="text-xs text-amber-400 mb-2">Structured format unavailable ({riskParseError})</p>
                  )}
                  <p className="text-sm text-[var(--color-text-muted)] whitespace-pre-wrap leading-relaxed">{riskContent}</p>
                </div>
              )}
            </section>
          )}

          {/* Position */}
          {(positionStructured || positionContent) && (
            <section id="position_section">
              {positionStructured ? (
                <PositionCard
                  structured={positionStructured}
                  citations={report?.phases.position?.citations ?? citations}
                  ticker={ticker}
                  convictionScore={convictionScore}
                />
              ) : (
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
                  <h2 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider mb-3">Position Plan</h2>
                  {positionParseError && (
                    <p className="text-xs text-amber-400 mb-2">Structured format unavailable ({positionParseError})</p>
                  )}
                  <p className="text-sm text-[var(--color-text-muted)] whitespace-pre-wrap leading-relaxed">{positionContent}</p>
                </div>
              )}
            </section>
          )}

          {/* Generate Position button — shows when completed but no position */}
          {!isLive && (run.status === "completed" || run.status === "watchlist") && !positionStructured && (
            <button
              onClick={handleGeneratePosition}
              disabled={generatingPosition}
              className="w-full py-3 rounded-lg bg-[var(--color-primary)] text-white text-sm font-semibold
                         hover:bg-[var(--color-primary)]/90 active:scale-[0.98] disabled:opacity-50 transition-all
                         flex items-center justify-center gap-2"
            >
              {generatingPosition ? (
                <>
                  <span className="w-4 h-4 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                  Generating Position Plan...
                </>
              ) : (
                "Generate Position Plan \u2192"
              )}
            </button>
          )}

          {/* Back to library */}
          {!isLive && (
            <div className="flex gap-3 pb-10">
              <button
                onClick={() => router.push("/library")}
                className="flex-1 py-3 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                           text-sm font-semibold text-[var(--color-text-primary)] hover:border-[var(--color-primary)]/50 transition-colors"
              >
                Back to Library
              </button>
            </div>
          )}
      </div>
    </main>
  );
}
