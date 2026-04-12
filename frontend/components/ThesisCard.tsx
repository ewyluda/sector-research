/**
 * Analyst Memo dashboard for the Thesis Construction phase output.
 *
 * Layout (top to bottom):
 *   1. Header — ScoreRing (conviction) + ticker + thesis status badge
 *   2. Core thesis callout (teal-tinted, left-bordered)
 *   3. Bull/Bear columns (symmetric two-column layout)
 *   4. Variant perception callout (rust-tinted, left-bordered)
 *   5. Catalyst list (timeframe + description rows)
 *   6. Conviction rationale footer
 *   7. Citation list footer
 */

import type { ThesisStructured, Citation } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { BullBearColumns } from "@/components/BullBearColumns";
import { CatalystList } from "@/components/CatalystList";
import { CitationList } from "@/components/CitationList";

const STATUS_COLORS: Record<string, string> = {
  "ON TRACK": "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  DRIFTING:   "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  BROKEN:     "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  PENDING:    "bg-[var(--surface)] text-[var(--text-faint)] border-[var(--border)]",
};

interface Props {
  structured: ThesisStructured;
  citations?: Citation[];
  ticker: string;
  thesisStatus: string;
}

export function ThesisCard({
  structured,
  citations = [],
  ticker,
  thesisStatus,
}: Props) {
  const statusColor =
    STATUS_COLORS[thesisStatus] ?? STATUS_COLORS.PENDING;

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
      <div className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3.5"
           style={{ borderLeft: "3px solid var(--primary)" }}>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1.5">
          Core Thesis
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.core_thesis}
        </div>
      </div>

      {/* Bull / Bear columns */}
      <BullBearColumns bull={structured.bull_case} bear={structured.bear_case} />

      {/* Variant perception callout */}
      <div className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/4 p-3.5"
           style={{ borderLeft: "3px solid var(--warning)" }}>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--warning)] mb-1.5">
          ◆ Variant Perception
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.variant_perception}
        </div>
      </div>

      {/* Catalyst list */}
      <CatalystList catalysts={structured.catalysts} />

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
