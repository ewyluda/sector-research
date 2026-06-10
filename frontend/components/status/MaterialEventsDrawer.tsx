"use client";

import { useState } from "react";
import type { MaterialEvent } from "@/lib/api";
import { events as eventsApi } from "@/lib/api";

interface Props {
  items: MaterialEvent[];
  onDismissed: (eventId: string) => void;
}

const MATERIALITY_BADGE: Record<string, string> = {
  high: "bg-rose-900/40 text-rose-200 ring-rose-700",
  medium: "bg-amber-900/40 text-amber-200 ring-amber-700",
  low: "bg-slate-800 text-slate-300 ring-slate-700",
};

const TYPE_LABEL: Record<string, string> = {
  guidance: "Guidance",
  personnel: "Personnel",
  ma: "M&A",
  financing: "Financing",
  other: "Other",
};

export function MaterialEventsDrawer({ items, onDismissed }: Props) {
  if (items.length === 0) {
    return (
      <div className="px-4 py-3 text-sm text-slate-500" data-print-hide="true">
        No material events in the last 14 days.
      </div>
    );
  }

  return (
    <div className="space-y-2 px-4 py-3" data-print-hide="true">
      {items.map((item) => (
        <EventRow key={item.id} item={item} onDismissed={onDismissed} />
      ))}
    </div>
  );
}

function EventRow({
  item,
  onDismissed,
}: {
  item: MaterialEvent;
  onDismissed: (eventId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleDismiss() {
    setBusy(true);
    setError(null);
    try {
      await eventsApi.dismiss(item.id);
      onDismissed(item.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Dismiss failed");
      setBusy(false);
    }
  }

  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`rounded px-1.5 py-0.5 text-[11px] ring-1 shrink-0 ${
              MATERIALITY_BADGE[item.materiality] ?? MATERIALITY_BADGE.low
            }`}
          >
            {item.materiality}
          </span>
          <span className="text-slate-400 text-xs shrink-0">
            {TYPE_LABEL[item.event_type] ?? item.event_type}
          </span>
          <span className="text-slate-500 shrink-0">·</span>
          <span className="text-slate-500 text-xs shrink-0">{item.filing_date}</span>
        </div>
        <div className="flex gap-2 shrink-0">
          {item.document_url && (
            <a
              href={item.document_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              Filing ↗
            </a>
          )}
          <button
            onClick={handleDismiss}
            disabled={busy}
            className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            {busy ? "…" : "Dismiss"}
          </button>
        </div>
      </div>
      <div className="mt-1.5 font-medium text-slate-200">{item.headline}</div>
      <div className="mt-0.5 text-xs text-slate-400">{item.summary}</div>
      {error && <div className="mt-2 text-xs text-rose-400">{error}</div>}
    </div>
  );
}
