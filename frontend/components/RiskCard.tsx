/**
 * Risk Register dashboard for the Risk Stress-Test phase output.
 *
 * Layout (top to bottom):
 *   1. Header — RR ratio ring + ticker + loop status badge
 *   2. RR verdict callout
 *   3. Risk register table (risk × probability/impact/mitigation)
 *   4. Loop decision footer (if loop triggered)
 *   5. Citation list footer
 */

import type { RiskStressTestStructured, Citation } from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { CitationList } from "@/components/CitationList";

const PROB_COLORS: Record<string, string> = {
  High:   "bg-[var(--error)]/12 text-[var(--error)] border-[var(--error)]/30",
  Medium: "bg-[var(--warning)]/12 text-[var(--warning)] border-[var(--warning)]/30",
  Low:    "bg-emerald-500/12 text-emerald-400 border-emerald-500/30",
};

interface Props {
  structured: RiskStressTestStructured;
  citations?: Citation[];
  ticker: string;
  loopCount: number;
}

export function RiskCard({
  structured,
  citations = [],
  ticker,
  loopCount,
}: Props) {
  // Convert RR ratio to a 0-100 score for the ring.
  // 0:1 = 0, 2:1 = 50 (threshold), 4:1+ = 100.
  const rrScore = Math.min(100, Math.round((structured.rr_ratio / 4) * 100));

  const rrColor =
    structured.rr_ratio >= 2.0
      ? "text-emerald-400"
      : structured.rr_ratio >= 1.5
      ? "text-[var(--warning)]"
      : "text-[var(--error)]";

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center gap-4 pb-4 border-b border-[var(--border)]">
        <ScoreRing score={rrScore} size={86} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 mb-1">
            <span className="text-2xl font-mono font-bold text-[var(--text)] tracking-wide">
              {ticker}
            </span>
            <span className={`text-xl font-mono font-bold ${rrColor}`}>
              {structured.rr_ratio.toFixed(1)}:1
            </span>
            {structured.loop_required && (
              <span className="px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider bg-amber-500/10 text-amber-400 border-amber-500/30">
                LOOP BACK
              </span>
            )}
            {!structured.loop_required && (
              <span className="px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                PASS
              </span>
            )}
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            Risk Stress-Test · R/R {structured.rr_ratio.toFixed(1)}:1
            {loopCount > 0 && ` · Loop ${loopCount}/2`}
          </div>
        </div>
      </div>

      {/* RR verdict callout */}
      <div
        className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3.5"
        style={{ borderLeft: "3px solid var(--primary)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1.5">
          Risk/Reward Verdict
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.rr_verdict}
        </div>
      </div>

      {/* Risk register */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-2">
          Risk Register ({structured.risks.length} risks)
        </div>
        <div className="flex flex-col gap-2">
          {structured.risks.map((entry, i) => (
            <div
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] p-3"
            >
              <div className="flex items-start justify-between gap-3 mb-1.5">
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-semibold text-[var(--text)] leading-snug">
                    {entry.risk}
                  </div>
                  <div className="text-[10px] text-[var(--text-faint)] mt-0.5">
                    {entry.category}
                  </div>
                </div>
                <span
                  className={`flex-shrink-0 px-2 py-0.5 rounded-full border text-[10px] font-semibold ${
                    PROB_COLORS[entry.probability] ?? PROB_COLORS.Medium
                  }`}
                >
                  {entry.probability}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 mt-2">
                <div>
                  <div className="text-[9px] uppercase tracking-wider text-[var(--text-faint)] mb-0.5">
                    Impact
                  </div>
                  <div className="text-[10px] text-[var(--error)] leading-relaxed">
                    {entry.impact}
                  </div>
                </div>
                <div>
                  <div className="text-[9px] uppercase tracking-wider text-[var(--text-faint)] mb-0.5">
                    Mitigation
                  </div>
                  <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                    {entry.mitigation}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Loop decision footer (only if loop triggered) */}
      {structured.loop_required && structured.loop_reason && (
        <div
          className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3.5"
          style={{ borderLeft: "3px solid rgb(245 158 11)" }}
        >
          <div className="text-[10px] uppercase tracking-wider font-semibold text-amber-400 mb-1.5">
            Loop-Back Required
          </div>
          <div className="text-xs text-[var(--text)] leading-relaxed mb-2">
            {structured.loop_reason}
          </div>
          {structured.loop_categories.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {structured.loop_categories.map((cat) => (
                <span
                  key={cat}
                  className="px-2 py-0.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-[10px] font-medium text-amber-400"
                >
                  {cat}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Citation footer */}
      <CitationList citations={citations} />
    </div>
  );
}
