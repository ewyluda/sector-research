"use client";

import { useState } from "react";
import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { FindingsTable } from "./FindingsTable";

interface AICompanionPanelProps {
  structured: DeepDiveCategoryStructured | null;
  categoryLabel: string;
  expandAnalysis?: boolean;
  /** Fallback: raw CategoryOutput shown when structured is null */
  fallback?: CategoryOutput | null;
}

function scoreColor(score: number): string {
  if (score >= 70) return "bg-emerald-500/15 text-emerald-400";
  if (score >= 50) return "bg-amber-500/15 text-amber-400";
  return "bg-red-500/15 text-red-400";
}

export function AICompanionPanel({ structured, categoryLabel, expandAnalysis = false, fallback }: AICompanionPanelProps) {
  const [analysisOpen, setAnalysisOpen] = useState(expandAnalysis);
  const [gapsOpen, setGapsOpen] = useState(expandAnalysis);

  // Fallback: show raw content when structured output isn't available
  if (!structured) {
    if (!fallback || (!fallback.content && !fallback.key_findings?.length)) return null;
    return (
      <div className="space-y-4">
        {fallback.score != null && (
          <div className="rounded-lg border-l-2 border-[var(--color-primary)] bg-[var(--color-primary)]/5 p-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--color-text-muted)]">{categoryLabel}</span>
              <span className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded ${scoreColor(fallback.score)}`}>
                {fallback.score}/100
              </span>
            </div>
          </div>
        )}
        {fallback.key_findings?.length > 0 && (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
              Key Findings ({fallback.key_findings.length})
            </h4>
            <ul className="space-y-1">
              {fallback.key_findings.map((f, i) => (
                <li key={i} className="text-xs text-[var(--color-text-primary)] leading-snug">· {f}</li>
              ))}
            </ul>
          </div>
        )}
        {fallback.content && (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Analysis</h4>
            <p className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
              {fallback.content}
            </p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Score + rationale */}
      <div className="rounded-lg border-l-2 border-[var(--color-primary)] bg-[var(--color-primary)]/5 p-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-[var(--color-text-muted)]">{categoryLabel}</span>
          <span className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded ${scoreColor(structured.score)}`}>
            {structured.score}/100
          </span>
        </div>
        <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{structured.score_rationale}</p>
      </div>

      {/* Key findings table */}
      {structured.key_findings.length > 0 && (
        <div>
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
            Key Findings ({structured.key_findings.length})
          </h4>
          <FindingsTable findings={structured.key_findings} />
        </div>
      )}

      {/* Analysis — accordion or inline */}
      {structured.analysis && (
        expandAnalysis ? (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Analysis</h4>
            <p className="text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
              {structured.analysis}
            </p>
          </div>
        ) : (
          <details open={analysisOpen} onToggle={(e) => setAnalysisOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--color-text-primary)]">
              Full Analysis
            </summary>
            <p className="mt-2 text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap leading-relaxed">
              {structured.analysis}
            </p>
          </details>
        )
      )}

      {/* Data gaps — accordion or inline */}
      {structured.data_gaps.length > 0 && (
        expandAnalysis ? (
          <div className="rounded-lg bg-[var(--color-warning)]/5 border border-[var(--color-warning)]/20 p-3">
            <h4 className="text-[10px] font-medium text-[var(--color-warning)] uppercase tracking-wider mb-1">
              Data Gaps ({structured.data_gaps.length})
            </h4>
            {structured.data_gaps.map((gap, i) => (
              <p key={i} className="text-xs text-[var(--color-text-muted)]">· {gap}</p>
            ))}
          </div>
        ) : (
          <details open={gapsOpen} onToggle={(e) => setGapsOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="text-[10px] font-medium text-[var(--color-warning)] uppercase tracking-wider cursor-pointer">
              Data Gaps ({structured.data_gaps.length})
            </summary>
            <div className="mt-2 rounded-lg bg-[var(--color-warning)]/5 border border-[var(--color-warning)]/20 p-3">
              {structured.data_gaps.map((gap, i) => (
                <p key={i} className="text-xs text-[var(--color-text-muted)]">· {gap}</p>
              ))}
            </div>
          </details>
        )
      )}
    </div>
  );
}
