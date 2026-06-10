/** Local-date helpers for the calendar. Never use Date.toISOString() for
 * day math here — it converts to UTC and shifts evening local dates. */

export function isoLocal(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function parseIsoLocal(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function mondayOf(d: Date): Date {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
}

export function addDays(d: Date, n: number): Date {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

const DAY_FMT = new Intl.DateTimeFormat("en-US", { weekday: "short", day: "numeric" });
const AGENDA_FMT = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });

export function dayLabel(d: Date): string {
  return DAY_FMT.format(d); // "Tue 9"-style
}

export function agendaLabel(iso: string): string {
  return AGENDA_FMT.format(parseIsoLocal(iso)); // "Tue, Jun 16"-style
}
