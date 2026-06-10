import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";
import { EventCard } from "@/components/catalysts/EventCard";
import { addDays, dayLabel, isoLocal } from "@/components/catalysts/calendarDates";

export function TodayLanes({
  events,
  warnings,
  error,
  today,
}: {
  events: CalendarEvent[];
  warnings: string[];
  error: string | null;
  today: Date;
}) {
  const days = Array.from({ length: 4 }, (_, i) => addDays(today, i));
  const byDate = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const list = byDate.get(ev.date) ?? [];
    list.push(ev);
    byDate.set(ev.date, list);
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-medium text-[var(--text-muted)] uppercase tracking-wide">
          Today + next 3 days
        </h2>
        <Link href="/catalysts" className="text-xs text-[var(--primary)] hover:underline">
          Full calendar →
        </Link>
      </div>

      {error ? (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      ) : (
        /* today's lane is slightly wider */
        <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-1.5">
          {days.map((d, i) => {
            const iso = isoLocal(d);
            const dayEvents = byDate.get(iso) ?? [];
            return (
              <div
                key={iso}
                className={`rounded-md bg-[rgba(127,127,127,0.07)] p-1.5 min-h-[120px] ${
                  i === 0 ? "outline outline-1 outline-blue-400/40" : ""
                }`}
              >
                <div className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
                  {i === 0 ? `Today · ${dayLabel(d)}` : dayLabel(d)}
                </div>
                {dayEvents.length === 0 ? (
                  <div className="text-[11px] text-[var(--text-faint)]">—</div>
                ) : (
                  dayEvents.map((ev, j) => (
                    <EventCard key={`${ev.kind}-${ev.ticker ?? "us"}-${j}`} event={ev} />
                  ))
                )}
              </div>
            );
          })}
        </div>
      )}

      {warnings.length > 0 && (
        <p className="mt-1.5 text-[11px] text-[var(--text-faint)]">{warnings.join(" · ")}</p>
      )}
    </section>
  );
}
