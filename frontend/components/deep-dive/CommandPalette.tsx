"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { SECTIONS, type SectionEntry } from "./sections";

interface FlatItem extends SectionEntry {
  group: string;
  searchBlob: string;
}

const ITEMS: FlatItem[] = (() => {
  const out: FlatItem[] = [];
  for (const section of SECTIONS) {
    out.push({
      ...section,
      group: "Section",
      searchBlob: `${section.label} ${section.title ?? ""}`.toLowerCase(),
    });
  }
  return out;
})();

function scoreMatch(blob: string, query: string): number {
  if (!query) return 0;
  const idx = blob.indexOf(query);
  if (idx < 0) return -1;
  // Earlier matches rank higher; full-word starts rank best.
  return idx === 0 ? 2 : blob[idx - 1] === " " ? 1 : 0;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ITEMS;
    return ITEMS
      .map((item) => ({ item, score: scoreMatch(item.searchBlob, q) }))
      .filter((r) => r.score >= 0)
      .sort((a, b) => b.score - a.score)
      .map((r) => r.item);
  }, [query]);

  useEffect(() => {
    // Clamp the active index when the filter set shrinks. Driven by external
    // length value, safe to set synchronously.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setActiveIdx((i) => Math.min(i, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  function jumpTo(item: FlatItem) {
    setOpen(false);
    const target = document.getElementById(item.id);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
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
      if (item) jumpTo(item);
    }
  }

  if (!open) return null;

  return (
    <div
      data-print-hide="true"
      role="dialog"
      aria-modal="true"
      aria-label="Jump to section"
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
            placeholder="Jump to section…"
            className="flex-1 bg-transparent outline-none text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-faint)]"
          />
          <kbd className="hidden sm:inline text-[10px] font-mono text-[var(--color-text-faint)] border border-[var(--color-border)] rounded px-1.5 py-0.5">
            Esc
          </kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <li className="px-4 py-6 text-center text-xs text-[var(--color-text-faint)]">
              No matching section.
            </li>
          ) : (
            filtered.map((item, i) => (
              <li key={item.id}>
                <button
                  onMouseEnter={() => setActiveIdx(i)}
                  onClick={() => jumpTo(item)}
                  className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors cursor-pointer ${
                    i === activeIdx
                      ? "bg-[var(--color-primary)]/10 text-[var(--color-text-primary)]"
                      : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-alt)]"
                  }`}
                >
                  <span className="flex-1 truncate">{item.title ?? item.label}</span>
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
            <kbd className="font-mono">↑</kbd> <kbd className="font-mono">↓</kbd> navigate · <kbd className="font-mono">↵</kbd> jump
          </span>
          <span>
            <kbd className="font-mono">⌘K</kbd> toggle
          </span>
        </div>
      </div>
    </div>
  );
}
