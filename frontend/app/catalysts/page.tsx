/**
 * Page — /catalysts
 *
 * Fleet-wide catalyst calendar. Server component fetches the proximity-
 * bucketed catalyst list (latest run per ticker); the bucket sections
 * and per-row signposts toggle are client components.
 */

import { CatalystsView } from "@/components/catalysts/CatalystsView";
import { getCatalysts } from "@/lib/api";
import type { CatalystListResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function CatalystsPage() {
  let data: CatalystListResponse | null = null;
  let error: string | null = null;

  try {
    data = await getCatalysts();
  } catch {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 flex flex-col gap-6">
      <header>
        <h1 className="text-xl font-semibold text-[var(--text)] tracking-wide">
          Catalysts
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Economic releases, universe earnings, and thesis catalysts in one view.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
          {error}
        </div>
      )}

      {data && <CatalystsView buckets={data.buckets} />}
    </main>
  );
}
