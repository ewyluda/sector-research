"use client";

import { useState } from "react";
import type { CalendarEvent } from "@/lib/api";
import { AgendaRow } from "./AgendaRow";
import { agendaLabel } from "./calendarDates";

export function AgendaList({
  events,
  activeTickers,
}: {
  events: CalendarEvent[];
  // When provided, catalyst rows whose ticker has no active board entry get
  // an "archived thesis" chip. Catalyst rows only: they're the one row type
  // that is thesis-derived and survives archiving (earnings rows lose their
  // has_thesis flag, so they can't tell "archived" from "never a thesis").
  activeTickers?: Set<string>;
}) {
  // Windowed catalysts have no resolved date — their "date" is a window
  // midpoint/end, not a day they happen on. They collapse into one compact
  // group per ticker at the bottom, expandable to the full rows.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const dated = events.filter(
    (e) => !(e.kind === "catalyst" && e.detail.windowed)
  );
  const windowed = events.filter(
    (e) => e.kind === "catalyst" && e.detail.windowed
  );

  if (dated.length === 0 && windowed.length === 0) {
    return (
      <p className="text-xs text-[var(--text-muted)] py-3">
        Nothing on the calendar for this range.
      </p>
    );
  }

  const isArchived = (ev: CalendarEvent) =>
    activeTickers !== undefined &&
    ev.kind === "catalyst" &&
    !activeTickers.has(ev.ticker);

  // Pre-compute date labels: show the label only on the first row for each date.
  const labels = dated.map((ev, i) => {
    const prev = dated[i - 1];
    return i === 0 || ev.date !== prev.date ? agendaLabel(ev.date) : "";
  });

  // Group undated rows per ticker, preserving first-seen order.
  const undatedGroups = new Map<string, CalendarEvent[]>();
  for (const ev of windowed) {
    const ticker = ev.ticker ?? "—";
    const group = undatedGroups.get(ticker);
    if (group) group.push(ev);
    else undatedGroups.set(ticker, [ev]);
  }

  function toggle(ticker: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  return (
    <div>
      {dated.map((ev, i) => (
        <AgendaRow key={`d-${i}`} event={ev} dateLabel={labels[i]} archived={isArchived(ev)} />
      ))}
      {[...undatedGroups.entries()].map(([ticker, group]) => (
        <div key={`w-${ticker}`}>
          <button
            type="button"
            onClick={() => toggle(ticker)}
            className="flex w-full items-baseline gap-2.5 rounded-md px-2.5 py-1.5 mb-1 bg-[rgba(127,127,127,0.07)] text-xs text-left opacity-60 hover:opacity-80"
          >
            <span className="w-20 flex-none text-[11px] font-semibold text-[var(--text-muted)]">
              {expanded.has(ticker) ? "▾" : "▸"} Undated
            </span>
            <span className="text-[var(--text)]">
              <span className="font-semibold">{ticker}</span>
              {activeTickers !== undefined && !activeTickers.has(ticker) && (
                <span className="ml-1.5 rounded border border-[var(--text-muted)]/40 px-1 py-px text-[9px] text-[var(--text-muted)] align-middle">
                  archived thesis
                </span>
              )}
              <span className="text-[var(--text-muted)]">
                {" "}— {group.length} undated catalyst{group.length === 1 ? "" : "s"}
              </span>
            </span>
          </button>
          {expanded.has(ticker) &&
            group.map((ev, i) => (
              <AgendaRow
                key={`w-${ticker}-${i}`}
                event={ev}
                dateLabel={ev.kind === "catalyst" ? ev.detail.timeframe : ""}
                dimmed
                archived={isArchived(ev)}
              />
            ))}
        </div>
      ))}
    </div>
  );
}
