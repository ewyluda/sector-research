import Link from "next/link";
import type { CalendarEvent } from "@/lib/api";

export const KIND_COLOR: Record<CalendarEvent["kind"], string> = {
  economic: "#a78bfa",
  earnings: "#60a5fa",
  catalyst: "#fbbf24",
};

function fmtNum(v: number | null): string | null {
  if (v === null || v === undefined) return null;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(0)}M`;
  if (Math.abs(v) >= 1000) return v.toLocaleString("en-US");
  return Number(v.toFixed(2)).toString();
}

export function eventHref(ev: CalendarEvent): string | null {
  if (ev.kind === "earnings" && ev.detail.has_thesis && ev.detail.run_id) {
    return `/status?expand_earnings=${ev.detail.run_id}`;
  }
  if (ev.kind === "catalyst") return `/pipeline/${ev.detail.run_id}`;
  return null;
}

export function eventSubtitle(ev: CalendarEvent): string {
  if (ev.kind === "economic") {
    const unit = ev.detail.unit ?? "";
    const parts: string[] = [];
    if (ev.detail.actual !== null) parts.push(`actual ${fmtNum(ev.detail.actual)}${unit}`);
    if (ev.detail.estimate !== null) parts.push(`est ${fmtNum(ev.detail.estimate)}${unit}`);
    if (ev.detail.previous !== null) parts.push(`prev ${fmtNum(ev.detail.previous)}${unit}`);
    return parts.join(" · ");
  }
  if (ev.kind === "earnings") {
    const parts: string[] = [];
    if (ev.detail.eps_actual !== null) parts.push(`EPS ${fmtNum(ev.detail.eps_actual)}`);
    else if (ev.detail.eps_estimated !== null) parts.push(`EPS est ${fmtNum(ev.detail.eps_estimated)}`);
    if (ev.detail.has_thesis) parts.push("thesis tracked");
    return parts.join(" · ") || "Earnings";
  }
  return ev.detail.timeframe;
}

export function EventCard({ event }: { event: CalendarEvent }) {
  const href = eventHref(event);
  const body = (
    <div
      className="rounded-md px-2 py-1.5 mb-1.5 bg-[rgba(127,127,127,0.12)] border-l-[3px]"
      style={{ borderLeftColor: KIND_COLOR[event.kind] }}
    >
      <div className="text-[11px] font-medium text-[var(--text)] leading-tight">
        {event.kind === "earnings" ? event.ticker : event.title}
      </div>
      <div className="text-[10px] text-[var(--text-muted)] leading-tight">
        {event.kind === "catalyst" ? event.title : eventSubtitle(event)}
      </div>
      {event.kind === "catalyst" && (
        <div className="text-[9px] text-[var(--text-muted)] opacity-70">{event.ticker}</div>
      )}
    </div>
  );
  return href ? <Link href={href} className="block hover:opacity-80">{body}</Link> : body;
}
