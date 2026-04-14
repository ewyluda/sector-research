"use client";

import { useEffect, useState } from "react";

interface SidebarItem {
  key: string;
  label: string;
  tier: "overview" | "data-rich" | "mixed" | "qualitative" | "synthesis";
}

const ITEMS: SidebarItem[] = [
  { key: "report_header", label: "Overview", tier: "overview" },
  { key: "financial_health", label: "Financial Health", tier: "data-rich" },
  { key: "growth_earnings", label: "Growth & Earnings", tier: "data-rich" },
  { key: "technical_market_structure", label: "Technical & Market", tier: "data-rich" },
  { key: "cross_category", label: "Correlations", tier: "data-rich" },
  { key: "business_quality", label: "Business Quality", tier: "mixed" },
  { key: "macro_regime", label: "Macro & Regime", tier: "mixed" },
  { key: "risk_assessment", label: "Risk Assessment", tier: "mixed" },
  { key: "management_governance", label: "Management", tier: "qualitative" },
  { key: "sentiment_narrative", label: "Sentiment", tier: "qualitative" },
  { key: "future_durability", label: "Future", tier: "qualitative" },
  { key: "thesis_section", label: "Thesis", tier: "synthesis" },
  { key: "risk_section", label: "Risk Stress-Test", tier: "synthesis" },
];

const TIER_LABELS: Record<string, string> = {
  overview: "OVERVIEW",
  "data-rich": "DATA-RICH",
  mixed: "MIXED",
  qualitative: "QUALITATIVE",
  synthesis: "SYNTHESIS",
};

function scoreDot(score: number | null, status?: string): string {
  if (status === "running") return "bg-[var(--color-primary)] animate-pulse";
  if (status === "error") return "bg-red-400";
  if (score == null) return "bg-[var(--color-text-faint)]/30";
  if (score >= 70) return "bg-emerald-400";
  if (score >= 50) return "bg-amber-400";
  return "bg-red-400";
}

interface DashboardSidebarProps {
  scores: Record<string, number>;
  statuses?: Record<string, string>;
}

export function DashboardSidebar({ scores, statuses }: DashboardSidebarProps) {
  const [activeId, setActiveId] = useState<string>("");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
          }
        }
      },
      { rootMargin: "-20% 0px -60% 0px" }
    );

    for (const item of ITEMS) {
      const el = document.getElementById(item.key);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  let currentTier = "";

  return (
    <nav className="sticky top-4 space-y-0.5 w-48 shrink-0 hidden lg:block">
      {ITEMS.map((item) => {
        const showTier = item.tier !== currentTier;
        if (showTier) currentTier = item.tier;
        const isActive = activeId === item.key;
        const score = scores[item.key] ?? null;
        const status = statuses?.[item.key];

        return (
          <div key={item.key}>
            {showTier && (
              <p className="text-[8px] font-semibold text-[var(--color-text-faint)] uppercase tracking-widest mt-3 mb-1 px-2">
                {TIER_LABELS[item.tier]}
              </p>
            )}
            <a
              href={`#${item.key}`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(item.key)?.scrollIntoView({ behavior: "smooth" });
              }}
              className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded-md text-xs transition-colors ${
                isActive
                  ? "bg-[var(--color-primary)]/10 text-[var(--color-primary)]"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-alt)]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full shrink-0 ${scoreDot(score, status)}`} />
                <span className="leading-tight">{item.label}</span>
              </div>
              <span className="text-[10px] font-mono opacity-70">{score ?? "—"}</span>
            </a>
          </div>
        );
      })}
    </nav>
  );
}
