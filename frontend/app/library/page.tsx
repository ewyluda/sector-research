"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
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

// Current status vocabulary only — gate-era statuses (awaiting_approval) are gone.
const STATUS_LABEL: Record<string, string> = {
  in_progress: "Running",
  paused:      "Paused",
  completed:   "Complete",
  watchlist:   "Watchlist",
  pass:        "Pass",
  abandoned:   "Abandoned",
  error:       "Error",
};

const STATUS_DOT: Record<string, string> = {
  in_progress: "bg-[var(--color-accent)] animate-pulse",
  paused:      "bg-amber-400",
  completed:   "bg-emerald-400",
  watchlist:   "bg-amber-400",
  pass:        "bg-[var(--text-muted)]",
  abandoned:   "bg-[var(--text-faint)]",
  error:       "bg-red-400",
};

const ABANDON_AGE_MS = 7 * 24 * 60 * 60 * 1000;

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function activityTs(run: RunSummary): number {
  const iso = run.updated_at ?? run.created_at;
  return iso ? new Date(iso).getTime() : 0;
}

function hasThesis(run: RunSummary): boolean {
  return run.thesis_status != null && run.thesis_status !== "PENDING";
}

/** A stuck pipeline run: still in_progress/paused but started over ~7 days ago. */
function isZombie(run: RunSummary): boolean {
  if (run.status !== "in_progress" && run.status !== "paused") return false;
  if (!run.created_at) return false;
  return Date.now() - new Date(run.created_at).getTime() > ABANDON_AGE_MS;
}

function StatusChip({ status }: { status: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
      <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[status] ?? "bg-slate-400"}`} />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

function VerdictBadge({ thesis_status }: { thesis_status: ThesisStatus | null }) {
  if (!thesis_status || thesis_status === "PENDING") return null;
  return (
    <span
      className={`px-2 py-0.5 rounded-full border text-xs font-semibold ${
        THESIS_BADGE[thesis_status] ?? THESIS_BADGE.PENDING
      }`}
    >
      {thesis_status}
    </span>
  );
}

// ── Filters ────────────────────────────────────────────────────────────────────

type StatusFilter = "all_active" | "completed" | "watchlist" | "abandoned";
type View = StatusFilter | "data_gaps";

const STATUS_FILTERS: { key: StatusFilter; label: string }[] = [
  { key: "all_active", label: "All Active" },
  { key: "completed",  label: "Complete" },
  { key: "watchlist",  label: "Watchlist" },
  { key: "abandoned",  label: "Abandoned" },
];

function matchesStatus(run: RunSummary, filter: StatusFilter): boolean {
  if (filter === "all_active") return run.status !== "abandoned";
  return run.status === filter;
}

// ── Ticker group ───────────────────────────────────────────────────────────────

interface TickerGroup {
  ticker: string;
  runs: RunSummary[]; // newest-first
}

function groupByTicker(runs: RunSummary[]): TickerGroup[] {
  const byTicker = new Map<string, RunSummary[]>();
  for (const run of runs) {
    const key = run.ticker.toUpperCase();
    const bucket = byTicker.get(key);
    if (bucket) bucket.push(run);
    else byTicker.set(key, [run]);
  }
  const groups: TickerGroup[] = [];
  for (const [ticker, group] of byTicker) {
    group.sort((a, b) => activityTs(b) - activityTs(a));
    groups.push({ ticker, runs: group });
  }
  groups.sort((a, b) => activityTs(b.runs[0]) - activityTs(a.runs[0]));
  return groups;
}

// ── Run row (inside an expanded group) ────────────────────────────────────────

function RunRow({ run, onAbandon }: { run: RunSummary; onAbandon: (run: RunSummary) => void }) {
  const abandoned = run.status === "abandoned";
  return (
    <div
      className={`flex items-center flex-wrap gap-x-3 gap-y-1 px-4 py-2.5 border-t border-[var(--color-border)] ${
        abandoned ? "opacity-60" : ""
      }`}
    >
      <span className="text-xs text-[var(--color-text-muted)] tabular-nums w-24 flex-shrink-0">
        {fmtDate(run.updated_at ?? run.created_at)}
      </span>
      <span className="w-24 flex-shrink-0">
        <StatusChip status={run.status} />
      </span>
      <VerdictBadge thesis_status={run.thesis_status} />
      {run.conviction_score !== null && run.status !== "in_progress" && (
        <span className="text-xs font-mono text-[var(--color-text-secondary)] tabular-nums">
          {run.conviction_score} conviction
        </span>
      )}
      {run.loop_count > 0 && (
        <span
          title={`Risk stress-test triggered ${run.loop_count} deep-dive retry loop${run.loop_count !== 1 ? "s" : ""}`}
          className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 text-xs font-medium cursor-help"
        >
          ↻ L{run.loop_count}
        </span>
      )}
      {run.gap_count > 0 && (
        <span
          title={`${run.gap_count} data gap${run.gap_count !== 1 ? "s" : ""} (missing or low-confidence findings) across the 9 deep-dive categories`}
          className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 text-xs font-medium cursor-help"
        >
          {run.gap_count} gap{run.gap_count !== 1 ? "s" : ""}
        </span>
      )}
      {run.theme_name && (
        <span className="text-xs text-[var(--color-text-muted)] truncate">{run.theme_name}</span>
      )}
      <span className="ml-auto flex items-center gap-3 flex-shrink-0">
        {isZombie(run) && (
          <button
            onClick={() => onAbandon(run)}
            className="px-2 py-1 rounded border border-red-500/25 text-red-400 text-xs font-medium
                       hover:bg-red-500/10 transition-colors"
          >
            Abandon
          </button>
        )}
        <Link
          href={`/pipeline/${run.id}`}
          className="text-xs text-[var(--color-accent)] hover:underline"
        >
          open →
        </Link>
      </span>
    </div>
  );
}

// ── Ticker group card ─────────────────────────────────────────────────────────

function TickerGroupCard({
  group,
  onAbandon,
}: {
  group: TickerGroup;
  onAbandon: (run: RunSummary) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const latest = group.runs[0];
  const allAbandoned = group.runs.every((r) => r.status === "abandoned");

  return (
    <div
      className={`rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] ${
        allAbandoned ? "opacity-60" : ""
      }`}
    >
      {/* div+role, not <button>: the ticker <Link> inside would be invalid
          interactive-inside-interactive HTML. Keyboard parity via Enter/Space. */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((e) => !e)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((x) => !x);
          }
        }}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left cursor-pointer
                   hover:bg-[var(--color-accent)]/3 transition-colors"
      >
        <svg
          className={`w-3.5 h-3.5 flex-shrink-0 text-[var(--color-text-muted)] transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
          aria-hidden="true"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2.5}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
        <Link
          href={`/company/${group.ticker}`}
          onClick={(e) => e.stopPropagation()}
          className="text-lg font-mono font-bold text-[var(--color-text-primary)] tracking-wide
                     hover:text-[var(--color-accent)] transition-colors"
        >
          {group.ticker}
        </Link>
        <span className="px-1.5 py-0.5 rounded bg-[var(--color-bg)] border border-[var(--color-border)] text-xs font-mono text-[var(--color-text-muted)] tabular-nums">
          {group.runs.length} run{group.runs.length !== 1 ? "s" : ""}
        </span>
        <VerdictBadge thesis_status={latest.thesis_status} />
        <span className="ml-auto flex items-center gap-3 flex-shrink-0">
          <StatusChip status={latest.status} />
          <span className="text-xs text-[var(--color-text-muted)] tabular-nums">
            {fmtDate(latest.updated_at ?? latest.created_at)}
          </span>
        </span>
      </div>

      {expanded && group.runs.map((run) => <RunRow key={run.id} run={run} onAbandon={onAbandon} />)}
    </div>
  );
}

// ── Data Gaps view (unchanged from the pre-rebuild page) ─────────────────────

function DataGapsView({
  data,
  loading,
  onTickerClick,
}: {
  data: import("@/lib/api").DataGapsResponse | null;
  loading: boolean;
  onTickerClick: (ticker: string) => void;
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
      </div>
    );
  }

  if (!data || data.gaps.length === 0) {
    return (
      <div className="text-center py-24">
        <p className="text-[var(--color-text-muted)] text-sm">No data gaps detected across runs.</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-[var(--color-text-muted)] mb-4">
        {data.gaps.length} gap type{data.gaps.length !== 1 ? "s" : ""} found across {data.total_runs_scanned} run{data.total_runs_scanned !== 1 ? "s" : ""}
      </p>
      <div className="space-y-2">
        {data.gaps.map((gap, i) => (
          <div
            key={i}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span
                    className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                      gap.gap_type === "hard_error"
                        ? "bg-red-500/10 text-red-400"
                        : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {gap.gap_type === "hard_error" ? "Error" : "Gap"}
                  </span>
                  <span className="text-xs text-[var(--color-text-muted)]">
                    {gap.category.replace(/_/g, " ")}
                  </span>
                </div>
                <p className="text-sm text-[var(--color-text-primary)]">{gap.description}</p>
                {gap.example_tickers.length > 0 && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <span className="text-xs text-[var(--color-text-muted)]">e.g.</span>
                    {gap.example_tickers.map((t) => (
                      <button
                        key={t}
                        onClick={() => onTickerClick(t)}
                        className="px-1.5 py-0.5 rounded bg-[var(--color-accent)]/10 text-[var(--color-accent)]
                                   text-xs font-mono font-medium hover:bg-[var(--color-accent)]/20 transition-colors"
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex-shrink-0 text-right">
                <p className="text-lg font-mono font-semibold text-[var(--color-text-primary)]">
                  {gap.occurrences}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {Math.round(gap.frequency * 100)}% of runs
                </p>
              </div>
            </div>
            {/* Frequency bar */}
            <div className="mt-3 h-1 rounded-full bg-[var(--color-border)] overflow-hidden">
              <div
                className={`h-full rounded-full ${
                  gap.gap_type === "hard_error" ? "bg-red-400" : "bg-amber-400"
                }`}
                style={{ width: `${Math.round(gap.frequency * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────

export default function LibraryPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [view, setView] = useState<View>("all_active");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [themeId, setThemeId] = useState<string>("");
  const [thesisOnly, setThesisOnly] = useState(false);
  const [themeList, setThemeList] = useState<Theme[]>([]);
  const [dataGaps, setDataGaps] = useState<import("@/lib/api").DataGapsResponse | null>(null);
  const [gapsLoading, setGapsLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    themesApi.list().then(setThemeList).catch(() => {});
  }, []);

  // One fetch; status / theme / thesis / search filters are all client-side.
  // `loading` only guards the initial load — refetches (post-abandon) keep the
  // current list mounted so group expansion state survives.
  useEffect(() => {
    api.list({ limit: 500 })
      .then(setRuns)
      .finally(() => setLoading(false));
  }, [refreshKey]);

  useEffect(() => {
    if (view !== "data_gaps") return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setGapsLoading(true);
    const opts: Record<string, string> = {};
    if (themeId) opts.theme_id = themeId;
    api.dataGaps(opts as Parameters<typeof api.dataGaps>[0])
      .then(setDataGaps)
      .finally(() => setGapsLoading(false));
  }, [view, themeId, refreshKey]);

  // Theme / thesis / search filters apply before status, so the status chips
  // count within the currently visible slice.
  const baseFiltered = useMemo(() => {
    const q = search.trim().toUpperCase();
    return runs.filter((r) => {
      if (themeId && r.theme_id !== themeId) return false;
      if (thesisOnly && !hasThesis(r)) return false;
      if (q && !r.ticker.toUpperCase().includes(q)) return false;
      return true;
    });
  }, [runs, themeId, thesisOnly, search]);

  const counts = useMemo(() => {
    const next: Partial<Record<StatusFilter, number>> = {};
    for (const f of STATUS_FILTERS) {
      next[f.key] = baseFiltered.filter((r) => matchesStatus(r, f.key)).length;
    }
    return next;
  }, [baseFiltered]);

  const groups = useMemo(() => {
    if (view === "data_gaps") return [];
    return groupByTicker(baseFiltered.filter((r) => matchesStatus(r, view)));
  }, [baseFiltered, view]);

  const visibleRunCount = groups.reduce((n, g) => n + g.runs.length, 0);

  async function handleAbandon(run: RunSummary) {
    const started = fmtDate(run.created_at);
    if (!confirm(`Abandon the ${run.ticker} run started ${started}? It stays in the Library, greyed out.`)) {
      return;
    }
    try {
      await api.abandon(run.id);
    } catch (e) {
      alert(`Failed to abandon run: ${e instanceof Error ? e.message : e}`);
    }
    setRefreshKey((k) => k + 1);
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
              All due diligence runs, grouped by ticker
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

        {/* Search, theme, has-thesis filters */}
        <div className="flex items-center flex-wrap gap-3 mb-4">
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
          <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] cursor-pointer select-none">
            <input
              type="checkbox"
              checked={thesisOnly}
              onChange={(e) => setThesisOnly(e.target.checked)}
              className="accent-[var(--color-accent)]"
            />
            Has thesis
          </label>
        </div>

        {/* Status filter chips */}
        <div className="mb-5 flex items-center flex-wrap gap-2">
          {[...STATUS_FILTERS, { key: "data_gaps" as View, label: "Data Gaps" }].map(({ key, label }) => {
            const isActive = view === key;
            const count = key === "data_gaps" ? undefined : counts[key as StatusFilter];
            return (
              <button
                key={key}
                onClick={() => setView(key as View)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer flex items-center gap-1.5 ${
                  isActive
                    ? "bg-[var(--color-accent)] text-white"
                    : "bg-[var(--color-surface)] text-[var(--color-text-secondary)] border border-[var(--color-border)] hover:text-[var(--color-text-primary)]"
                }`}
              >
                <span>{label}</span>
                {count != null && (
                  <span className={`text-[10px] tabular-nums font-mono ${
                    isActive ? "text-white/80" : "text-[var(--color-text-muted)]"
                  }`}>
                    {count}
                  </span>
                )}
              </button>
            );
          })}
          <span className="ml-auto text-xs text-[var(--color-text-muted)]">
            {view === "data_gaps"
              ? `${dataGaps?.gaps.length ?? 0} gap type${(dataGaps?.gaps.length ?? 0) !== 1 ? "s" : ""}`
              : `${groups.length} ticker${groups.length !== 1 ? "s" : ""} · ${visibleRunCount} run${visibleRunCount !== 1 ? "s" : ""}`}
          </span>
        </div>

        {/* Content */}
        {view === "data_gaps" ? (
          <DataGapsView
            data={dataGaps}
            loading={gapsLoading}
            onTickerClick={(t) => {
              setSearch(t);
              setView("all_active");
            }}
          />
        ) : loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 rounded-full border-2 border-[var(--color-accent)] border-t-transparent animate-spin" />
          </div>
        ) : groups.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <p className="text-[var(--color-text-muted)] text-sm">
              {view === "all_active" && !search && !themeId && !thesisOnly
                ? "No research runs yet. Start your first one."
                : "No runs match the current filters."}
            </p>
            {view === "all_active" && !search && !themeId && !thesisOnly && (
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
            {groups.map((group) => (
              <TickerGroupCard key={group.ticker} group={group} onAbandon={handleAbandon} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
