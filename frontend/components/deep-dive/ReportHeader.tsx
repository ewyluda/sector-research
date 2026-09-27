"use client";

import { useEffect, useState } from "react";
import type { CuratedFinancials, QuickScreenStructured, PhaseStatus, ThesisStructured, ThesisStance } from "@/lib/api";
import { getModel } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";
import { useWorkspaceKickoff } from "@/lib/hooks/useWorkspaceKickoff";

interface ReportHeaderProps {
  financials: CuratedFinancials | null;
  quickScreen: QuickScreenStructured | null;
  /** Final thesis — its stance and text lead the header when present. */
  thesis?: ThesisStructured | null;
  convictionScore: number | null;
  ticker: string;
  runId?: string;
  isLive?: boolean;
  runStatus?: PhaseStatus;
}

function fmtMarketCap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${value.toFixed(0)}`;
}

function convictionTier(score: number): string {
  if (score >= 75) return "High Conviction";
  if (score >= 55) return "Moderate";
  if (score >= 35) return "Low";
  return "Very Low";
}

function relativeTime(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

function ModelStatusBadge({ ticker }: { ticker: string }) {
  const [loaded, setLoaded] = useState(false);
  const [info, setInfo] = useState<{ version: number; saved_at: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const r = await getModel(ticker);
        if (cancelled) return;
        if (r.latest_version) {
          setInfo({ version: r.latest_version.version, saved_at: r.latest_version.created_at });
        }
      } catch {
        // model not found or fetch error; show Create link
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, [ticker]);

  if (!loaded) return null;
  if (!info) {
    return (
      <a href={`/model/${ticker}#forecast`} className="text-xs text-blue-400 hover:underline">
        Create model →
      </a>
    );
  }
  const ago = relativeTime(info.saved_at);
  return (
    <a href={`/model/${ticker}#forecast`} className="text-xs text-[var(--text-muted)] hover:text-white">
      Model v{info.version} · saved {ago}
    </a>
  );
}

function StanceBadge({ stance }: { stance: ThesisStance }) {
  const styles: Record<ThesisStance, string> = {
    long: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    short: "bg-red-500/15 text-red-400 border-red-500/30",
    avoid: "bg-[var(--color-surface-alt)] text-[var(--color-text-muted)] border-[var(--color-border)]",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase tracking-wide border ${styles[stance]}`}
      title="Final call from the thesis phase"
    >
      {stance}
    </span>
  );
}

/** Quick screen = a coarse pre-screen on annual data. Shown muted and labelled,
 *  so it can't be mistaken for the final call (it once read GO over a short thesis). */
function PreScreenChip({ recommendation }: { recommendation: "GO" | "WATCHLIST" | "PASS" }) {
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide border border-[var(--color-border)] text-[var(--color-text-muted)]"
      title="Quick-screen pre-screen on annual data — not the final call"
    >
      Quick screen: {recommendation}
    </span>
  );
}

export function ReportHeader({ financials, quickScreen, thesis, convictionScore, ticker, runId, isLive, runStatus }: ReportHeaderProps) {
  const stance = thesis?.stance ?? null;
  // Callouts: the final thesis when it exists, else the quick screen (live runs
  // before the thesis phase finishes).
  const calloutThesis = thesis?.core_thesis ?? quickScreen?.thesis ?? null;
  const bearPoint = thesis?.bear_case?.[0];
  const calloutRisk = bearPoint ? `${bearPoint.title} — ${bearPoint.evidence}` : quickScreen?.key_risk ?? null;
  const targets = thesis?.price_targets ?? null;
  const { status: preflight, reasons } = useWorkspacePreflight(ticker, runId);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const workspaceTooltip = reasons.length > 0 ? reasons.join(" • ") : "Run a workspace refresh for this ticker";
  const { kickOff, busy } = useWorkspaceKickoff({ ticker, researchRunId: runId, inFlightRunId });

  return (
    <section id="report_header" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      {/* Top row: identity + conviction ring */}
      <div className="p-5 border-b border-[var(--color-border)] flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold font-mono text-[var(--color-text-primary)]">
                <a href={`/company/${ticker}`} className="hover:underline" title="Open company workspace">
                  {ticker}
                </a>
              </h1>
              {stance && <StanceBadge stance={stance} />}
              {quickScreen && <PreScreenChip recommendation={quickScreen.recommendation} />}
              <span data-print-hide="true" className="flex items-center gap-2">
                <ModelStatusBadge ticker={ticker} />
                {runStatus === "completed" && (
                  <button
                    type="button"
                    onClick={() => void kickOff()}
                    disabled={busy || !canKickOff}
                    className="text-xs px-2 py-1 rounded border border-[var(--border)] hover:border-[var(--text-faint)] disabled:opacity-50 disabled:cursor-not-allowed text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
                    title={workspaceTooltip}
                  >
                    {busy ? "Launching..." : inFlightRunId ? "View running →" : "Refresh workspace →"}
                  </button>
                )}
                <a
                  href={`/company/${ticker}`}
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] hover:underline"
                >
                  Company →
                </a>
              </span>
            </div>
            {financials && (
              <>
                <p className="text-sm text-[var(--color-text-primary)] mt-0.5">{financials.company_name}</p>
                <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                  {[
                    financials.sector,
                    financials.industry,
                    fmtMarketCap(financials.market_cap),
                    `$${financials.current_price.toFixed(2)}`,
                  ].join(" \u00B7 ")}
                </p>
              </>
            )}
          </div>
        </div>
        <div className="shrink-0 flex flex-col items-center gap-1">
          {convictionScore != null ? (
            <>
              <ScoreRing score={convictionScore} size={92} label={stance ? `Conviction · ${stance}` : "Conviction"} />
              <span className="text-[10px] font-medium text-[var(--color-text-muted)] whitespace-nowrap">
                {convictionTier(convictionScore)}
              </span>
            </>
          ) : isLive ? (
            <>
              <div className="w-[92px] h-[92px] rounded-full bg-[var(--color-surface-alt)] animate-pulse" />
              <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Conviction</span>
            </>
          ) : null}
        </div>
      </div>

      {targets && (
        <div className="px-5 py-2 border-b border-[var(--color-border)] text-xs text-[var(--color-text-muted)] font-mono">
          Targets{thesis?.time_horizon ? ` (${thesis.time_horizon})` : ""}: bear ${targets.bear.toFixed(2)} · base ${targets.base.toFixed(2)} · bull ${targets.bull.toFixed(2)}
        </div>
      )}

      {/* Thesis / Key Risk callouts */}
      {calloutThesis && calloutRisk && (
        <div className="grid grid-cols-1 md:grid-cols-2">
          <div className="p-5 border-b md:border-b-0 md:border-r border-[var(--color-border)]">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-400 mb-1">Thesis</p>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">{calloutThesis}</p>
          </div>
          <div className="p-5">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-red-400 mb-1">{bearPoint ? "Main bear point" : "Key Risk"}</p>
            <p className="text-sm text-[var(--color-text-primary)] leading-relaxed">{calloutRisk}</p>
          </div>
        </div>
      )}
    </section>
  );
}
