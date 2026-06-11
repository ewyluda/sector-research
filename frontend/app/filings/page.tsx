/**
 * Page — /filings
 *
 * SEC EDGAR filing sections grouped by theme → ticker.
 * Server component fetches the theme list; FilingsWorkbench (client) owns the
 * header chore-count chip and the per-theme panels so users can trigger
 * on-demand ingest and drill into sections without a full-page reload.
 */

import { themes as themesApi } from "@/lib/api";
import type { Theme } from "@/lib/api";
import FilingsWorkbench from "@/components/filings/FilingsWorkbench";
import CurationPanel from "@/components/filings/CurationPanel";
import { ProspectusList } from "@/components/prospectus/ProspectusList";

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
    <FilingsWorkbench themes={themesWithTickers}>
      <details className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
        <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-[var(--text)]">
          Prospectus reports
        </summary>
        <div className="px-4 pb-4">
          <ProspectusList />
        </div>
      </details>

      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
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
    </FilingsWorkbench>
  );
}
