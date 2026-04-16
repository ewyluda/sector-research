"use client";

import type { DeepDiveFinding } from "@/lib/api";

interface RAGStripProps {
  findings: DeepDiveFinding[];
  score: number;
}

function severityColor(score: number): { bg: string; text: string; label: string; icon: React.ReactNode } {
  if (score >= 70) return {
    bg: "bg-emerald-500/20", text: "text-emerald-400", label: "Low",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  };
  if (score >= 50) return {
    bg: "bg-amber-500/20", text: "text-amber-400", label: "Medium",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  };
  return {
    bg: "bg-red-500/20", text: "text-red-400", label: "High",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
  };
}

export function RAGStrip({ findings, score }: RAGStripProps) {
  const sev = severityColor(score);
  return (
    <div className="space-y-1">
      {findings.map((f, i) => (
        <div key={i} className={`flex items-center gap-2 rounded-md px-3 py-1.5 ${sev.bg}`}>
          <span className={`flex items-center gap-1 ${sev.text} shrink-0`}>
            {sev.icon}
            <span className="text-[10px] font-semibold uppercase w-12">{sev.label}</span>
          </span>
          <span className="text-xs text-[var(--color-text-primary)] leading-snug">{f.finding}</span>
        </div>
      ))}
    </div>
  );
}
