"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { pipeline as api, themes as themesApi } from "@/lib/api";
import type { RunSummary, ThesisStatus, Theme } from "@/lib/api";

// ── Helpers ────────────────────────────────────────────────────────────────────

const THESIS_BADGE: Record<ThesisStatus | string, string> = {
  STRONG_BUY: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
  BUY:        "bg-teal-500/15 text-teal-400 border-teal-500/25",
  WATCHLIST:  "bg-amber-500/15 text-amber-400 border-amber-500/25",
  PASS:       "bg-slate-500/15 text-slate-400 border-slate-500/25",
  BROKEN:     "bg-red-500/15 text-red-400 border-red-500/25",
  PENDING:    "bg-[var(--color-surface)] text-[var(--color-text-muted)] border-[var(--color-border)]",
};

const STATUS_LABEL: Record<string, string> = {
  in_progress:       "Running",
  awaiting_approval: "Awaiting Approval",
  completed:         "Complete",
  watchlist:         "Watchlist",
  error:             "Error",
};

const STATUS_DOT: Record<string, string> = {
  in_progress:       "bg-[var(--color-accent)] animate-pulse",
  awaiting_approval: "bg-amber-400 animate-pulse",
  completed:         "bg-emerald-400",
  watchlist:         "bg-amber-400",
  error:             "bg-red-400",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ── Filter bar ─────────────────────────────────────────────────────────────────

type FilterStatus = "all" | "completed" | "in_progress" | "awaiting_approval" | "watchlist";

function FilterBar({
  active,
  onChange,
  total,
}: {
  active: FilterStatus;
  onChange: (f: FilterStatus) => void;
  total: number;
}) {
  const filters: { key: FilterStatus; label: string }[] = [
    { key: "all",               label: "All" },
    { key: "completed",         label: "Complete" },
    { key: "awaiting_approval", label: "Awaiting" },
    { key: "in_progress",       label: "Running" },
    { key: "watchlist",         label: "Watchlist" },
  ];

  return (
    <div className="flex items-center gap-2">
      {filters.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            active === key
              ? "bg-[var(--color-accent)] text-white"
              : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:text-[var(--color-text-primary)]"
          }`}
        >
          {label}
        </button>
      ))}
      <span className="ml-auto text-xs text-[var(--color-text-muted)]">
        {total} run{total !== 1 ? "s" : ""}
      </span>
    </div>
  );
}

// ── Run card ──────────────────────────────────────────────────────────────────

function RunCard({ run, onClick }: { run: RunSummary; onClick: () => void }) {
  const isLive = run.status === "in_progress" || run.status === "awaiting_approval";

  return (
    <div
      onClick={onClick}
      className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]
                 hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-accent)]/3
                 cursor-pointer transition-all p-5"
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: ticker + meta */}
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 mb-1">
            <span className="text-xl font-mono font-bold text-[var(--color-text-primary)] tracking-wide">
              {run.ticker}
            </span>
            {run.thesis_status && run.thesis_status !== "PENDING" && (
              <span
                className={`px-2 py-0.5 rounded-full border text-xs font-semibold ${
                  THESIS_BADGE[run.thesis_status] ?? THESIS_BADGE.PENDING
                }`}
              >
                {run.thesis_status}
              </span>
            )}
            {run.loop_count > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 text-xs font-medium">
                ↻ L{run.loop_count}
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[run.status] ?? "bg-slate-400"}`} />
              {STATUS_LABEL[run.status] ?? run.status}
            </span>
            <span>·</span>
            <span>Phase: {run.phase.replace(/_/g, " ")}</span>
            <span>·</span>
            <span>{fmtDate(run.updated_at ?? run.created_at)}</span>
          </div>
        </div>

        {/* Right: conviction score */}
        <div className="flex-shrink-0 text-right">
          {run.conviction_score !== null ? (
            <>
              <p className="text-2xl font-mono font-semibold text-[var(--color-accent)]">
                {run.conviction_score}
              </p>
              <p className="text-xs text-[var(--color-text-muted)]">conviction</p>
            </>
          ) : (
            <p className="text-xs text-[var(--color-text-muted)] mt-2">—</p>
          )}
        </div>
      </div>

      {/* Live badge */}
      {isLive && (
        <div className="mt-3 pt-3 border-t border-[var(--color-border)] flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
          <span className="text-xs text-[var(--color-accent)] font-medium">
            {run.status === "awaiting_approval" ? "Waiting for your approval" : "Running…"}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function LibraryPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [filter, setFilter] = useState<FilterStatus>("all");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [themeId, setThemeId] = useState<string>("");
  const [themeList, setThemeList] = useState<Theme[]>([]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    themesApi.list().then(setThemeList).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const opts: Record<string, string | number> = {};
    if (filter !== "all") opts.status = filter;
    if (themeId) opts.theme_id = themeId;
    if (debouncedSearch.trim()) opts.search = debouncedSearch.trim();
    api.list(opts as Parameters<typeof api.list>[0])
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [filter, themeId, debouncedSearch]);

  function navigate(run: RunSummary) {
    if (run.status === "completed" || run.status === "watchlist") {
      router.push(`/report/${run.id}`);
    } else {
      router.push(`/pipeline/${run.id}`);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--color-bg)] py-10 px-6">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-[var(--color-text-primary)] tracking-tight">
              Research Library
            </h1>
            <p className="mt-0.5 text-sm text-[var(--color-text-muted)]">
              All due diligence runs, signals, and completed theses
            </p>
          </div>
          <button
            onClick={() => router.push("/pipeline/new")}
            className="px-4 py-2 rounded-lg bg-[var(--color-accent)] text-white text-sm font-semibold
                       hover:bg-[var(--color-accent)]/90 active:scale-[0.98] transition-all"
          >
            + New Run
          </button>
        </div>

        {/* Search & theme filter */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              placeholder="Search by ticker..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                         text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]
                         focus:outline-none focus:border-[var(--color-accent)]/50 transition-colors"
            />
          </div>
          <select
            value={themeId}
            onChange={(e) => setThemeId(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)]
                       text-sm text-[var(--color-text-primary)]
                       focus:outline-none focus:border-[var(--color-accent)]/50 transition-colors"
          >
            <option value="">All Themes</option>
            {themeList.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>

        {/* Filter bar */}
        <div className="mb-5">
          <FilterBar active={filter} onChange={setFilter} total={runs.length} />
        </div>

        {/* Content */}
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
          </div>
        ) : runs.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <p className="text-[var(--color-text-muted)] text-sm">
              {filter === "all"
                ? "No research runs yet. Start your first one."
                : `No ${STATUS_LABEL[filter]?.toLowerCase() ?? filter} runs.`}
            </p>
            {filter === "all" && (
              <button
                onClick={() => router.push("/pipeline/new")}
                className="mt-2 px-5 py-2.5 rounded-lg bg-[var(--color-accent)] text-white text-sm font-semibold
                           hover:bg-[var(--color-accent)]/90 transition-colors"
              >
                Begin Research →
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {runs.map((run) => (
              <RunCard key={run.id} run={run} onClick={() => navigate(run)} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
