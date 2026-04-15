/**
 * Page — /filings
 *
 * SEC EDGAR filing sections grouped by theme → ticker.
 * Server component fetches the theme list; the per-theme panels are rendered
 * client-side so users can trigger on-demand ingest and drill into sections
 * without a full-page reload.
 */

import { themes as themesApi } from "@/lib/api";
import type { Theme } from "@/lib/api";
import ThemeFilingsPanel from "@/components/filings/ThemeFilingsPanel";
import CurationPanel from "@/components/filings/CurationPanel";

export const dynamic = "force-dynamic";

export default async function FilingsPage() {
  let allThemes: Theme[] = [];
  let error: string | null = null;

  try {
    allThemes = await themesApi.list();
  } catch {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  const themesWithTickers = allThemes.filter(
    (t) => Array.isArray(t.seed_tickers) && t.seed_tickers.length > 0
  );

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold text-[var(--text)]">SEC Filings</h1>
        <p className="text-sm text-[var(--text-muted)] mt-0.5">
          Narrative sections from the latest 10-K, 10-Q, and DEF 14A filings —
          grouped by thesis.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {!error && themesWithTickers.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-[var(--border)] py-16 text-center">
          <p className="text-[var(--text-muted)] text-sm">
            No themes with seed tickers yet.
          </p>
          <p className="text-[var(--text-faint)] text-xs mt-1">
            Add seed tickers to a theme to start browsing its filings.
          </p>
        </div>
      )}

      <CurationPanel />

      <div className="space-y-10">
        {themesWithTickers.map((t) => (
          <ThemeFilingsPanel key={t.id} theme={t} />
        ))}
      </div>
    </div>
  );
}
