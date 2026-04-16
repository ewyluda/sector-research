"use client";

import { useState } from "react";
import type { DeepDiveCategoryStructured, CategoryOutput } from "@/lib/api";
import { AICompanionPanel } from "../panels/AICompanionPanel";
import { PanelSkeleton } from "../skeleton/PanelSkeleton";

interface DataRichSectionProps {
  id: string;
  label: string;
  score: number | null;
  structured: DeepDiveCategoryStructured | null;
  fallback?: CategoryOutput | null;
  isLive?: boolean;
  children: React.ReactNode;
}

function scoreBadge(score: number | null): string {
  if (score == null) return "bg-[var(--color-surface-alt)] text-[var(--color-text-faint)]";
  if (score >= 70) return "bg-emerald-500/15 text-emerald-400";
  if (score >= 50) return "bg-amber-500/15 text-amber-400";
  return "bg-red-500/15 text-red-400";
}

export function DataRichSection({ id, label, score, structured, fallback, isLive, children }: DataRichSectionProps) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <section id={id} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <div
        className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 flex items-center justify-between cursor-pointer select-none"
        onClick={() => setCollapsed(c => !c)}
      >
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{label}</h3>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${scoreBadge(score)}`}>
            {score != null ? `${score}/100` : "—"}
          </span>
          <svg
            className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ${collapsed ? "" : "rotate-180"}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
      {!collapsed && (
        <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 p-5">
          <div className="space-y-4">{children}</div>
          <div>
            {structured ? (
              <AICompanionPanel structured={structured} categoryLabel={label} expandAnalysis={true} fallback={fallback} />
            ) : isLive ? (
              <PanelSkeleton />
            ) : null}
          </div>
        </div>
      )}
    </section>
  );
}
