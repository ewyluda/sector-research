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
  low: "bg-[var(--surface)] text-[var(--text-muted)] ring-[var(--border)]",
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
      <div className="px-4 py-3 text-sm text-[var(--text-faint)]" data-print-hide="true">
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
  const [showGroup, setShowGroup] = useState(false);

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
    <div className="rounded-md border border-[var(--surface)] bg-[var(--bg)]/40 p-3 text-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`rounded px-1.5 py-0.5 text-[11px] ring-1 shrink-0 ${
              MATERIALITY_BADGE[item.materiality] ?? MATERIALITY_BADGE.low
            }`}
          >
            {item.materiality}
          </span>
          <span className="text-[var(--text-muted)] text-xs shrink-0">
            {TYPE_LABEL[item.event_type] ?? item.event_type}
          </span>
          <span className="text-[var(--text-faint)] shrink-0">·</span>
          <span className="text-[var(--text-faint)] text-xs shrink-0">{item.filing_date}</span>
          {item.group_count > 1 && (
            <button
              onClick={() => setShowGroup((v) => !v)}
              title={`${item.group_count} near-duplicate filings — click to ${showGroup ? "collapse" : "expand"}`}
              className="rounded bg-[var(--surface)] px-1.5 py-0.5 text-[11px] text-[var(--text-muted)] ring-1 ring-[var(--border)] hover:bg-[var(--border)] shrink-0"
            >
              ×{item.group_count}
            </button>
          )}
        </div>
        <div className="flex gap-2 shrink-0">
          {item.document_url && (
            <a
              href={item.document_url}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--text-muted)] hover:bg-[var(--surface)]"
            >
              Filing ↗
            </a>
          )}
          <button
            onClick={handleDismiss}
            disabled={busy}
            title={
              item.group_count > 1
                ? `Dismisses all ${item.group_count} grouped filings`
                : undefined
            }
            className="rounded border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--text-muted)] hover:bg-[var(--surface)] disabled:opacity-50"
          >
            {busy ? "…" : "Dismiss"}
          </button>
        </div>
      </div>
      <div className="mt-1.5 font-medium text-[var(--text)]">{item.headline}</div>
      <div className="mt-0.5 text-xs text-[var(--text-muted)]">{item.summary}</div>
      {showGroup && item.group_headlines.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-xs text-[var(--text-muted)]">
          {item.group_headlines.map((h, i) => (
            <li key={i}>{h}</li>
          ))}
        </ul>
      )}
      {error && <div className="mt-2 text-xs text-rose-400">{error}</div>}
    </div>
  );
}
