/**
 * Page — /filings/graph
 *
 * Multi-hop supply-chain graph view. Server component fetches the theme list
 * (for the theme picker dropdown); MultiHopGraphView is the client component
 * that owns root/theme/depth/direction state, URL sync, and the graph fetch.
 */

import { themes as themesApi } from "@/lib/api";
import type { Theme } from "@/lib/api";
import MultiHopGraphView from "@/components/filings/MultiHopGraphView";

export const dynamic = "force-dynamic";

export default async function FilingsGraphPage() {
  let allThemes: Theme[] = [];
  let error: string | null = null;

  try {
    allThemes = await themesApi.list();
  } catch {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text)]">
          Supply-chain graph
        </h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">
          Multi-hop counterparty relationships extracted from SEC filings.
          Pick a ticker as the root; expand into a theme to see its 2-hop
          neighbourhood.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      <MultiHopGraphView themes={allThemes} />
    </div>
  );
}
