"use client";

import { useState } from "react";
import { MarkdownProse } from "@/components/deep-dive/renderMarkdown";
import {
  earnings,
  type EarningsBoardEntry,
  type Verdict,
  type ThesisPrintVerdictRow,
  type BriefResponse,
} from "@/lib/api";

interface Props {
  entry: EarningsBoardEntry;
  onVerdictGenerated?: (verdict: ThesisPrintVerdictRow) => void;
}

const VERDICT_PILL: Record<Verdict, string> = {
  confirms:     "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  threatens:    "bg-red-500/10 text-red-400 border-red-500/30",
  neutral:      "bg-slate-500/10 text-[var(--text-muted)] border-slate-500/30",
  insufficient: "bg-amber-500/10 text-amber-400 border-amber-500/30",
};

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(1)}%`;
}

function fmtUSD(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

// ── Safe markdown renderer (no innerHTML) ───────────────────────────────────

/**
 * Render a small subset of markdown as React nodes — paragraphs, bullet
 * lists (`- ` lines), and `**bold**` spans. Anything else is rendered as
 * plain text. Safe by construction: no innerHTML, no HTML injection.
 *
 * Haiku output for this feature is constrained to bullets + bold by the
 * system prompt, so this renderer is sufficient. If/when the project
 * adopts a markdown library (e.g. react-markdown), swap this for that.
 */
function SafeMarkdownBlock({ source }: { source: string }) {
  return <MarkdownProse text={source} className="space-y-2 text-sm text-[var(--text)]" />;
}

// ── Drawer dispatcher ───────────────────────────────────────────────────────

export function EarningsDrawer({ entry, onVerdictGenerated }: Props) {
  if (!entry.print) return null;
  if (entry.verdict) return <VerdictBlock entry={entry} />;
  if (entry.phase === "post") return <PostEarningsBlock entry={entry} onVerdictGenerated={onVerdictGenerated} />;
  if (entry.phase === "post_pending") return <PendingActualsBlock entry={entry} />;
  return <PreEarningsBlock entry={entry} />;
}

// ── Pre-print ───────────────────────────────────────────────────────────────

function PreEarningsBlock({ entry }: { entry: EarningsBoardEntry }) {
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    if (!entry.print) return;
    setLoading(true);
    setErr(null);
    try {
      const out = await earnings.brief(entry.run_id, entry.print.id);
      setBrief(out);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }

  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-[var(--bg)]/40 border-t border-[var(--surface)]">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-[var(--text-muted)]">
        <span><span className="text-[var(--text-faint)]">Date:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-[var(--text-faint)]">EPS est:</span> {p.eps_estimated?.toFixed(2) ?? "—"}</span>
        <span><span className="text-[var(--text-faint)]">Rev est:</span> {fmtUSD(p.revenue_estimated)}</span>
      </div>
      {entry.matched_catalyst && entry.matched_catalyst.signposts.length > 0 && (
        <div className="mt-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] mb-1">Signposts</div>
          <ul className="list-disc list-inside text-xs text-[var(--text-muted)] space-y-0.5">
            {entry.matched_catalyst.signposts.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={generate}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-[var(--border)] hover:border-[var(--text-faint)] disabled:opacity-50"
        >
          {loading ? "Generating…" : brief ? "Regenerate brief" : "Generate pre-earnings brief"}
        </button>
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
      {brief && (
        <div className="mt-3">
          <SafeMarkdownBlock source={brief.summary_md} />
        </div>
      )}
    </div>
  );
}

// ── Post-print, actuals pending (issue #52) ─────────────────────────────────

function PendingActualsBlock({ entry }: { entry: EarningsBoardEntry }) {
  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-[var(--bg)]/40 border-t border-[var(--surface)]">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-[var(--text-muted)]">
        <span><span className="text-[var(--text-faint)]">Reported:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-[var(--text-faint)]">EPS est:</span> {p.eps_estimated?.toFixed(2) ?? "—"}</span>
        <span><span className="text-[var(--text-faint)]">Rev est:</span> {fmtUSD(p.revenue_estimated)}</span>
      </div>
      <p className="mt-2 text-xs text-amber-400">
        Awaiting actuals — the nightly earnings refresh (21:00 UTC) hasn&apos;t landed yet. Estimates shown.
      </p>
    </div>
  );
}

// ── Post-print, no verdict yet ──────────────────────────────────────────────

function PostEarningsBlock({
  entry,
  onVerdictGenerated,
}: {
  entry: EarningsBoardEntry;
  onVerdictGenerated?: (v: ThesisPrintVerdictRow) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function generate() {
    if (!entry.print) return;
    setLoading(true);
    setErr(null);
    try {
      const v = await earnings.verdict(entry.run_id, entry.print.id);
      onVerdictGenerated?.(v);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }

  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-[var(--bg)]/40 border-t border-[var(--surface)]">
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-[var(--text-muted)]">
        <span><span className="text-[var(--text-faint)]">Reported:</span> {p.earnings_date} ({p.fiscal_year}Q{p.fiscal_quarter})</span>
        <span><span className="text-[var(--text-faint)]">EPS surprise:</span> <strong>{fmtPct(p.eps_surprise_pct)}</strong></span>
        <span><span className="text-[var(--text-faint)]">Rev surprise:</span> <strong>{fmtPct(p.revenue_surprise_pct)}</strong></span>
        <span><span className="text-[var(--text-faint)]">Guidance:</span> {p.guidance_direction ?? "—"}</span>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={generate}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-emerald-700 text-emerald-400 hover:border-emerald-500 disabled:opacity-50"
        >
          {loading ? "Running thesis-check…" : "Run thesis-check"}
        </button>
        {err && <span className="text-xs text-red-400">{err}</span>}
      </div>
    </div>
  );
}

// ── Verdict rendered ────────────────────────────────────────────────────────

function VerdictBlock({ entry }: { entry: EarningsBoardEntry }) {
  const v = entry.verdict!;
  const p = entry.print!;
  return (
    <div data-print-hide="true" className="px-4 py-3 bg-[var(--bg)]/40 border-t border-[var(--surface)]">
      <div className="flex items-center gap-3 mb-2">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-semibold ${VERDICT_PILL[v.verdict]}`}>
          {v.verdict}
        </span>
        <span className="text-xs text-[var(--text-faint)]">
          {p.earnings_date} · {p.fiscal_year}Q{p.fiscal_quarter} ·
          EPS {fmtPct(p.eps_surprise_pct)} · Rev {fmtPct(p.revenue_surprise_pct)} ·
          Guidance {p.guidance_direction ?? "—"}
        </span>
      </div>
      <SafeMarkdownBlock source={v.summary_md} />
      {v.pillars_addressed.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {v.pillars_addressed.map((pillar) => (
            <span key={pillar} className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--surface)] border border-[var(--border)] text-[var(--text-muted)]">
              {pillar}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
