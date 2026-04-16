"use client";

import { useState, useEffect } from "react";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "financial_health", label: "Financial" },
  { id: "growth_earnings", label: "Growth" },
  { id: "technical_market_structure", label: "Technical" },
  { id: "cross_category", label: "Cross-Cat" },
  { id: "business_quality", label: "Business" },
  { id: "supply_chain", label: "Supply" },
  { id: "macro_regime", label: "Macro" },
  { id: "risk_assessment", label: "Risk" },
  { id: "management_governance", label: "Mgmt" },
  { id: "sentiment_narrative", label: "Sentiment" },
  { id: "future_durability", label: "Future" },
];

export function MobileSectionNav() {
  const [active, setActive] = useState("overview");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        }
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[var(--color-bg)]/95 backdrop-blur border-t border-[var(--color-border)]">
      <div className="flex overflow-x-auto gap-1 px-3 py-2 scrollbar-hide">
        {SECTIONS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors ${
              active === id
                ? "bg-[var(--color-primary)] text-white"
                : "bg-[var(--color-surface-alt)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </nav>
  );
}
