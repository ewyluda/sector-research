"use client";

/**
 * Client shell for /filings: owns the page header (with the ingest-chore
 * count chip) and the per-theme panels. The chore count is lifted from the
 * ticker cards — each card reports whether its ticker has any ingested
 * sections after its own filings fetch (the data lives in the cards, not in
 * the page's server fetch).
 */

import { useCallback, useState, type ReactNode } from "react";
import type { Theme } from "@/lib/api";
import ThemeFilingsPanel from "./ThemeFilingsPanel";
import { NewProspectusButton } from "@/components/prospectus/NewProspectusButton";

export default function FilingsWorkbench({
  themes,
  children,
}: {
  themes: Theme[];
  children?: ReactNode;
}) {
  // ticker → has ingested sections (unknown tickers absent until reported)
  const [sectionsState, setSectionsState] = useState<Record<string, boolean>>({});

  const onSectionsState = useCallback((ticker: string, hasSections: boolean) => {
    setSectionsState((prev) =>
      prev[ticker] === hasSections ? prev : { ...prev, [ticker]: hasSections },
    );
  }, []);

  const choreCount = Object.values(sectionsState).filter((has) => !has).length;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">SEC Filings</h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            Narrative sections from the latest 10-K, 10-Q, and DEF 14A filings —
            grouped by thesis.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {choreCount > 0 && (
            <span className="text-[11px] px-2.5 py-1 rounded-full border border-[var(--border)] bg-[var(--surface)] text-[var(--text-muted)] whitespace-nowrap">
              {choreCount} ticker{choreCount !== 1 ? "s" : ""} ready to ingest
            </span>
          )}
          <NewProspectusButton />
        </div>
      </div>

      {children}

      <div className="space-y-10">
        {themes.map((t) => (
          <ThemeFilingsPanel key={t.id} theme={t} onSectionsState={onSectionsState} />
        ))}
      </div>
    </div>
  );
}
