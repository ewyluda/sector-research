/**
 * Dashboard-layout card for the Quick Screen phase output.
 *
 * Layout (top to bottom):
 *   1. Header row — ScoreRing + ticker + recommendation badge + company meta
 *   2. Dimension breakdown table
 *   3. Thesis + Key Risk callout boxes side-by-side
 *   4. Citation list footer
 *
 * Pure presentational — takes structured data + citations and renders.
 * Reused on both the pipeline runner page and the report page.
 */

import type { QuickScreenStructured, Citation } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { DimensionTable } from "@/components/DimensionTable";
import { CitationList } from "@/components/CitationList";

const RECOMMENDATION_COLORS: Record<string, string> = {
  GO:        "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  WATCHLIST: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  PASS:      "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
};

interface Props {
  structured: QuickScreenStructured;
  citations?: Citation[];
  ticker: string;
  companyName?: string;
  sector?: string;
}

export function QuickScreenCard({
  structured,
  citations = [],
  ticker,
  companyName,
  sector,
}: Props) {
  const recColor =
    RECOMMENDATION_COLORS[structured.recommendation] ??
    RECOMMENDATION_COLORS.PASS;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center gap-4 pb-4 border-b border-[var(--border)]">
        <ScoreRing score={structured.overall_score} size={72} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-mono font-bold text-[var(--text)] tracking-wide">
              {ticker}
            </span>
            <span
              className={`px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider ${recColor}`}
            >
              {structured.recommendation}
            </span>
          </div>
          {(companyName || sector) && (
            <div className="text-xs text-[var(--text-muted)] mt-0.5">
              {[companyName, sector].filter(Boolean).join(" · ")}
            </div>
          )}
        </div>
      </div>

      {/* Dimension breakdown */}
      <DimensionTable dimensions={structured.dimensions} />

      {/* Thesis + Key Risk side-by-side */}
      <div className="grid grid-cols-[1.4fr_1fr] gap-3 mt-2">
        <div className="rounded-lg border border-[var(--primary)]/25 bg-[var(--primary)]/5 p-3">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1">
            Thesis
          </div>
          <div className="text-xs text-[var(--text)] leading-relaxed">
            {structured.thesis}
          </div>
        </div>
        <div className="rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/5 p-3">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--warning)] mb-1">
            ⚠ Key Risk
          </div>
          <div className="text-xs text-[var(--text)] leading-relaxed">
            {structured.key_risk}
          </div>
        </div>
      </div>

      {/* Citation footer */}
      <CitationList citations={citations} />
    </div>
  );
}
