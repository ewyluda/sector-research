"use client";

import { useState, useEffect, useRef } from "react";
import { SECTION_GROUPS, SECTIONS } from "./sections";

export function SectionNav({ ticker }: { ticker?: string } = {}) {
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
        data-print-hide="true"
        className={`sticky top-14 z-30 transition-shadow ${
          stuck
            ? "bg-[var(--color-bg)]/95 backdrop-blur shadow-md border-b border-[var(--color-border)]"
            : "bg-transparent"
        }`}
      >
        <div className="flex overflow-x-auto items-center px-2 py-2 scrollbar-hide">
          {SECTION_GROUPS.map((group, groupIdx) => (
            <div key={group.title} className="flex items-center gap-1 shrink-0">
              {groupIdx > 0 && (
                <span
                  aria-hidden="true"
                  className="mx-1.5 h-4 w-px bg-[var(--color-border)] shrink-0"
                />
              )}
              {group.items.map(({ id, label }) => (
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
          ))}
          {ticker && (
            <a
              href={`/model/${ticker}#forecast`}
              className="ml-auto px-3 py-1 rounded text-sm text-blue-400 hover:bg-[var(--surface)] shrink-0"
            >
              Model →
            </a>
          )}
        </div>
      </nav>
    </>
  );
}
