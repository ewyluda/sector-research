import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";
import { KIND_COLOR, eventHref, eventSubtitle } from "./EventCard";

const KIND_PILL: Record<CalendarEvent["kind"], string> = {
  economic: "ECON",
  earnings: "EARN",
  catalyst: "CAT",
};

export function AgendaRow({
  event,
  dateLabel,
  dimmed = false,
  archived = false,
}: {
  event: CalendarEvent;
  dateLabel: string; // empty string when a previous row already showed the day
  dimmed?: boolean;
  archived?: boolean; // ticker has no active board entry — tag "archived thesis"
}) {
  const href = eventHref(event);
  const body = (
    <div
      className={`flex items-baseline gap-2.5 rounded-md px-2.5 py-1.5 mb-1 bg-[rgba(127,127,127,0.07)] text-xs ${dimmed ? "opacity-60" : ""}`}
    >
      <span className="w-20 flex-none text-[11px] font-semibold text-[var(--text-muted)]">
        {dateLabel}
      </span>
      <span
        className="flex-none rounded-full px-2 py-px text-[9px] font-semibold text-black"
        style={{ backgroundColor: KIND_COLOR[event.kind] }}
      >
        {KIND_PILL[event.kind]}
      </span>
      <span className="text-[var(--text)]">
        <span className="font-semibold">
          {event.kind === "economic" ? event.title : event.ticker}
        </span>
        {archived && (
          <span className="ml-1.5 rounded border border-[var(--text-muted)]/40 px-1 py-px text-[9px] text-[var(--text-muted)] align-middle">
            archived thesis
          </span>
        )}
        {event.kind !== "economic" && (
          <span className="text-[var(--text-muted)]"> — {event.kind === "catalyst" ? event.title : eventSubtitle(event)}</span>
        )}
        {event.kind === "economic" && eventSubtitle(event) && (
          <span className="text-[var(--text-muted)]"> — {eventSubtitle(event)}</span>
        )}
      </span>
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-80">{body}</Link> : body;
}
