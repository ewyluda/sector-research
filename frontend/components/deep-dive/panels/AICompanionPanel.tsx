"use client";

import { useState } from "react";
import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { FindingsTable } from "./FindingsTable";
import { scoreBadge } from "../scoreColors";
import { MarkdownProse } from "../renderMarkdown";

interface AICompanionPanelProps {
  structured: DeepDiveCategoryStructured | null;
  categoryLabel: string;
  expandAnalysis?: boolean;
  /** Fallback: raw CategoryOutput shown when structured is null */
  fallback?: CategoryOutput | null;
  /**
   * Which blocks to render. `all` (default) keeps the historical behavior —
   * one column with every block. Split sections pass `summary` to render only
   * the score callout + findings table (which fits beside the chart column),
   * then render `analysis` as a full-width row underneath to reclaim the
   * empty left-column space the analysis paragraph used to leave behind.
   */
  section?: "all" | "summary" | "analysis";
}

function ScoreCallout({ score, rationale, label }: { score: number; rationale: string; label: string }) {
  return (
    <div className="rounded-lg border-l-2 border-[var(--color-primary)] bg-[var(--color-primary)]/5 p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-xs font-medium text-[var(--color-text-muted)]">{label}</span>
        <span className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded ${scoreBadge(score)}`}>
          {score}/100
        </span>
      </div>
      <p className="text-xs text-[var(--color-text-secondary)] leading-relaxed">{rationale}</p>
    </div>
  );
}

export function AICompanionPanel({ structured, categoryLabel, expandAnalysis = false, fallback, section = "all" }: AICompanionPanelProps) {
  const [analysisOpen, setAnalysisOpen] = useState(expandAnalysis);
  const [gapsOpen, setGapsOpen] = useState(expandAnalysis);

  const showSummary = section === "all" || section === "summary";
  const showAnalysis = section === "all" || section === "analysis";

  // Fallback: show raw content when structured output isn't available
  if (!structured) {
    if (!fallback || (!fallback.content && !fallback.key_findings?.length)) return null;
    return (
      <div className="space-y-4">
        {showSummary && fallback.score != null && (
          <div className="rounded-lg border-l-2 border-[var(--color-primary)] bg-[var(--color-primary)]/5 p-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-[var(--color-text-muted)]">{categoryLabel}</span>
              <span className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded ${scoreBadge(fallback.score)}`}>
                {fallback.score}/100
              </span>
            </div>
          </div>
        )}
        {showSummary && fallback.key_findings?.length > 0 && (
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
        {showAnalysis && fallback.content && (
          <details>
            <summary className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--color-text-primary)]">
              Full Analysis
            </summary>
            <MarkdownProse text={fallback.content} className="mt-2 space-y-2 text-xs text-[var(--color-text-secondary)] leading-relaxed" />
          </details>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {showSummary && (
        <ScoreCallout score={structured.score} rationale={structured.score_rationale} label={categoryLabel} />
      )}

      {showSummary && structured.key_findings.length > 0 && (
        <div>
          <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">
            Key Findings ({structured.key_findings.length})
          </h4>
          <FindingsTable findings={structured.key_findings} />
        </div>
      )}

      {showAnalysis && structured.analysis && (
        expandAnalysis ? (
          <div>
            <h4 className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider mb-2">Analysis</h4>
            <MarkdownProse text={structured.analysis} className="space-y-2 text-xs text-[var(--color-text-secondary)] leading-relaxed" />
          </div>
        ) : (
          <details open={analysisOpen} onToggle={(e) => setAnalysisOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="text-[10px] font-medium text-[var(--color-text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--color-text-primary)]">
              Full Analysis
            </summary>
            <MarkdownProse text={structured.analysis} className="mt-2 space-y-2 text-xs text-[var(--color-text-secondary)] leading-relaxed" />
          </details>
        )
      )}

      {showAnalysis && structured.data_gaps.length > 0 && (
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
