import type { CalendarEvent } from "@/lib/api";
import { EventCard } from "./EventCard";
import { addDays, dayLabel, isoLocal } from "./calendarDates";

export function WeekLanes({
  monday,
  events,
}: {
  monday: Date;
  events: CalendarEvent[]; // already filtered to this week
}) {
  const todayIso = isoLocal(new Date());
  const days = Array.from({ length: 7 }, (_, i) => addDays(monday, i));
  const byDate = new Map<string, CalendarEvent[]>();
  for (const ev of events) {
    const list = byDate.get(ev.date) ?? [];
    list.push(ev);
    byDate.set(ev.date, list);
  }

  return (
    <div className="grid grid-cols-7 gap-1.5">
      {days.map((d) => {
        const iso = isoLocal(d);
        const isToday = iso === todayIso;
        return (
          <div
            key={iso}
            className={`rounded-md bg-[var(--surface-2,rgba(127,127,127,0.07))] p-1.5 min-h-[140px] ${isToday ? "outline outline-1 outline-blue-400/40" : ""}`}
          >
            <div className="text-[10px] uppercase tracking-wide text-[var(--text-muted)] mb-1.5">
              {dayLabel(d)}
            </div>
            {(byDate.get(iso) ?? []).map((ev, i) => (
              <EventCard key={`${ev.kind}-${ev.ticker ?? "us"}-${i}`} event={ev} />
            ))}
          </div>
        );
      })}
    </div>
  );
}
