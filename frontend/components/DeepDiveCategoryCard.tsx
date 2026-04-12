/**
 * Structured renderer for a single deep-dive category.
 *
 * Layout (top to bottom):
 *   1. Score rationale callout
 *   2. Key findings — cards with finding + evidence
 *   3. Analysis prose
 *   4. Data gap warnings (if any)
 */

import type { DeepDiveCategoryStructured } from "@/lib/api";

interface Props {
  structured: DeepDiveCategoryStructured;
  categoryLabel: string;
}

export function DeepDiveCategoryCard({ structured, categoryLabel }: Props) {
  return (
    <div className="flex flex-col gap-3">
      {/* Score rationale callout */}
      <div
        className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3"
        style={{ borderLeft: "3px solid var(--primary)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1">
          {categoryLabel} — {structured.score}/100
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.score_rationale}
        </div>
      </div>

      {/* Key findings */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1.5">
          Key Findings ({structured.key_findings.length})
        </div>
        <div className="flex flex-col gap-1.5">
          {structured.key_findings.map((f, i) => (
            <div
              key={i}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] p-2.5"
            >
              <div className="text-xs font-medium text-[var(--text)] leading-snug">
                {f.finding}
              </div>
              <div className="text-[10px] text-[var(--text-faint)] mt-1 leading-relaxed">
                {f.evidence}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Analysis */}
      <div>
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1.5">
          Analysis
        </div>
        <div className="text-sm text-[var(--text-muted)] whitespace-pre-wrap leading-relaxed">
          {structured.analysis}
        </div>
      </div>

      {/* Data gaps (if any) */}
      {structured.data_gaps.length > 0 && (
        <div className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/5 p-2.5">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--warning)] mb-1">
            Data Gaps
          </div>
          <ul className="space-y-0.5">
            {structured.data_gaps.map((gap, i) => (
              <li key={i} className="text-[10px] text-[var(--text-muted)] leading-relaxed flex gap-1.5">
                <span className="text-[var(--warning)] flex-shrink-0">!</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
