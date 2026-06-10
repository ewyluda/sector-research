"use client";

/**
 * Unified calendar: "This week" lanes + "Coming up" agenda.
 * One fetch covers both (Monday of this week → end of week + range).
 * Filter chips gate kinds client-side; range changes refetch.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { getCalendarEvents } from "@/lib/api";
import type { CalendarEvent, CalendarEventKind, CalendarResponse } from "@/lib/api";
import { WeekLanes } from "./WeekLanes";
import { AgendaList } from "./AgendaList";
import { KIND_COLOR } from "./EventCard";
import { addDays, isoLocal, mondayOf } from "./calendarDates";

const RANGES = [14, 30, 90] as const;
type RangeDays = (typeof RANGES)[number];

const KIND_CHIPS: Array<{ kind: CalendarEventKind; label: string }> = [
  { kind: "economic", label: "Econ" },
  { kind: "earnings", label: "Earnings" },
  { kind: "catalyst", label: "Catalysts" },
];

export function CalendarView() {
  const [rangeDays, setRangeDays] = useState<RangeDays>(14);
  const [kinds, setKinds] = useState<Set<CalendarEventKind>>(
    () => new Set<CalendarEventKind>(["economic", "earnings", "catalyst"])
  );
  const [data, setData] = useState<CalendarResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasDataRef = useRef(false);
  const loading = data === null && !error;
  const failedInitialLoad = error !== null && data === null;

  const monday = useMemo(() => mondayOf(new Date()), []);
  const sundayIso = useMemo(() => isoLocal(addDays(monday, 6)), [monday]);

  useEffect(() => {
    let cancelled = false;
    getCalendarEvents(isoLocal(monday), isoLocal(addDays(monday, 6 + rangeDays)))
      .then((d) => {
        if (!cancelled) {
          hasDataRef.current = true;
          setData(d);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(
            hasDataRef.current
              ? "Could not refresh calendar — showing previous data."
              : "Could not load calendar."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [monday, rangeDays]);

  const visible = useMemo(
    () => (data?.events ?? []).filter((e) => kinds.has(e.kind)),
    [data, kinds]
  );
  const isWindowed = (e: CalendarEvent) => e.kind === "catalyst" && e.detail.windowed;
  const thisWeek = visible.filter((e) => e.date <= sundayIso && !isWindowed(e));
  const comingUp = visible.filter((e) => e.date > sundayIso || isWindowed(e));

  function toggleKind(kind: CalendarEventKind) {
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between" data-print-hide="true">
        <div className="flex gap-3 text-[11px] text-[var(--text-muted)]">
          {KIND_CHIPS.map(({ kind, label }) => (
            <button
              key={kind}
              onClick={() => toggleKind(kind)}
              className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 ${
                kinds.has(kind)
                  ? "border-[var(--text-muted)] text-[var(--text)]"
                  : "border-transparent opacity-50"
              }`}
            >
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ backgroundColor: KIND_COLOR[kind] }}
              />
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--error)]/30 bg-[var(--error)]/5 p-3 text-xs text-[var(--error)]">
          {error}
        </div>
      )}
      {data?.warnings.map((w) => (
        <div
          key={w}
          className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-400"
        >
          {w}
        </div>
      ))}

      {loading ? (
        <p className="text-xs text-[var(--text-muted)] py-6">Loading calendar…</p>
      ) : !failedInitialLoad ? (
        <>
          <section>
            <h2 className="text-[11px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
              This week
            </h2>
            <WeekLanes monday={monday} events={thisWeek} />
          </section>

          <section>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-[11px] uppercase tracking-widest text-[var(--text-muted)]">
                Coming up
              </h2>
              <div
                className="flex overflow-hidden rounded-md border border-[var(--text-muted)]/30 text-[10px]"
                data-print-hide="true"
              >
                {RANGES.map((r) => (
                  <button
                    key={r}
                    onClick={() => setRangeDays(r)}
                    className={`px-2.5 py-1 ${
                      rangeDays === r
                        ? "bg-blue-400/20 font-semibold text-[var(--text)]"
                        : "text-[var(--text-muted)]"
                    }`}
                  >
                    {r} days
                  </button>
                ))}
              </div>
            </div>
            <AgendaList events={comingUp} />
          </section>
        </>
      ) : null}
    </div>
  );
}
