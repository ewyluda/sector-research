"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { OrphanEventGroup } from "@/lib/orphanEvents";
import { MaterialEventsDrawer } from "./MaterialEventsDrawer";

interface Props {
  groups: OrphanEventGroup[];
  /** One-shot deep-link target: ?expand_events= ticker with no board row. */
  autoExpandTicker?: string | null;
  onDismissed: (ticker: string, eventId: string) => void;
}

/**
 * Material events on tickers with no status-board entry. Without this
 * section a /status?expand_events= deep link from Today silently no-ops
 * for seed-only tickers.
 */
export function OrphanEventsSection({ groups, autoExpandTicker, onDismissed }: Props) {
  const [manualExpanded, setManualExpanded] = useState<Record<string, boolean>>({});

  // Merge the one-shot autoExpandTicker into the display map without an effect.
  const expanded = useMemo(
    () =>
      autoExpandTicker
        ? { ...manualExpanded, [autoExpandTicker]: manualExpanded[autoExpandTicker] ?? true }
        : manualExpanded,
    [manualExpanded, autoExpandTicker],
  );

  if (groups.length === 0) return null;

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        Material events — untracked tickers
      </h2>
      {groups.map((g) => (
        <div key={g.ticker} className="rounded-lg border border-[var(--border)] bg-[var(--surface)]">
          <div className="flex items-center gap-3 px-3 py-2">
            <Link
              href={`/company/${g.ticker}`}
              className="font-mono font-bold text-sm text-[var(--text)] hover:text-[var(--primary)]"
            >
              {g.ticker}
            </Link>
            <span className="text-xs text-[var(--text-muted)] truncate flex-1">
              {g.events[0].headline}
            </span>
            <button
              type="button"
              data-print-hide="true"
              // Read merged `expanded` (not prev) so the first click after auto-expand collapses.
              onClick={() => setManualExpanded((prev) => ({ ...prev, [g.ticker]: !expanded[g.ticker] }))}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-400 text-[11px] font-semibold"
            >
              8-K ×{g.events.length}
            </button>
          </div>
          {expanded[g.ticker] && (
            <div className="border-t border-[var(--border)]">
              <MaterialEventsDrawer
                items={g.events}
                onDismissed={(id) => onDismissed(g.ticker, id)}
              />
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
