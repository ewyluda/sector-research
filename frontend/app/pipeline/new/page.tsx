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
  const [recentTickers, setRecentTickers] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    themes.list().then(setThemeList).catch(() => {});
  }, []);

  useEffect(() => {
    // Last 20 runs → dedupe tickers → show up to 6 as quick-fill chips.
    pipeline
      .list({ limit: 20 })
      .then((runs) => {
        const seen = new Set<string>();
        const tickers: string[] = [];
        for (const run of runs) {
          const t = run.ticker?.toUpperCase();
          if (t && !seen.has(t)) {
            seen.add(t);
            tickers.push(t);
            if (tickers.length >= 6) break;
          }
        }
        setRecentTickers(tickers);
      })
      .catch(() => {});
  }, []);

  const selectedTheme = themeList.find((t) => t.id === themeId) ?? null;

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
            Runs all 5 due-diligence phases automatically — quick screen through risk stress test — and produces a fully cited report. No approval gates.
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
            {recentTickers.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <span className="text-[10px] uppercase tracking-wider text-[var(--text-faint)] mr-1">Recent:</span>
                {recentTickers.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTicker(t)}
                    className={`font-mono text-[11px] px-2 py-0.5 rounded border transition-colors cursor-pointer ${
                      ticker === t
                        ? "bg-[var(--primary)]/15 text-[var(--primary)] border-[var(--primary)]/30"
                        : "bg-[var(--surface)] text-[var(--text-muted)] border-[var(--border)] hover:border-[var(--primary)]/40 hover:text-[var(--text)]"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
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
            {selectedTheme?.description && (
              <p className="text-[11px] text-[var(--text-faint)] mt-1.5 leading-relaxed line-clamp-2">
                {selectedTheme.description}
              </p>
            )}
          </div>

          {error && (
            <p className="text-sm text-[var(--error-text)] bg-[var(--error-bg)] border border-[var(--error-border)] rounded-lg px-4 py-3">
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
                { num: "1", label: "Quick Screen", sub: "GO/WATCHLIST/PASS decision from FMP fundamentals" },
                { num: "2", label: "Deep Dive", sub: "9 categories in parallel (incl. transcript forensics)" },
                { num: "3", label: "Thesis Construction", sub: "Bull/bear synthesis + variant perception" },
                { num: "4", label: "Risk Stress-Test", sub: "Tail scenarios + invalidation triggers" },
              ].map(({ num, label, sub }) => (
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
              <div className="flex items-start gap-3 pt-2 border-t border-[var(--border)]/60 mt-2">
                <span className="mt-0.5 flex-shrink-0 w-5 h-5 rounded-full bg-[var(--surface-alt)]
                                 text-[var(--text-faint)] text-xs font-semibold flex items-center justify-center">
                  5
                </span>
                <div>
                  <span className="text-sm font-medium text-[var(--text-muted)]">Position Monitor</span>
                  <span className="ml-2 text-[10px] font-medium uppercase tracking-wider text-[var(--text-faint)]">
                    Manual
                  </span>
                  <span className="text-xs text-[var(--text-faint)] ml-2">Entry zones + sizing, triggered after review</span>
                </div>
              </div>
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
