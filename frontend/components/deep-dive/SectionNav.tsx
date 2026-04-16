"use client";

import { useState, useEffect, useRef } from "react";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "financial_health", label: "Financial Health" },
  { id: "growth_earnings", label: "Growth & Earnings" },
  { id: "technical_market_structure", label: "Technical" },
  { id: "cross_category", label: "Correlations" },
  { id: "business_quality", label: "Business Quality" },
  { id: "supply_chain", label: "Supply Chain" },
  { id: "macro_regime", label: "Macro" },
  { id: "risk_assessment", label: "Risk" },
  { id: "management_governance", label: "Management" },
  { id: "sentiment_narrative", label: "Sentiment" },
  { id: "future_durability", label: "Future" },
];

export function SectionNav() {
  const [active, setActive] = useState("overview");
  const [stuck, setStuck] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        }
      },
      { rootMargin: "-20% 0px -75% 0px" }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([entry]) => setStuck(!entry.isIntersecting),
      { threshold: 0 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <>
      <div ref={sentinelRef} className="h-0" />
      <nav
        className={`sticky top-14 z-30 transition-shadow ${
          stuck
            ? "bg-[var(--color-bg)]/95 backdrop-blur shadow-md border-b border-[var(--color-border)]"
            : "bg-transparent"
        }`}
      >
        <div className="flex overflow-x-auto gap-1 px-2 py-2 scrollbar-hide">
          {SECTIONS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors cursor-pointer ${
                active === id
                  ? "bg-[var(--color-primary)] text-white"
                  : stuck
                    ? "bg-[var(--color-surface-alt)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>
    </>
  );
}
