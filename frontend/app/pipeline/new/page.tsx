"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { themes, pipeline } from "@/lib/api";
import type { Theme } from "@/lib/api";

function NewPipelineForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Pre-fill both fields from URL query params on first mount — used by the
  // "Run Quick Screen →" CTA on the theme detail page (ThemeDetailClient),
  // which links here as `/pipeline/new?ticker=VRT&theme=<theme-id>`.
  //
  // Lazy initializers (useState(() => ...)) run exactly once on mount and
  // avoid React 19's set-state-in-effect lint rule that would fire if we
  // did this hydration inside a useEffect.
  const [ticker, setTicker] = useState<string>(
    () => searchParams?.get("ticker")?.toUpperCase() ?? ""
  );
  const [themeId, setThemeId] = useState<string>(
    () => searchParams?.get("theme") ?? ""
  );
  const [themeList, setThemeList] = useState<Theme[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    themes.list().then(setThemeList).catch(() => {});
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!ticker.trim() || !themeId) return;
    setLoading(true);
    setError(null);
    try {
      const run = await pipeline.start(ticker.trim().toUpperCase(), themeId);
      router.push(`/pipeline/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-semibold text-[var(--text)] tracking-tight">
            New Research Run
          </h1>
          <p className="mt-1 text-sm text-[var(--text-faint)]">
            Run the full 6-phase due diligence pipeline on any ticker
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Ticker input */}
          <div>
            <label
              htmlFor="ticker"
              className="block text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-1.5"
            >
              Ticker
            </label>
            <input
              id="ticker"
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="e.g. NVDA"
              maxLength={10}
              required
              className="w-full px-4 py-3 rounded-lg bg-[var(--surface)] border border-[var(--border)]
                         text-[var(--text)] placeholder-[var(--text-faint)]
                         text-base font-mono tracking-widest
                         focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)]
                         transition-colors"
            />
          </div>

          {/* Theme select */}
          <div>
            <label
              htmlFor="theme"
              className="block text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-1.5"
            >
              Theme
            </label>
            <select
              id="theme"
              value={themeId}
              onChange={(e) => setThemeId(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-lg bg-[var(--surface)] border border-[var(--border)]
                         text-[var(--text)]
                         focus:outline-none focus:border-[var(--primary)] focus:ring-1 focus:ring-[var(--primary)]
                         transition-colors appearance-none cursor-pointer"
            >
              <option value="" disabled>Select a theme…</option>
              {themeList.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
              {error}
            </p>
          )}

          {/* Phase preview */}
          <div className="rounded-lg bg-[var(--surface)] border border-[var(--border)] p-4">
            <p className="text-xs font-medium text-[var(--text-faint)] uppercase tracking-wider mb-3">
              Pipeline phases
            </p>
            <div className="space-y-2">
              {[
                ["1", "Quick Screen", "GO/WATCHLIST/PASS decision from FMP fundamentals"],
                ["2", "Deep Dive", "9 categories in parallel (incl. transcript forensics)"],
                ["3", "Thesis Construction", "Bull/bear synthesis + variant perception"],
                ["4", "Risk Stress-Test", "Tail scenarios + invalidation triggers"],
                ["5", "Position Monitor", "Entry zones + sizing + monitoring cadence"],
              ].map(([num, label, sub]) => (
                <div key={num} className="flex items-start gap-3">
                  <span className="mt-0.5 flex-shrink-0 w-5 h-5 rounded-full bg-[var(--primary)]/15
                                   text-[var(--primary)] text-xs font-semibold flex items-center justify-center">
                    {num}
                  </span>
                  <div>
                    <span className="text-sm font-medium text-[var(--text)]">{label}</span>
                    <span className="text-xs text-[var(--text-faint)] ml-2">{sub}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || !ticker || !themeId}
            className="w-full py-3 rounded-lg bg-[var(--primary)] text-white font-semibold text-sm
                       hover:bg-[var(--primary-dk)] active:scale-[0.98]
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-all duration-150"
          >
            {loading ? "Starting…" : "Begin Research Run →"}
          </button>
        </form>
      </div>
    </main>
  );
}

// Next.js 16 requires useSearchParams callers to be wrapped in a Suspense
// boundary so the page can statically render the fallback shell while the
// URL params resolve on the client.
export default function NewPipelinePage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-[var(--bg)] flex items-center justify-center p-6">
          <div className="w-6 h-6 rounded-full border-2 border-[var(--primary)] border-t-transparent animate-spin" />
        </main>
      }
    >
      <NewPipelineForm />
    </Suspense>
  );
}
