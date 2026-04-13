"use client";

import type { DeepDiveFinding } from "@/lib/api";

interface RAGStripProps {
  findings: DeepDiveFinding[];
  score: number;
}

function severityColor(score: number): { bg: string; text: string; label: string } {
  if (score >= 70) return { bg: "bg-emerald-500/20", text: "text-emerald-400", label: "Low" };
  if (score >= 50) return { bg: "bg-amber-500/20", text: "text-amber-400", label: "Medium" };
  return { bg: "bg-red-500/20", text: "text-red-400", label: "High" };
}

export function RAGStrip({ findings, score }: RAGStripProps) {
  const sev = severityColor(score);
  return (
    <div className="space-y-1">
      {findings.map((f, i) => (
        <div key={i} className={`flex items-center gap-2 rounded-md px-3 py-1.5 ${sev.bg}`}>
          <span className={`text-[10px] font-semibold uppercase ${sev.text} w-12 shrink-0`}>{sev.label}</span>
          <span className="text-xs text-[var(--color-text-primary)] leading-snug">{f.finding}</span>
        </div>
      ))}
    </div>
  );
}
