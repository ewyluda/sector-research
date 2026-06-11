"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { SECTIONS } from "@/components/deep-dive/sections";
import { getTickers, pipeline } from "@/lib/api";

type AppRouter = ReturnType<typeof useRouter>;

interface PaletteItem {
  id: string;
  group: "Ticker" | "Surface" | "Run" | "Action" | "Section";
  title: string;
  searchBlob: string;
  run: (router: AppRouter) => void;
}

/** Tie-break order when match scores are equal. */
const GROUP_ORDER: Record<PaletteItem["group"], number> = {
  Ticker: 0,
  Action: 1,
  Section: 2,
  Surface: 3,
  Run: 4,
};

const SURFACES: { title: string; href: string }[] = [
  { title: "Today", href: "/" },
  { title: "Calendar", href: "/?tab=calendar" },
  { title: "Status board", href: "/status" },
  { title: "Themes", href: "/themes" },
  { title: "Filings", href: "/filings" },
  { title: "Filings graph", href: "/filings/graph" },
  { title: "Performance", href: "/performance" },
  { title: "Library", href: "/library" },
  { title: "Questions", href: "/questions" },
  { title: "Workspace runs", href: "/workspace" },
  { title: "Prospectus reports", href: "/prospectus" },
  { title: "Compare peers", href: "/compare" },
  { title: "New research run", href: "/pipeline/new" },
];

const SURFACE_ITEMS: PaletteItem[] = SURFACES.map(({ title, href }) => ({
  id: `surface:${href}`,
  group: "Surface",
  title,
  searchBlob: title.toLowerCase(),
  run: (r) => r.push(href),
}));

/** Section jump entries — only offered on /pipeline/[runId] report pages. */
const SECTION_ITEMS: PaletteItem[] = SECTIONS.map((section) => ({
  id: `section:${section.id}`,
  group: "Section",
  title: section.title ?? section.label,
  searchBlob: `${section.label} ${section.title ?? ""}`.toLowerCase(),
  run: () => {
    const target = document.getElementById(section.id);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  },
}));

function scoreMatch(blob: string, query: string): number {
  if (!query) return 0;
  const idx = blob.indexOf(query);
  if (idx < 0) return -1;
  // Earlier matches rank higher; full-word starts rank best.
  return idx === 0 ? 2 : blob[idx - 1] === " " ? 1 : 0;
}

export function GlobalCommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const [dynamicItems, setDynamicItems] = useState<PaletteItem[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  // Session cache: tickers + recent runs are fetched on first open only.
  const dynamicCache = useRef<PaletteItem[] | null>(null);

  // Section entries only make sense on a report page (/pipeline/[runId]).
  const onReportPage = /^\/pipeline\/(?!new$)[^/]+$/.test(pathname ?? "");

  // Global open / close shortcut: Cmd-K (mac) / Ctrl-K (everyone else), Esc to close.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      // Reset UI state on open. These are fire-once transitions tied to
      // the modal lifecycle, not cascading updates.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQuery("");
      setActiveIdx(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Fetch dynamic sources (tickers + recent runs) on first open, then reuse.
  useEffect(() => {
    if (!open) return;
    if (dynamicCache.current) {
      setDynamicItems(dynamicCache.current);
      return;
    }
    let cancelled = false;
    Promise.allSettled([getTickers(), pipeline.list({ limit: 15 })]).then(
      ([tickersRes, runsRes]) => {
        if (cancelled) return;
        const items: PaletteItem[] = [];
        if (tickersRes.status === "fulfilled") {
          for (const { ticker } of tickersRes.value) {
            items.push({
              id: `ticker:${ticker}`,
              group: "Ticker",
              title: ticker,
              searchBlob: ticker.toLowerCase(),
              run: (r) => r.push(`/company/${ticker}`),
            });
          }
        }
        if (runsRes.status === "fulfilled") {
          for (const run of runsRes.value) {
            const date = run.created_at?.slice(0, 10) ?? "—";
            items.push({
              id: `run:${run.id}`,
              group: "Run",
              title: `${run.ticker} · ${date} · ${run.status}`,
              searchBlob: `${run.ticker} ${date} ${run.status} ${run.theme_name ?? ""}`.toLowerCase(),
              run: (r) => r.push(`/pipeline/${run.id}`),
            });
          }
        }
        dynamicCache.current = items;
        setDynamicItems(items);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const tickerItems = dynamicItems.filter((i) => i.group === "Ticker");
    const runItems = dynamicItems.filter((i) => i.group === "Run");

    // Contextual actions for tickers the query prefixes (e.g. "orcl" →
    // "New run: ORCL", "Log trade: ORCL").
    const actionItems: PaletteItem[] = q
      ? tickerItems
          .filter((t) => t.searchBlob.startsWith(q))
          .flatMap((t): PaletteItem[] => [
            {
              id: `action:new-run:${t.title}`,
              group: "Action",
              title: `New run: ${t.title}`,
              searchBlob: t.searchBlob,
              run: (r) => r.push(`/pipeline/new?ticker=${t.title}`),
            },
            {
              id: `action:log-trade:${t.title}`,
              group: "Action",
              title: `Log trade: ${t.title}`,
              searchBlob: t.searchBlob,
              run: (r) => r.push(`/performance?log_trade=${t.title}`),
            },
          ])
      : [];

    // Assemble in tie-break group order so the stable sort preserves it.
    const all = [
      ...tickerItems,
      ...actionItems,
      ...(onReportPage ? SECTION_ITEMS : []),
      ...SURFACE_ITEMS,
      ...runItems,
    ];
    if (!q) return all;
    return all
      .map((item) => ({ item, score: scoreMatch(item.searchBlob, q) }))
      .filter((r) => r.score >= 0)
      .sort(
        (a, b) =>
          b.score - a.score || GROUP_ORDER[a.item.group] - GROUP_ORDER[b.item.group]
      )
      .map((r) => r.item);
  }, [query, dynamicItems, onReportPage]);

  useEffect(() => {
    // Clamp the active index when the filter set shrinks. Driven by external
    // length value, safe to set synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveIdx((i) => Math.min(i, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  function execute(item: PaletteItem) {
    setOpen(false);
    item.run(router);
  }

  function onListKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = filtered[activeIdx];
      if (item) execute(item);
    }
  }

  if (!open) return null;

  return (
    <div
      data-print-hide="true"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4"
      onClick={() => setOpen(false)}
    >
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
          <svg className="w-4 h-4 text-[var(--color-text-muted)] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onListKey}
            placeholder="Search tickers, pages, runs…"
            className="flex-1 bg-transparent outline-none text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-faint)]"
          />
          <kbd className="hidden sm:inline text-[10px] font-mono text-[var(--color-text-faint)] border border-[var(--color-border)] rounded px-1.5 py-0.5">
            Esc
          </kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <li className="px-4 py-6 text-center text-xs text-[var(--color-text-faint)]">
              No matches.
            </li>
          ) : (
            filtered.map((item, i) => (
              <li key={item.id}>
                <button
                  onMouseEnter={() => setActiveIdx(i)}
                  onClick={() => execute(item)}
                  className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors cursor-pointer ${
                    i === activeIdx
                      ? "bg-[var(--color-primary)]/10 text-[var(--color-text-primary)]"
                      : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-alt)]"
                  }`}
                >
                  <span className="flex-1 truncate">{item.title}</span>
                  <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-faint)]">
                    {item.group}
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center justify-between px-4 py-2 border-t border-[var(--color-border)] text-[10px] text-[var(--color-text-faint)]">
          <span>
            <kbd className="font-mono">↑</kbd> <kbd className="font-mono">↓</kbd> navigate · <kbd className="font-mono">↵</kbd> go
          </span>
          <span>
            <kbd className="font-mono">⌘K</kbd> toggle
          </span>
        </div>
      </div>
    </div>
  );
}
