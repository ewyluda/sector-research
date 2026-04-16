/**
 * Page 1 — Theme Dashboard (/)
 * Grid of curated themes. Each card shows top 3 companies, velocity summary,
 * surprise signal banner, and last refreshed timestamp.
 * Data fetched server-side.
 */

import Link from "next/link";
import { themes } from "@/lib/api";
import type { Theme } from "@/lib/api";

export const dynamic = "force-dynamic";

function ThemeCard({ theme }: { theme: Theme }) {
  const seedCount = Array.isArray(theme.seed_tickers) ? theme.seed_tickers.length : 0;
  const hasParent = !!theme.parent_theme_id;

  return (
    <Link
      href={`/theme/${theme.id}`}
      className="group block rounded-xl border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--primary)]/50 hover:shadow-sm transition-all overflow-hidden"
    >
      {/* Card header */}
      <div className="bg-[var(--teal-dark)] px-5 py-4">
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-white font-semibold text-sm leading-snug">{theme.name}</h2>
          {hasParent && (
            <span className="shrink-0 text-[10px] text-[var(--teal-light)] border border-[var(--teal-light)]/40 rounded-full px-2 py-0.5">
              sub-theme
            </span>
          )}
        </div>
        {theme.description && (
          <p className="text-[var(--teal-lighter)] text-xs mt-1 line-clamp-2">{theme.description}</p>
        )}
      </div>

      {/* Card body */}
      <div className="px-5 py-4 space-y-3">
        {/* Signal building state when no seed tickers */}
        {seedCount === 0 ? (
          <div className="flex items-center gap-2 text-xs text-[var(--text-faint)]">
            <span className="w-1.5 h-1.5 rounded-full bg-[var(--text-faint)] animate-pulse" />
            Signal building…
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-[10px] text-[var(--text-faint)] uppercase tracking-wide font-medium">
              Seed tickers
            </p>
            <div className="flex flex-wrap gap-1">
              {(Array.isArray(theme.seed_tickers) ? theme.seed_tickers : [])
                .slice(0, 6)
                .map((t: string) => (
                  <span
                    key={t}
                    className="text-[11px] font-mono font-medium text-[var(--primary-dk)] bg-[var(--accent-bg)] px-1.5 py-0.5 rounded"
                  >
                    {t}
                  </span>
                ))}
              {seedCount > 6 && (
                <span className="text-[11px] text-[var(--text-faint)]">+{seedCount - 6}</span>
              )}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-1 border-t border-[var(--border)]">
          <span className="text-[11px] text-[var(--text-muted)]">
            {seedCount} tracked ticker{seedCount !== 1 ? "s" : ""}
          </span>
          <span className="text-[11px] text-[var(--primary)] group-hover:underline font-medium">
            Open →
          </span>
        </div>
      </div>
    </Link>
  );
}

export default async function ThemeDashboard() {
  let allThemes: Theme[] = [];
  let error: string | null = null;

  try {
    allThemes = await themes.list();
  } catch (e) {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  // Separate parent themes and sub-themes
  const parentThemes = allThemes.filter((t) => !t.parent_theme_id);
  const subThemes = allThemes.filter((t) => !!t.parent_theme_id);

  return (
    <div className="space-y-8">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">Theme Dashboard</h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            {allThemes.length} theme{allThemes.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <Link
          href="/theme/new"
          className="text-sm px-3 py-1.5 rounded-lg bg-[var(--primary)] text-white hover:bg-[var(--primary-dk)] transition-colors"
        >
          + New theme
        </Link>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      {/* Empty state */}
      {!error && allThemes.length === 0 && (
        <div className="rounded-xl border-2 border-dashed border-[var(--border)] py-16 text-center">
          <p className="text-[var(--text-muted)] text-sm">No themes yet.</p>
          <p className="text-[var(--text-faint)] text-xs mt-1">
            Create your first theme to start discovering companies.
          </p>
          <Link
            href="/theme/new"
            className="inline-block mt-4 text-sm px-4 py-2 rounded-lg bg-[var(--primary)] text-white hover:bg-[var(--primary-dk)] transition-colors"
          >
            + Create theme
          </Link>
        </div>
      )}

      {/* Parent themes grid */}
      {parentThemes.length > 0 && (
        <section>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {parentThemes.map((t) => (
              <ThemeCard key={t.id} theme={t} />
            ))}
          </div>
        </section>
      )}

      {/* Sub-themes section */}
      {subThemes.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-[var(--text-muted)] mb-3 uppercase tracking-wide">
            Sub-themes
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {subThemes.map((t) => (
              <ThemeCard key={t.id} theme={t} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
