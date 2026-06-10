import type { CalendarEvent } from "@/lib/api";
import { AgendaRow } from "./AgendaRow";
import { agendaLabel } from "./calendarDates";

export function AgendaList({ events }: { events: CalendarEvent[] }) {
  // Windowed catalysts get a dimmed footer block (approved mockup) —
  // their "date" is a window midpoint/end, not a day they happen on.
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

  // Pre-compute date labels: show the label only on the first row for each date.
  const labels = dated.map((ev, i) => {
    const prev = dated[i - 1];
    return i === 0 || ev.date !== prev.date ? agendaLabel(ev.date) : "";
  });

  return (
    <div>
      {dated.map((ev, i) => (
        <AgendaRow key={`d-${i}`} event={ev} dateLabel={labels[i]} />
      ))}
      {windowed.map((ev, i) => (
        <AgendaRow
          key={`w-${i}`}
          event={ev}
          dateLabel={ev.kind === "catalyst" ? ev.detail.timeframe : ""}
          dimmed
        />
      ))}
    </div>
  );
}
