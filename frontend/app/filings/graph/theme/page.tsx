/**
 * Page — /filings/graph/theme
 *
 * Theme-wide force-directed supply-chain graph. Server component fetches
 * the theme list; ThemeGraphView owns ?theme= URL state and the graph
 * fetch + rendering.
 */
import Link from "next/link";
import { themes as themesApi } from "@/lib/api";
import type { Theme } from "@/lib/api";
import ThemeGraphView from "@/components/filings/ThemeGraphView";

export const dynamic = "force-dynamic";

export default async function ThemeGraphPage() {
  let allThemes: Theme[] = [];
  let error: string | null = null;

  try {
    allThemes = await themesApi.list();
  } catch {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">
            Theme graph map
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            Force-directed view of every extracted relationship touching a
            theme&apos;s tickers. Hubs and dense clusters surface structure
            the per-ticker view hides.
          </p>
        </div>
        <Link
          href="/filings/graph"
          className="shrink-0 text-sm text-[var(--color-accent)] hover:underline"
        >
          Root graph view →
        </Link>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      <ThemeGraphView themes={allThemes} />
    </div>
  );
}
