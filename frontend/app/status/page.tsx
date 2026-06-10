"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  status as statusApi,
  themes as themesApi,
  readThroughs,
  earnings as earningsApi,
  events as eventsApi,
  type Health,
  type ReadThroughsByRun,
  type StatusBoardEntry,
  type Theme,
  type EarningsBoardEntry,
  type ThesisPrintVerdictRow,
  type MaterialEvent,
} from "@/lib/api";
import { ReadThroughDrawer } from "@/components/status/ReadThroughDrawer";
import { EarningsDrawer } from "@/components/status/EarningsDrawer";
import { MaterialEventsDrawer } from "@/components/status/MaterialEventsDrawer";
import { WorkspaceButton } from "@/components/status/WorkspaceButton";

const HEALTH_PILL: Record<Health, string> = {
  healthy:   "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
  imminent:  "bg-blue-500/10 text-blue-400 border-blue-500/30",
  stale:     "bg-slate-500/10 text-slate-400 border-slate-500/30",
  triggered: "bg-amber-500/10 text-amber-400 border-amber-500/30",
  broken:    "bg-red-500/10 text-red-400 border-red-500/30",
};

const HEALTH_LABEL: Record<Health, string> = {
  healthy:   "Healthy",
  imminent:  "Imminent",
  stale:     "Stale",
  triggered: "Triggered",
  broken:    "Broken",
};

const HEALTH_ORDER: (Health | "all")[] = [
  "all", "broken", "triggered", "stale", "imminent", "healthy",
];

const VERDICT_BADGE: Record<"confirms" | "threatens" | "neutral" | "insufficient", string> = {
  confirms:     "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  threatens:    "border-red-500/30 bg-red-500/10 text-red-400",
  neutral:      "border-slate-500/30 bg-slate-500/10 text-slate-400",
  insufficient: "border-amber-500/30 bg-amber-500/10 text-amber-400",
};

const EVENT_BADGE: Record<string, string> = {
  high: "bg-rose-900/40 text-rose-200 ring-rose-700 hover:bg-rose-900/60",
  medium: "bg-amber-900/40 text-amber-200 ring-amber-700 hover:bg-amber-900/60",
  low: "bg-slate-800 text-slate-300 ring-slate-700 hover:bg-slate-700",
};

function daysUntil(isoDate: string): number {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const target = new Date(`${isoDate}T00:00:00Z`);
  return Math.max(0, Math.round((target.getTime() - today.getTime()) / 86400000));
}

function daysSince(isoDate: string): number {
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  const target = new Date(`${isoDate}T00:00:00Z`);
  return Math.max(0, Math.round((today.getTime() - target.getTime()) / 86400000));
}

function fmtDays(d: number): string {
  if (d === 0) return "today";
  if (d === 1) return "1d ago";
  return `${d}d ago`;
}

function fmtCatalystDays(d: number | null): string {
  if (d === null) return "undated";
  if (d < 0) return "in window";
  if (d === 0) return "today";
  return `${d}d`;
}

function HealthPill({ health }: { health: Health }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${HEALTH_PILL[health]}`}
    >
      {HEALTH_LABEL[health]}
    </span>
  );
}

function OverflowMenu({
  archived,
  onArchive,
  onUnarchive,
  onOpen,
}: {
  archived: boolean;
  onArchive: () => void;
  onUnarchive: () => void;
  onOpen: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Row menu"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
        className="px-2 py-0.5 text-[var(--text-muted)] hover:text-[var(--text)] rounded"
      >
        ⋯
      </button>
      {open && (
        <div
          className="absolute right-0 mt-1 z-10 min-w-[160px] rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg text-xs"
          onMouseDown={(e) => e.preventDefault()}
        >
          <button
            className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)]"
            onClick={(e) => { e.stopPropagation(); onOpen(); setOpen(false); }}
          >
            Open report
          </button>
          {archived ? (
            <button
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)]"
              onClick={(e) => { e.stopPropagation(); onUnarchive(); setOpen(false); }}
            >
              Unarchive
            </button>
          ) : (
            <button
              className="w-full text-left px-3 py-2 hover:bg-[var(--surface-alt)] text-amber-400"
              onClick={(e) => { e.stopPropagation(); onArchive(); setOpen(false); }}
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Row({
  entry,
  archived,
  onClick,
  onArchive,
  onUnarchive,
  actions,
}: {
  entry: StatusBoardEntry;
  archived: boolean;
  onClick: () => void;
  onArchive: () => void;
  onUnarchive: () => void;
  actions?: React.ReactNode;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter") onClick(); }}
      className={`grid grid-cols-[80px_110px_60px_minmax(0,1fr)_120px_70px_auto_40px] gap-3 items-center px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--accent-bg)] hover:bg-[var(--surface-alt)] cursor-pointer transition-colors ${archived ? "opacity-50" : ""}`}
    >
      <div className="font-mono font-bold text-sm text-[var(--text)] tracking-wide">
        {entry.ticker}
      </div>
      <div><HealthPill health={entry.health} /></div>
      <div className="font-mono text-sm text-[var(--text)] tabular-nums">
        {entry.conviction_score ?? "—"}
      </div>
      <div className="text-xs text-[var(--text-muted)] truncate">
        {entry.next_catalyst ? (
          <>
            <span className="text-[var(--text)]">{entry.next_catalyst.description}</span>
            <span className="ml-2 text-blue-400 font-medium">
              {fmtCatalystDays(entry.next_catalyst.days_until)}
            </span>
          </>
        ) : (
          <span className="text-[var(--text-faint)]">—</span>
        )}
      </div>
      <div className="text-[11px] text-[var(--text-muted)] truncate">
        {entry.theme_name}
      </div>
      <div className={`text-[11px] tabular-nums ${entry.days_since_update > 90 ? "text-slate-400" : "text-[var(--text-muted)]"}`}>
        {fmtDays(entry.days_since_update)}
      </div>
      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
        {actions}
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <OverflowMenu
          archived={archived}
          onArchive={onArchive}
          onUnarchive={onUnarchive}
          onOpen={onClick}
        />
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-12 rounded-lg border border-[var(--border)] bg-[var(--surface)] animate-pulse"
        />
      ))}
    </div>
  );
}

export default function StatusPage() {
  const router = useRouter();
  const [entries, setEntries] = useState<StatusBoardEntry[]>([]);
  const [archived, setArchived] = useState<Set<string>>(new Set());
  const [healthFilter, setHealthFilter] = useState<Health | "all">("all");
  const [themeId, setThemeId] = useState<string>("");
  const [themes, setThemes] = useState<Theme[]>([]);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rtByRun, setRtByRun] = useState<ReadThroughsByRun>({});
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);
  const [earningsByRun, setEarningsByRun] = useState<Record<string, EarningsBoardEntry>>({});
  const [earningsExpanded, setEarningsExpanded] = useState<Record<string, boolean>>({});
  const [eventsByTicker, setEventsByTicker] = useState<Record<string, MaterialEvent[]>>({});
  const [eventsExpanded, setEventsExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    themesApi.list().then(setThemes).catch(() => {});
  }, []);

  async function fetchBoard() {
    try {
      const res = await statusApi.board({
        theme_id: themeId || undefined,
        include_archived: includeArchived,
      });
      setEntries(res.entries);
      // Track which entries are currently archived (we sent
      // include_archived=true but the API doesn't tag them — infer from
      // the entry list when toggle is on by checking the next refetch.)
      // Simpler: when include_archived is on, we don't visually distinguish
      // unless we know archived_at. The API exposes it implicitly by the
      // fact they're absent when include_archived=false. Compute the set
      // by diff'ing against an include_archived=false fetch.
      if (includeArchived) {
        const visible = await statusApi.board({
          theme_id: themeId || undefined,
          include_archived: false,
        });
        const visibleIds = new Set(visible.entries.map((e) => e.run_id));
        setArchived(new Set(res.entries.filter((e) => !visibleIds.has(e.run_id)).map((e) => e.run_id)));
      } else {
        setArchived(new Set());
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load board");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchBoard();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchBoard();
    };
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") fetchBoard();
    }, 60_000);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [themeId, includeArchived]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await readThroughs.list();
        if (!cancelled) setRtByRun(data);
      } catch {
        // best-effort — leave previous data on the screen
      }
    }
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 60_000);
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      if (document.visibilityState !== "visible") return;
      try {
        const out = await earningsApi.board(14);
        if (cancelled) return;
        const next: Record<string, EarningsBoardEntry> = {};
        for (const e of out.entries) {
          next[e.run_id] = e;
        }
        setEarningsByRun(next);
      } catch {
        // soft fail; do not unmount the rest of the page
      }
    }
    refresh();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 60_000);
    const onVis = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const out = await eventsApi.list({ since_days: 14 });
        if (cancelled) return;
        const grouped: Record<string, MaterialEvent[]> = {};
        for (const ev of out.events) {
          (grouped[ev.ticker] ??= []).push(ev);
        }
        setEventsByTicker(grouped);
      } catch {
        // best-effort — leave previous data on the screen
      }
    }
    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 60_000);
    const onVis = () => {
      if (document.visibilityState === "visible") load();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  // Deep link from the unified calendar: /status?expand_earnings=<run_id>
  // auto-opens that run's EarningsDrawer once the board has loaded.
  // One-shot: the board refetches on a 60s poll, and re-applying would
  // fight a user who closed the drawer.
  const expandEarningsConsumed = useRef(false);
  useEffect(() => {
    if (expandEarningsConsumed.current) return;
    const runId = new URLSearchParams(window.location.search).get("expand_earnings");
    if (runId && earningsByRun[runId]) {
      expandEarningsConsumed.current = true;
      setEarningsExpanded((prev) => (prev[runId] ? prev : { ...prev, [runId]: true }));
    }
  }, [earningsByRun]);

  // Deep link from Today: /status?expand_events=<ticker> auto-opens that
  // ticker's MaterialEventsDrawer once board + events have loaded. One-shot.
  const expandEventsConsumed = useRef(false);
  useEffect(() => {
    if (expandEventsConsumed.current) return;
    const ticker = new URLSearchParams(window.location.search)
      .get("expand_events")
      ?.toUpperCase();
    if (!ticker || entries.length === 0) return;
    const entry = entries.find((en) => en.ticker === ticker);
    if (entry && (eventsByTicker[ticker] ?? []).length > 0) {
      expandEventsConsumed.current = true;
      setEventsExpanded((prev) => ({ ...prev, [entry.run_id]: true }));
    }
  }, [entries, eventsByTicker]);

  const counts = useMemo(() => {
    const c: Record<Health | "all", number> = {
      all: entries.length,
      broken: 0,
      triggered: 0,
      stale: 0,
      imminent: 0,
      healthy: 0,
    };
    for (const e of entries) c[e.health]++;
    return c;
  }, [entries]);

  const filtered = useMemo(
    () =>
      healthFilter === "all"
        ? entries
        : entries.filter((e) => e.health === healthFilter),
    [entries, healthFilter],
  );

  async function archiveEntry(run_id: string) {
    await statusApi.archive(run_id);
    fetchBoard();
  }

  async function unarchiveEntry(run_id: string) {
    await statusApi.unarchive(run_id);
    fetchBoard();
  }

  function handleReadThroughDismissed(runId: string, eventKey: string) {
    setRtByRun((prev) => ({
      ...prev,
      [runId]: (prev[runId] ?? []).filter((it) => it.event_key !== eventKey),
    }));
  }

  function handleEventDismissed(ticker: string, eventId: string) {
    setEventsByTicker((prev) => ({
      ...prev,
      [ticker]: (prev[ticker] ?? []).filter((ev) => ev.id !== eventId),
    }));
    fetchBoard(); // refresh the badge summary
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-8 flex flex-col gap-5">
      <header>
        <h1 className="text-xl font-semibold text-[var(--text)] tracking-wide">
          Status Board
        </h1>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          Active theses with health, catalyst proximity, and kill-criteria flags.
        </p>
      </header>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={themeId}
          onChange={(e) => setThemeId(e.target.value)}
          className="px-3 py-1.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-xs text-[var(--text)]"
        >
          <option value="">All themes</option>
          {themes.map((t) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <div className="flex items-center gap-1.5 flex-wrap">
          {HEALTH_ORDER.map((k) => (
            <button
              key={k}
              onClick={() => setHealthFilter(k)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition-colors flex items-center gap-1.5 ${
                healthFilter === k
                  ? "bg-[var(--accent-bg)] text-[var(--primary-dk)]"
                  : "bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)] hover:text-[var(--text)]"
              }`}
            >
              <span>{k === "all" ? "All" : HEALTH_LABEL[k]}</span>
              <span className="text-[10px] tabular-nums font-mono opacity-70">
                {counts[k]}
              </span>
            </button>
          ))}
        </div>

        <label className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          Include archived
        </label>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/5 p-3 text-xs text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <Skeleton />
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 space-y-2">
          <p className="text-[var(--text-muted)] text-sm">
            {entries.length === 0
              ? "No active theses yet."
              : `No ${healthFilter === "all" ? "" : HEALTH_LABEL[healthFilter as Health].toLowerCase() + " "}theses.`}
          </p>
          {entries.length === 0 && (
            <button
              onClick={() => router.push("/pipeline/new")}
              className="px-4 py-1.5 rounded-md bg-[var(--accent-bg)] text-[var(--primary-dk)] text-xs font-semibold"
            >
              Start a new run →
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          {/* Column header */}
          <div className="grid grid-cols-[80px_110px_60px_minmax(0,1fr)_120px_70px_auto_40px] gap-3 px-3 py-1 text-[10px] uppercase tracking-wider text-[var(--text-faint)]">
            <div>Ticker</div>
            <div>Health</div>
            <div>Conv</div>
            <div>Next catalyst</div>
            <div>Theme</div>
            <div>Refreshed</div>
            <div></div>
            <div></div>
          </div>
          {filtered.map((e) => {
            const items = rtByRun[e.run_id] ?? [];
            const isExpanded = expandedRunId === e.run_id;
            return (
              <div key={e.run_id} className="space-y-1">
                <Row
                  entry={e}
                  archived={archived.has(e.run_id)}
                  onClick={() => router.push(`/pipeline/${e.run_id}`)}
                  onArchive={() => archiveEntry(e.run_id)}
                  onUnarchive={() => unarchiveEntry(e.run_id)}
                  actions={
                    <>
                      {items.length > 0 && (
                        <button
                          type="button"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setExpandedRunId(isExpanded ? null : e.run_id);
                          }}
                          title="Read-through events"
                          className="rounded bg-amber-900/40 px-1.5 py-0.5 text-[11px] text-amber-200 ring-1 ring-amber-700 hover:bg-amber-900/60"
                        >
                          ⟿ {items.length}
                        </button>
                      )}
                      {e.material_events && (
                        <button
                          type="button"
                          data-print-hide="true"
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setEventsExpanded((m) => ({ ...m, [e.run_id]: !m[e.run_id] }));
                          }}
                          title={e.material_events.latest_headline}
                          className={`rounded px-1.5 py-0.5 text-[11px] ring-1 ${
                            EVENT_BADGE[e.material_events.max_materiality] ?? EVENT_BADGE.low
                          }`}
                        >
                          8-K ×{e.material_events.count_14d}
                        </button>
                      )}
                      {(() => {
                        const eb = earningsByRun[e.run_id];
                        if (!eb || !eb.print) return null;
                        const onClick = (ev: React.MouseEvent) => {
                          ev.stopPropagation();
                          setEarningsExpanded((m) => ({ ...m, [e.run_id]: !m[e.run_id] }));
                        };
                        if (eb.verdict) {
                          const colors = VERDICT_BADGE[eb.verdict.verdict];
                          return (
                            <button
                              onClick={onClick}
                              data-print-hide="true"
                              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-semibold ${colors}`}
                            >
                              📊 {eb.verdict.verdict}
                            </button>
                          );
                        }
                        if (eb.phase === "post") {
                          const days = daysSince(eb.print.earnings_date);
                          return (
                            <button
                              onClick={onClick}
                              data-print-hide="true"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-semibold"
                            >
                              📊 {days}d ago
                            </button>
                          );
                        }
                        if (eb.phase === "pre") {
                          const days = daysUntil(eb.print.earnings_date);
                          return (
                            <button
                              onClick={onClick}
                              data-print-hide="true"
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-blue-500/30 bg-blue-500/10 text-blue-400 text-[11px] font-semibold"
                            >
                              📅 T-{days}d
                            </button>
                          );
                        }
                        return null;
                      })()}
                      <WorkspaceButton ticker={e.ticker} researchRunId={e.run_id} />
                    </>
                  }
                />
                {isExpanded && items.length > 0 && (
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
                    <ReadThroughDrawer
                      runId={e.run_id}
                      items={items}
                      onDismissed={(ek) => handleReadThroughDismissed(e.run_id, ek)}
                    />
                  </div>
                )}
                {eventsExpanded[e.run_id] && (
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
                    <MaterialEventsDrawer
                      items={eventsByTicker[e.ticker] ?? []}
                      onDismissed={(id) => handleEventDismissed(e.ticker, id)}
                    />
                  </div>
                )}
                {earningsExpanded[e.run_id] && earningsByRun[e.run_id] && (
                  <EarningsDrawer
                    entry={earningsByRun[e.run_id]}
                    onVerdictGenerated={(v: ThesisPrintVerdictRow) => {
                      setEarningsByRun((m) => ({
                        ...m,
                        [e.run_id]: { ...m[e.run_id], verdict: v },
                      }));
                    }}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
